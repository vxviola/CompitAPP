"""Confronto volontario fra un gruppo locale e gli eventi letti da Argo."""
from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime

import argo_client
import sync_argo
from models import get_db


def _firma(valori):
    return tuple(valori[k] or '' for k in ('data', 'materia', 'voto', 'descrizione'))


def _ultimo(eventi):
    """Gli eventi in conflitto senza una cronologia certa restano da verificare."""
    if all(e['versione'] for e in eventi):
        versione = max(e['versione'] for e in eventi)
        eventi = [e for e in eventi if e['versione'] == versione]
        ritirato = next((e for e in eventi if e['eliminato']), None)
        if ritirato:
            return ritirato
    stati = {None if e['eliminato'] else _firma(e['valori']) for e in eventi}
    return eventi[0] if len(stati) == 1 else None


def _anno_scolastico(data):
    return sync_argo.inizio_anno(datetime.fromisoformat(data)).year


def _leggi_gruppo(conn, nome, gruppo):
    righe = conn.execute("""SELECT v.id, v.argo_uid, e.versione FROM voti v LEFT JOIN argo_eventi e
            ON e.studente=v.studente AND e.categoria='voti' AND e.uid=v.argo_uid
            WHERE v.studente=? AND v.data=? AND v.materia=? AND v.voto=? AND COALESCE(v.descrizione,'')=?""",
            (nome, *_firma(gruppo))).fetchall()
    return righe if {r['id'] for r in righe} == {r['id'] for r in gruppo['righe']} else []


def _risultato(esito, messaggio, trovati=None, righe=None):
    return dict(esito=esito, messaggio=messaggio, trovati=trovati, righe=righe or {})


def _indice_anno(studente, inizio):
    sezione = argo_client.dashboard_sync(studente, inizio, solo_sessione_attiva=True)
    if sezione.get('ricaricaDati') or sezione.get('rimuoviDatiLocali'):
        raise argo_client.ArgoSyncError('Rilettura richiesta', 'aggiornamento')
    chiave = 'voti' if 'voti' in sezione else 'votiGiornalieri'
    if not isinstance(sezione.get(chiave), list):
        raise argo_client.ArgoSyncError('Elenco voti assente o incompleto')
    eventi = []
    for riga in sync_argo._lista(sezione, chiave):
        e = sync_argo._evento_voto(riga)
        if e is None:
            continue
        # I vecchi progressivi di voto da soli possono ripetersi per materia e periodo.
        if (not any(riga.get(k) not in (None, '') for k in ('pk', 'uid', 'pkVoto')) and
                not all(riga.get(k) not in (None, '') for k in ('prgVoto', 'pkMateria', 'pkPeriodo'))):
            e['uid'] = None
            e['alias'] = set()
        eventi.append(e)
    # Un alias dichiarato dal registro serve anche per collegare una correzione o un ritiro.
    # Un alias conteso non identifica positivamente alcuna valutazione.
    proprietari = defaultdict(set)
    for e in eventi:
        if e['primario']:
            for k in {e['primario'], *e['alias']}:
                proprietari[k].add(e['primario'])
    primari = {e['primario'] for e in eventi if e['primario']}
    per_uid = defaultdict(list)
    incerti = set()
    for e in eventi:
        if not e['uid']:
            if not e['eliminato']:
                incerti.add(_firma(e['valori']))
            continue
        possibili = {e['uid']} if e['uid'] in primari else proprietari[e['uid']]
        if len(possibili) > 1 and not e['primario']:
            if not e['eliminato']:
                incerti.add(_firma(e['valori']))
            continue
        uid = e['primario'] or next(iter(possibili), e['uid'])
        per_uid[uid].append(e)
        for k in {e['uid'], *e['alias']}:
            proprietari[k].add(uid)
    ultimi = {uid: _ultimo(serie) for uid, serie in per_uid.items()}
    conteggi = Counter(_firma(e['valori']) for e in ultimi.values() if e and not e['eliminato'])
    for uid, serie in per_uid.items():
        if ultimi[uid] is None:
            incerti.update(_firma(e['valori']) for e in serie if not e['eliminato'])
    for uid in primari:
        proprietari[uid] = {uid}
    return proprietari, ultimi, conteggi, incerti


def _confronta_gruppo(gruppo, righe, indice):
    firma = _firma(gruppo)
    proprietari, ultimi, conteggi, incerti = indice
    trovati, incerto = conteggi[firma], firma in incerti
    etichette = {}
    confermati = []
    for r in righe:
        possibili = proprietari.get(r['argo_uid'], ())
        uid = next(iter(possibili)) if len(possibili) == 1 else None
        e = ultimi.get(uid)
        if not r['argo_uid']:
            testo = 'Nessun identificativo del registro archiviato.'
        elif e is None or (r['versione'] and (not e['versione'] or e['versione'] < r['versione'])):
            testo = 'Identità o versione corrente da verificare nel portale.'
        elif e['eliminato']:
            testo = 'Argo ha restituito un ritiro per questo identificativo.'
        elif _firma(e['valori']) != firma:
            testo = ('Identificativo presente in un altro anno. Verifica la prova nel portale.'
                     if _anno_scolastico(e['valori']['data']) != _anno_scolastico(firma[0]) else
                     'Stesso identificativo con dati diversi nella risposta di Argo.')
        else:
            testo = 'Identificativo e dati coincidono con Argo.'
            confermati.append(uid)
        etichette[r['id']] = testo
    if len(confermati) == len(righe) == len(set(confermati)):
        return _risultato('distinti', 'Argo restituisce un identificativo distinto per ciascuna riga. Conserva queste valutazioni.', trovati, etichette)
    if trovati == 0:
        messaggio = 'Nella risposta di Argo mancano valutazioni identificabili con questi dati.'
    elif trovati == 1:
        messaggio = 'Argo ha restituito una valutazione identificabile con questi dati.'
    else:
        messaggio = f'Argo ha restituito {trovati} valutazioni identificabili con questi dati.'
    if len(set(confermati)) < len(confermati):
        messaggio += ' Più righe locali corrispondono alla stessa valutazione Argo.'
    if incerto:
        messaggio += ' Alcuni eventi hanno identità o cronologia incerta.'
    messaggio += ' Verifica nel portale quante prove compaiono prima di escludere una copia.'
    esito = 'incerto' if incerto else 'riscontro' if trovati else 'nessun_riscontro'
    return _risultato(esito, messaggio, trovati, etichette)


def confronta_gruppi_voti(studente, gruppi):
    """Una lettura per anno richiesto. La connessione locale si chiude prima di contattare Argo."""
    da_verificare = defaultdict(list)
    risultati = {}
    with closing(get_db()) as conn:
        for gruppo in gruppi:
            versione = gruppo['versione']
            righe = _leggi_gruppo(conn, studente['nome'], gruppo)
            if not righe:
                risultati[versione] = _risultato('indisponibile', 'Il gruppo è cambiato. Riapri la verifica dei voti.')
                continue
            try:
                inizio = sync_argo.inizio_anno(datetime.fromisoformat(gruppo['data']))
            except (TypeError, ValueError):
                risultati[versione] = _risultato('indisponibile', 'Data locale non valida per il confronto.')
                continue
            da_verificare[inizio].append((gruppo, righe))
    for inizio, gruppi_anno in da_verificare.items():
        try:
            indice = _indice_anno(studente, inizio)
        except argo_client.ArgoSyncError as exc:
            messaggi = {
                'accesso': 'Serve una sessione Argo attiva. Premi Aggiorna e riprova dopo la sincronizzazione.',
                'permessi': 'Il profilo Argo non consente di verificare i voti.',
                'rete': 'Argo non è raggiungibile. Riprova tra poco.',
                'servizio': 'Il servizio Argo è temporaneamente indisponibile. Riprova più tardi.',
                'limite': 'Argo ha raggiunto il limite di richieste. Riprova più tardi.',
                'aggiornamento': 'Argo richiede un aggiornamento. Premi Aggiorna e ripeti il confronto.',
            }
            messaggio = messaggi.get(exc.categoria, 'La risposta di Argo è incompleta o non verificabile. Riprova più tardi.')
            for gruppo, _ in gruppi_anno:
                risultati[gruppo['versione']] = _risultato('indisponibile', messaggio)
            continue
        for gruppo, righe in gruppi_anno:
            risultati[gruppo['versione']] = _confronta_gruppo(gruppo, righe, indice)
    return risultati


def confronta_voti(studente, gruppo):
    return confronta_gruppi_voti(studente, [gruppo])[gruppo['versione']]
