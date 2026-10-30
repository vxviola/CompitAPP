"""Notifiche HA opzionali: il destinatario viene scelto esplicitamente dall'utente."""
import json
import os
import re
from urllib.parse import urlencode
from datetime import date
import requests
from models import get_db

EVENTI = ('compiti', 'voti', 'assenze', 'note', 'bacheca', 'promemoria', 'documenti')
_slug = None
_ultimo_avviso_sync = None


def avviso_sincronizzazione(stati):
    """Un solo avviso tecnico HA, indipendente dalle notifiche scolastiche."""
    global _ultimo_avviso_sync
    if not stati or not os.environ.get('SUPERVISOR_TOKEN'):
        return
    errori = [s for s in stati if s.get('esito') == 'errore']
    accesso = sum(s.get('motivo') == 'accesso' for s in errori)
    firma = (len(errori), accesso)
    if firma == _ultimo_avviso_sync:
        return
    # Non cancellare un avviso se manca una verifica completa di qualche profilo.
    if not errori and any(s.get('esito') != 'ok' for s in stati):
        return
    _apertura('/')  # recupera lo slug per separare installazioni diverse
    if not _slug:
        return  # al prossimo ciclo si riprova, senza ID condivisi tra installazioni
    payload = {'notification_id': _slug + '_sincronizzazione'}
    azione = 'dismiss'
    if errori:
        azione = 'create'
        payload.update(
            title='UniScuola — accesso Argo fallito' if accesso else 'UniScuola — sincronizzazione fallita',
            message=(f'Dati non aggiornati per {len(errori)} profilo/i. '
                     'Apri UniScuola per verificare lo stato e l’ultimo aggiornamento riuscito. '
                     'I dati già scaricati sono conservati. L’avviso verrà rimosso dopo una '
                     'sincronizzazione completa riuscita per tutti i profili.'))
    try:
        r = requests.post('http://supervisor/core/api/services/persistent_notification/' + azione,
                          headers=_headers(), json=payload, timeout=(3, 8))
        r.raise_for_status()
        _ultimo_avviso_sync = firma
    except (requests.RequestException, RuntimeError):
        print('[HA] Avviso stato non consegnato; riprovo al prossimo controllo')


def configurazione(nome):
    conn = get_db()
    try:
        row = conn.execute('SELECT valore FROM meta WHERE chiave=?', ('ha_notify:' + nome,)).fetchone()
        try:
            cfg = json.loads(row['valore']) if row else {}
        except (ValueError, TypeError):
            cfg = {}
        if not isinstance(cfg, dict):
            cfg = {}
        try:
            destinatari = _destinatari(cfg)
        except ValueError:
            destinatari = []
        return {'attive': cfg.get('attive') is True, 'servizi': destinatari,
                'servizio': destinatari[0] if destinatari else '',
                'eventi': [e for e in cfg.get('eventi', EVENTI) if e in EVENTI]}
    finally:
        conn.close()


def _headers():
    token = os.environ.get('SUPERVISOR_TOKEN', '')
    if not token:
        raise RuntimeError('Disponibile quando UniScuola è eseguita in Home Assistant')
    return {'Authorization': 'Bearer ' + token}


def servizi():
    r = requests.get('http://supervisor/core/api/services', headers=_headers(), timeout=(3, 8))
    r.raise_for_status()
    result = []
    domini = r.json()
    entita_supportate = any(d.get('domain') == 'notify' and 'send_message' in d.get('services', {}) for d in domini)
    for dominio in domini:
        for servizio, info in dominio.get('services', {}).items():
            nome = dominio.get('domain', '') + '.' + servizio
            if nome == 'persistent_notification.create' or (dominio.get('domain') == 'notify' and servizio.startswith('mobile_app_')):
                result.append({'id': nome, 'nome': (info.get('name') or nome) + ' (servizio)'})
    if entita_supportate:
        stati = requests.get('http://supervisor/core/api/states', headers=_headers(), timeout=(3, 8))
        stati.raise_for_status()
        for stato in stati.json():
            entity_id = stato.get('entity_id', '')
            if re.fullmatch(r'notify\.[a-z0-9_]+', entity_id) and stato.get('state') != 'unavailable':
                result.append({'id': 'entity:' + entity_id,
                               'nome': (stato.get('attributes', {}).get('friendly_name') or entity_id) + ' (entità)'})
    return sorted(result, key=lambda s: s['nome'])


def _destinatari(cfg):
    valori = cfg.get('servizi') if 'servizi' in cfg else [cfg.get('servizio', '')]
    if 'servizi' not in cfg and valori == ['']:
        valori = []
    if (not isinstance(valori, list) or len(valori) > 50
            or any(not isinstance(v, str) or len(v) > 150 or not (
                v == 'persistent_notification.create'
                or re.fullmatch(r'notify\.mobile_app_[a-z0-9_]+', v)
                or re.fullmatch(r'entity:notify\.[a-z0-9_]+', v)) for v in valori)):
        raise ValueError('Seleziona dispositivi di notifica validi')
    return list(dict.fromkeys(valori))


def salva(nome, cfg):
    destinatari = _destinatari(cfg)
    if not isinstance(cfg.get('attive'), bool) or not isinstance(cfg.get('eventi'), list):
        raise ValueError('Configurazione non valida')
    if any(e not in EVENTI for e in cfg['eventi']):
        raise ValueError('Categoria di notifica non valida')
    if cfg['attive']:
        disponibili = {s['id'] for s in servizi()}
        if not destinatari or any(s not in disponibili for s in destinatari):
            raise ValueError('Seleziona almeno un dispositivo disponibile; rimuovi quelli non disponibili')
    dati = {'attive': cfg['attive'], 'servizi': destinatari, 'eventi': list(dict.fromkeys(cfg['eventi']))}
    conn = get_db()
    try:
        conn.execute('INSERT OR REPLACE INTO meta(chiave,valore) VALUES (?,?)', ('ha_notify:' + nome, json.dumps(dati)))
        conn.commit()
    finally:
        conn.close()


def _apertura(percorso):
    global _slug
    if _slug is None:
        try:
            r = requests.get('http://supervisor/addons/self/info', headers=_headers(), timeout=(3, 8))
            r.raise_for_status()
            valore = r.json().get('data', {}).get('slug', '')
            if re.fullmatch(r'[A-Za-z0-9_-]+', valore):
                _slug = valore
        except (requests.RequestException, ValueError, RuntimeError):
            pass
    return '/app/' + _slug + '?' + urlencode({'uniscuola': percorso}) if _slug else '/'


def _invia_dispositivo(servizio, titolo, messaggio, percorso):
    # Un ID tipizzato evita ambiguità tra un servizio e un'entità omonima.
    if servizio.startswith('entity:'):
        entity_id = servizio.removeprefix('entity:')
        if not re.fullmatch(r'notify\.[a-z0-9_]+', entity_id):
            return False
        dominio, azione = 'notify', 'send_message'
        # Solo i campi comuni: non tutte le entità supportano titolo o dati Companion.
        payload = {'entity_id': entity_id, 'message': (titolo[:150] + '\n' + str(messaggio)[:1500]).strip()}
    else:
        if not (servizio == 'persistent_notification.create' or re.fullmatch(r'notify\.mobile_app_[a-z0-9_]+', servizio)):
            return False
        dominio, azione = servizio.split('.', 1)
        payload = {'title': titolo[:150], 'message': str(messaggio)[:1500]}
    if dominio == 'notify' and azione != 'send_message':
        url = _apertura(percorso)
        payload['data'] = {'url': url, 'clickAction': url}
    try:
        r = requests.post(f'http://supervisor/core/api/services/{dominio}/{azione}',
                          headers=_headers(), json=payload, timeout=(3, 8))
        r.raise_for_status()
        return True
    except (requests.RequestException, RuntimeError):
        print('[HA] Notifica non consegnata; controllare il dispositivo nelle impostazioni')
        return False


def invia_dettaglio(nome, categoria, titolo, messaggio, percorso='/'):
    cfg = configurazione(nome)
    if not cfg['attive'] or categoria not in cfg['eventi']:
        return {}
    return {s: _invia_dispositivo(s, titolo, messaggio, percorso) for s in cfg['servizi']}


def invia(nome, categoria, titolo, messaggio, percorso='/', promemoria_id=None):
    if promemoria_id is None:
        esiti = invia_dettaglio(nome, categoria, titolo, messaggio, percorso)
        return bool(esiti) and all(esiti.values())
    cfg = configurazione(nome)
    if not cfg['attive'] or categoria not in cfg['eventi'] or not cfg['servizi']:
        return False
    conn = get_db()
    try:
        ok = True
        for servizio in cfg['servizi']:
            chiave = 'ha_consegna:' + json.dumps([nome, promemoria_id, servizio])
            if conn.execute('SELECT 1 FROM meta WHERE chiave=?', (chiave,)).fetchone():
                continue
            if _invia_dispositivo(servizio, titolo, messaggio, percorso):
                conn.execute('INSERT OR REPLACE INTO meta(chiave,valore) VALUES (?,?)', (chiave, '1'))
                conn.commit()
            else:
                ok = False
        return ok
    finally:
        conn.close()


def promemoria_documenti(studenti):
    for studente in studenti:
        nome = studente['nome']
        cfg = configurazione(nome)
        if not cfg['attive'] or 'documenti' not in cfg['eventi']:
            continue
        conn = get_db()
        try:
            righe = conn.execute('''SELECT id,titolo,promemoria_locale,letta,allegati FROM bacheca WHERE studente=?
                AND promemoria_locale IS NOT NULL AND promemoria_locale<=?''',
                                 (nome, date.today().isoformat())).fetchall()
            for r in righe:
                from allegati import leggi_allegati
                letti = {a['uid'] for a in conn.execute('SELECT uid FROM allegati_letti WHERE studente=? AND messaggio_id=? AND letto=1', (nome, r['id']))}
                if r['letta'] and all(a['uid'] in letti for a in leggi_allegati(r['allegati'])):
                    continue
                chiave = f'prom_doc:{nome}:{r["id"]}'
                inviato = conn.execute('SELECT valore FROM meta WHERE chiave=?', (chiave,)).fetchone()
                if inviato and inviato['valore'] == r['promemoria_locale']:
                    continue
                ok = invia(nome, 'documenti', f'UniScuola · {nome} · Da leggere', r['titolo'],
                           '/bacheca?' + urlencode({'studente': nome}) + '#msg-' + str(r['id']),
                           promemoria_id=[r['id'], r['promemoria_locale']])
                if ok:
                    conn.execute('INSERT OR REPLACE INTO meta(chiave,valore) VALUES (?,?)', (chiave, r['promemoria_locale']))
                    conn.commit()
        finally:
            conn.close()
