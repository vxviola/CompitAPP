"""Eventi Argo identificabili, aggiornamenti idempotenti e cursori transazionali.

La dashboard è un elenco di variazioni, non una fotografia completa: l'assenza
di una riga NON autorizza a cancellarla. Solo D o una lista compiti esplicita
del singolo registro permettono di ritirare dati già acquisiti.
"""
import json
from hashlib import sha256
from collections import Counter
from datetime import date, datetime, timedelta
from urllib.parse import urlencode
import pytz

import argo_client
import sync_state
from models import get_db

TZ = pytz.timezone('Europe/Rome')
CATEGORIE = ('compiti', 'voti', 'assenze', 'note', 'bacheca', 'argomenti', 'promemoria', 'registro')
SPEC = {
    'compiti': ('compiti', ('data', 'materia', 'testo'), ('data', 'materia')),
    'voti': ('voti', ('data', 'materia', 'voto', 'descrizione'), ('data', 'materia')),
    'assenze': ('assenze', ('data', 'tipo', 'descrizione', 'giustificata'), ('data', 'tipo')),
    'note': ('note_disciplinari', ('data', 'docente', 'testo'), ('data', 'docente')),
    'bacheca': ('bacheca', ('data', 'titolo', 'testo', 'mittente', 'allegati'), ('data', 'titolo')),
    'argomenti': ('argomenti', ('data', 'materia', 'argomento', 'attivita'), ('data', 'materia')),
    'promemoria': ('promemoria', ('data', 'testo', 'docente'), ('data', 'docente')),
}


def adesso():
    return datetime.now(TZ).replace(tzinfo=None, microsecond=0)


def inizio_anno(ora):
    return datetime(ora.year if ora.month >= 9 else ora.year - 1, 9, 1) - timedelta(days=7)


def _chiave(categoria, nome):
    return f'sync_eventi:v1:{categoria}:{nome}'


def piano(conn, categoria, nome, ora):
    r = conn.execute('SELECT valore FROM meta WHERE chiave=?', (_chiave(categoria, nome),)).fetchone()
    try:
        stato = json.loads(r['valore']) if r else {}
        completo = stato.get('inizio') == inizio_anno(ora).isoformat() and stato.get('completo') is True
        ultimo = datetime.fromisoformat(stato['ultimo']) if completo else None
        if ultimo and ultimo.tzinfo:
            ultimo = ultimo.astimezone(TZ).replace(tzinfo=None)
    except (ValueError, TypeError, KeyError, AttributeError):
        ultimo = None
    # Il primo passaggio della nuova versione rilegge lo storico senza notifiche.
    return {'dal': min(ultimo, ora) - timedelta(days=7) if ultimo else inizio_anno(ora),
            'silenzioso': ultimo is None, 'ora': ora}


def _lista(sezione, *chiavi):
    presenti = [k for k in chiavi if k in sezione]
    if not presenti:
        raise argo_client.ArgoSyncError('Sezione non presente nella risposta')
    righe = []
    for k in presenti:
        valori = [] if sezione[k] is None else sezione[k]
        if not isinstance(valori, list) or any(not isinstance(v, dict) for v in valori):
            raise argo_client.ArgoSyncError('Elenco Argo non valido')
        righe.extend(valori)
    return righe


def _testo(valore):
    return str(valore) if valore is not None else ''


def _uid(riga):
    valore = argo_client._pick(riga, 'pk', 'uid', 'pkVoto', 'pkNota', 'pkPromemoria', default=None)
    if valore is None and riga.get('prgVoto') is not None:
        valore = ['voto', riga['prgVoto'], riga.get('pkMateria'), riga.get('pkPeriodo')]
    if valore is None or valore == '':
        return None
    return (json.dumps(valore, sort_keys=True, separators=(',', ':'))
            if isinstance(valore, (dict, list)) else str(valore))


def _base(riga):
    op = _testo(riga.get('operazione')).upper()
    if op not in ('', 'I', 'U', 'M', 'D'):
        raise argo_client.ArgoSyncError('Operazione Argo non riconosciuta')
    versione = None
    try:
        dt = datetime.fromisoformat(_testo(riga.get('datEvento')).replace('Z', '+00:00'))
        versione = (dt.astimezone(TZ).replace(tzinfo=None) if dt.tzinfo else dt).isoformat()
    except ValueError:
        pass
    evento = {'uid': _uid(riga), 'eliminato': op == 'D', 'versione': versione, 'valori': {}}
    if evento['eliminato'] and not evento['uid']:
        raise argo_client.ArgoSyncError('Cancellazione senza identificativo: dati locali conservati')
    return evento


def _data(valore):
    try:
        return date.fromisoformat(_testo(valore)[:10]).isoformat()
    except ValueError:
        raise argo_client.ArgoSyncError('Data Argo non valida') from None


def normalizza(categoria, sezione):
    if categoria in ('compiti', 'registro') or (categoria == 'argomenti' and 'argomentiLezione' not in sezione):
        righe = _lista(sezione, 'registro')
    else:
        chiavi = {'voti': ('voti', 'votiGiornalieri'), 'assenze': ('appello', 'assenze'),
                  'note': ('noteDisciplinari',), 'bacheca': ('bacheca', 'bachecaAlunno'),
                  'argomenti': ('argomentiLezione',), 'promemoria': ('promemoria',)}[categoria]
        righe = _lista(sezione, *chiavi)
    eventi = []
    for r in righe:
        e = _base(r)
        pick = lambda *keys, default='': argo_client._pick(r, *keys, default=default)
        if categoria == 'compiti':
            if not e['eliminato'] and 'compiti' not in r:
                raise argo_client.ArgoSyncError('Lista compiti del registro non presente')
            figli = [] if r.get('compiti') is None else r['compiti']
            if not isinstance(figli, list) or any(not isinstance(c, dict) for c in figli):
                raise argo_client.ArgoSyncError('Compiti non validi')
            e['figli'] = []
            if not e['eliminato']:
                for i, c in enumerate(figli):
                    proprio_uid = _uid(c)
                    child_uid = proprio_uid or (f'{e["uid"]}:compito:{i}' if e['uid'] else None)
                    child = dict(e, uid=child_uid, gruppo=e['uid'], virtuale=proprio_uid is None)
                    child.pop('figli', None)
                    child['valori'] = {'data': _data(c.get('dataConsegna')),
                                       'materia': _testo(pick('materia')), 'testo': _testo(c.get('compito')).strip()}
                    if not child['valori']['testo'] or not child['valori']['materia']:
                        raise argo_client.ArgoSyncError('Compito incompleto')
                    e['figli'].append(child)
            eventi.append(e)
            continue
        if e['eliminato']:
            eventi.append(e)
            continue
        if categoria == 'voti':
            valore = pick('valore', 'decValore', 'decVoto', 'codVoto')
            if not argo_client._voto_valido(valore):
                if e['uid']:
                    e['eliminato'] = True
                    eventi.append(e)
                continue
            materia = pick('desMateria', 'materia', 'descrizioneMateria')
            if isinstance(materia, dict):
                materia = argo_client._pick(materia, 'descrizione', 'desMateria', 'nome')
            e['valori'] = {'data': _data(pick('datGiorno', 'data', 'dataVoto')), 'materia': _testo(materia),
                           'voto': str(valore), 'descrizione': _testo(pick('desCommento', 'commento', 'descrizione', 'desProva'))}
        elif categoria == 'assenze':
            e['valori'] = {'data': _data(pick('data', 'datAssenza')), 'tipo': _testo(pick('codEvento', default='A')),
                           'descrizione': _testo(pick('descrizione', 'desAssenza')),
                           'giustificata': int(argo_client._bool_arg(pick('giustificata', 'flgGiustificata', default='N')))}
        elif categoria == 'note':
            e['valori'] = {'data': _data(pick('datNota', 'data', 'datGiorno')), 'docente': _testo(pick('docente')),
                           'testo': _testo(pick('desNota', 'nota', 'testo'))}
        elif categoria == 'bacheca':
            allegati = r.get('listaAllegati')
            if allegati is not None and (not isinstance(allegati, list) or any(not isinstance(a, dict) for a in allegati)):
                raise argo_client.ArgoSyncError('Elenco allegati non valido')
            tipo = 'alunno' if r in (sezione.get('bachecaAlunno') or []) else 'bacheca'
            msg = argo_client._msg_bacheca(r, tipo)
            e['valori'] = {k: msg[k] for k in ('data', 'titolo', 'testo', 'mittente')}
            e['valori']['data'] = _data(msg['data'])
            e['valori']['allegati'] = json.dumps(msg['allegati'], ensure_ascii=False)
        elif categoria == 'promemoria':
            e['valori'] = {'data': _data(pick('datGiorno', 'data')), 'testo': _testo(pick('desAnnotazioni', 'testo')),
                           'docente': _testo(pick('docente'))}
        elif categoria == 'argomenti':
            e['valori'] = {'data': _data(pick('datGiorno', 'data')),
                           'materia': _testo(pick('materia', default=sezione.get('materia', ''))),
                           'argomento': _testo(pick('desArgomento', 'argomento')),
                           'attivita': _testo(pick('desAttivita', 'attivita'))}
            if not (e['valori']['argomento'] or e['valori']['attivita']):
                if not e['uid']:
                    continue
                e['eliminato'] = True
        elif categoria == 'registro':
            ora = r.get('ora')
            if not isinstance(ora, int) or isinstance(ora, bool) or ora < 1 or not pick('materia'):
                # Alcune righe del registro contengono compiti/annotazioni senza un'ora di lezione.
                if e['uid']:
                    e['eliminato'] = True
                    eventi.append(e)
                continue
            e['valori'] = {'data': _data(pick('datGiorno')), 'ora': ora,
                           'materia': _testo(pick('materia')), 'docente': _testo(pick('docente'))}
        eventi.append(e)
    return eventi


def _accetta(conn, nome, categoria, evento):
    if not evento['uid']:
        return True
    old = conn.execute('SELECT * FROM argo_eventi WHERE studente=? AND categoria=? AND uid=?',
                       (nome, categoria, evento['uid'])).fetchone()
    if old and old['versione'] and evento['versione']:
        if evento['versione'] < old['versione']:
            return False
        if evento['versione'] == old['versione'] and old['eliminato'] and not evento['eliminato']:
            return False
    if old and old['eliminato'] and not evento['eliminato'] and not evento['versione']:
        return False
    return True


def _segna(conn, nome, categoria, e):
    if e['uid']:
        conn.execute('''INSERT INTO argo_eventi(studente,categoria,uid,versione,eliminato) VALUES (?,?,?,?,?)
                        ON CONFLICT(studente,categoria,uid) DO UPDATE SET
                        versione=COALESCE(excluded.versione,argo_eventi.versione),eliminato=excluded.eliminato''',
                     (nome, categoria, e['uid'], e['versione'], int(e['eliminato'])))


def _candidati(conn, tabella, nome, valori, campi):
    where = ' AND '.join(f'COALESCE({k},\'\')=?' for k in campi)
    senza_uid = " AND (uid IS NULL OR uid='')" if tabella == 'bacheca' else ''
    return conn.execute(f'SELECT * FROM {tabella} WHERE studente=? AND argo_uid IS NULL{senza_uid} AND {where}',
                        [nome] + [valori[k] for k in campi]).fetchall()


def applica_record(conn, categoria, nome, e, univoco=True):
    if not _accetta(conn, nome, categoria, e):
        return False
    tabella, campi, naturali = SPEC[categoria]
    row = conn.execute(f'SELECT * FROM {tabella} WHERE studente=? AND argo_uid=?', (nome, e['uid'])).fetchone() if e['uid'] else None
    if row is None and categoria == 'bacheca' and e['uid']:
        row = conn.execute('SELECT * FROM bacheca WHERE studente=? AND uid=? AND argo_uid IS NULL', (nome, e['uid'])).fetchone()
    if e['eliminato']:
        if row:
            conn.execute(f'DELETE FROM {tabella} WHERE id=?', (row['id'],))
            if categoria == 'bacheca':
                conn.execute('DELETE FROM allegati_letti WHERE studente=? AND messaggio_id=?', (nome, row['id']))
        _segna(conn, nome, categoria, e)
        return False
    valori = e['valori']
    adottato = False
    if row is None:
        matches = _candidati(conn, tabella, nome, valori, campi)
        if len(matches) == 1:
            row, adottato = matches[0], True
        elif not matches and e['uid'] and univoco:
            matches = _candidati(conn, tabella, nome, valori, naturali)
            if len(matches) == 1:
                row, adottato = matches[0], True
        elif matches and not e['uid']:
            return False  # Evita nuovi duplicati legacy; non elimina righe non distinguibili.
    nuovo = row is None
    if row:
        e['id_locale'] = row['id']
        conn.execute(f'UPDATE {tabella} SET ' + ','.join(f'{k}=?' for k in campi)
                     + ',argo_uid=?,argo_gruppo=? WHERE id=?',
                     [valori[k] for k in campi] + [e['uid'], e.get('gruppo'), row['id']])
    else:
        colonne = ['studente', *campi, 'argo_uid', 'argo_gruppo']
        if categoria == 'bacheca':
            colonne.append('uid')
        cur = conn.execute(f'INSERT INTO {tabella} ({",".join(colonne)}) VALUES ({",".join("?" for _ in colonne)})',
                     [nome, *[valori[k] for k in campi], e['uid'], e.get('gruppo')]
                     + ([e['uid']] if categoria == 'bacheca' else []))
        e['id_locale'] = cur.lastrowid
    _segna(conn, nome, categoria, e)
    return nuovo and not adottato


def _compiti(conn, nome, gruppi):
    nuovi = []
    conteggi = Counter((e['valori']['data'], e['valori']['materia']) for g in gruppi for e in g['figli'])
    for gruppo in gruppi:
        if not _accetta(conn, nome, 'compiti_gruppi', gruppo):
            continue
        if gruppo['uid']:
            vecchi = conn.execute('SELECT * FROM compiti WHERE studente=? AND argo_gruppo=?', (nome, gruppo['uid'])).fetchall()
            usati = {e['uid'] for e in gruppo['figli'] if not e.get('virtuale')}
            da_associare = []
            # Compiti senza ID proprio: una diversa posizione nella lista non deve
            # spostare la spunta di completamento da un'attività a un'altra.
            for e in gruppo['figli']:
                if not e.get('virtuale'):
                    continue
                uguali = [r for r in vecchi if r['argo_uid'] not in usati
                          and all(r[k] == e['valori'][k] for k in SPEC['compiti'][1])]
                if uguali:
                    e['uid'] = uguali[0]['argo_uid']
                    usati.add(e['uid'])
                else:
                    da_associare.append(e)
            for e in da_associare:
                if e['uid'] in usati:
                    digest = sha256(json.dumps(e['valori'], sort_keys=True).encode()).hexdigest()[:24]
                    base = f'{gruppo["uid"]}:compito:{digest}'
                    indice = 0
                    while base + ':' + str(indice) in usati:
                        indice += 1
                    e['uid'] = base + ':' + str(indice)
                usati.add(e['uid'])
        presenti = {e['uid'] for e in gruppo['figli'] if e['uid']}
        if gruppo['uid']:
            for row in conn.execute('SELECT id,argo_uid FROM compiti WHERE studente=? AND argo_gruppo=?', (nome, gruppo['uid'])).fetchall():
                if row['argo_uid'] not in presenti:
                    conn.execute('DELETE FROM compiti WHERE id=?', (row['id'],))
                    _segna(conn, nome, 'compiti', dict(gruppo, uid=row['argo_uid'], eliminato=True))
        for e in gruppo['figli']:
            chiave = (e['valori']['data'], e['valori']['materia'])
            if applica_record(conn, 'compiti', nome, e, conteggi[chiave] == 1):
                nuovi.append(dict(e['valori'], _id=e.get('id_locale')))
        _segna(conn, nome, 'compiti_gruppi', gruppo)
    return nuovi


def _registro(conn, nome, eventi):
    for e in eventi:
        if not _accetta(conn, nome, 'registro', e):
            continue
        old = conn.execute('SELECT * FROM registro_argo WHERE studente=? AND uid=?', (nome, e['uid'])).fetchone() if e['uid'] else None
        if e['eliminato']:
            conn.execute('DELETE FROM registro_argo WHERE studente=? AND uid=?', (nome, e['uid']))
        elif e['uid']:
            v = e['valori']
            conn.execute('''INSERT INTO registro_argo(studente,uid,data,ora,materia,docente) VALUES (?,?,?,?,?,?)
                            ON CONFLICT(studente,uid) DO UPDATE SET data=excluded.data,ora=excluded.ora,
                            materia=excluded.materia,docente=excluded.docente''',
                         (nome, e['uid'], v['data'], v['ora'], v['materia'], v['docente']))
        if old:
            altro = conn.execute('SELECT 1 FROM registro_argo WHERE studente=? AND data=? AND ora=? AND materia=?',
                                  (nome, old['data'], old['ora'], old['materia'])).fetchone()
            if not altro:
                conn.execute('DELETE FROM lezioni_registro WHERE studente=? AND data=? AND ora=? AND materia=?',
                             (nome, old['data'], old['ora'], old['materia']))
        if not e['eliminato']:
            v = e['valori']
            conn.execute('''INSERT INTO lezioni_registro(studente,data,ora,materia,docente) VALUES (?,?,?,?,?)
                            ON CONFLICT(studente,data,ora,materia) DO UPDATE SET docente=excluded.docente''',
                         (nome, v['data'], v['ora'], v['materia'], v['docente']))
        _segna(conn, nome, 'registro', e)


def _notifica(categoria, nome, nuovi, silenzioso):
    if silenzioso:
        return
    import notifier
    import ha_client
    compiti = {}
    for v in nuovi:
        if categoria == 'compiti':
            if v['data'] >= adesso().date().isoformat():
                c = compiti.setdefault(v['data'], {'materie': [], 'compiti': []})
                c['materie'].append(v['materia']); c['compiti'].append(v['testo'])
        elif categoria == 'voti':
            notifier.notifica_nuovo_voto(nome, v['materia'], v['voto'], v['descrizione'])
        elif categoria == 'assenze':
            notifier.notifica_assenza(nome, v['data'], v['tipo'])
        elif categoria == 'note':
            notifier.notifica_nota(nome, v['data'], v['docente'], v['testo'])
        elif categoria == 'bacheca':
            notifier.notifica_bacheca(nome, v['titolo'], v['testo'], v['mittente'])
        elif categoria == 'promemoria':
            notifier.notifica_promemoria(nome, v['data'], v['docente'], v['testo'])
        if categoria != 'compiti':
            pagina = '/bacheca' if categoria == 'bacheca' else '/'
            percorso = pagina + '?' + urlencode({'studente': nome})
            if categoria == 'bacheca' and v.get('_id'):
                percorso += '#msg-' + str(v['_id'])
            titolo = {'voti':'Nuovo voto', 'assenze':'Nuova assenza', 'note':'Nota disciplinare',
                      'bacheca':'Comunicazione dalla scuola', 'promemoria':'Promemoria della scuola'}.get(categoria, 'Novità')
            testo = v.get('titolo') or v.get('testo') or v.get('descrizione') or v.get('materia') or titolo
            if categoria == 'voti':
                testo = v['materia'] + ': ' + v['voto']
            ha_client.invia(nome, categoria, f'UniScuola · {nome} · {titolo}', testo, percorso)
    if compiti:
        notifier.notifica_nuovi_compiti(nome, compiti)
        ha_client.invia(nome, 'compiti', f'UniScuola · {nome} · Nuovi compiti',
                        '\n'.join(f"{giorno}: {', '.join(info['materie'])}" for giorno, info in compiti.items()),
                        '/calendario?' + urlencode({'studente': nome}))


def sincronizza(studenti, categorie=CATEGORIE):
    riuscito = True
    for studente in studenti:
        nome = studente.get('nome', 'Studente')
        ora = adesso()
        conn = get_db()
        try:
            piani = {c: piano(conn, c, nome, ora) for c in categorie}
        finally:
            conn.close()
        try:
            dal = min(p['dal'] for p in piani.values())
            sezione = argo_client.dashboard_sync(studente, dal)
            # La creazione della sessione può rilevare un cambio di profilo e azzerare
            # i vecchi cursori. In quel caso la richiesta incrementale non basta.
            verifica = get_db()
            try:
                dopo_login = {c: piano(verifica, c, nome, ora) for c in categorie}
            finally:
                verifica.close()
            if any(dopo_login[c]['silenzioso'] and not piani[c]['silenzioso'] for c in categorie):
                piani = dopo_login
                dal = inizio_anno(ora)
                sezione = argo_client.dashboard_sync(studente, dal)
            if sezione.get('ricaricaDati') or sezione.get('rimuoviDatiLocali'):
                if dal > inizio_anno(ora):
                    sezione = argo_client.dashboard_sync(studente, inizio_anno(ora))
                for p in piani.values():
                    p['silenzioso'] = True
        except Exception:
            riuscito = False
            sync_state.errore(nome)
            print(f'[SYNC] {nome}: risposta Argo non verificata; dati e cursori conservati')
            continue
        for categoria in categorie:
            conn = None
            try:
                eventi = normalizza(categoria, sezione)
                conn = get_db()
                nuovi = []
                if categoria == 'compiti':
                    nuovi = _compiti(conn, nome, eventi)
                elif categoria == 'registro':
                    _registro(conn, nome, eventi)
                else:
                    naturali = SPEC[categoria][2]
                    conteggi = Counter(tuple(e['valori'].get(k) for k in naturali) for e in eventi if not e['eliminato'])
                    for e in eventi:
                        chiave = tuple(e['valori'].get(k) for k in naturali)
                        if applica_record(conn, categoria, nome, e, conteggi[chiave] <= 1):
                            nuovi.append(dict(e['valori'], _id=e.get('id_locale')))
                stato = {'ultimo': ora.isoformat(), 'inizio': inizio_anno(ora).isoformat(), 'completo': True}
                conn.execute('INSERT OR REPLACE INTO meta(chiave,valore) VALUES (?,?)',
                             (_chiave(categoria, nome), json.dumps(stato)))
                # Compatibilità con versioni precedenti e diagnostica esistente.
                conn.execute("INSERT OR REPLACE INTO meta(chiave,valore) VALUES (?, '1')", (f'storico:{categoria}:{nome}',))
                if categoria == 'bacheca':
                    conn.execute("INSERT OR REPLACE INTO meta(chiave,valore) VALUES (?, '1')", (f'storico:bacheca_allegati:{nome}',))
                if categoria == 'voti':
                    medie = argo_client.medie_da_sezione(sezione)
                    if medie:
                        conn.execute('INSERT OR REPLACE INTO meta(chiave,valore) VALUES (?,?)',
                                     (f'media_argo:{nome}', json.dumps(medie)))
                    elif eventi or 'mediaGenerale' in sezione or 'mediaMaterie' in sezione:
                        conn.execute('DELETE FROM meta WHERE chiave=?', (f'media_argo:{nome}',))
                conn.commit()
                conn.close(); conn = None
                _notifica(categoria, nome, nuovi, piani[categoria]['silenzioso'])
            except Exception:
                if conn:
                    conn.rollback()
                riuscito = False
                sync_state.errore(nome)
                print(f'[SYNC] {nome}: {categoria} non completata; prossimo controllo riprenderà dallo stesso punto')
            finally:
                if conn:
                    conn.close()
    return riuscito
