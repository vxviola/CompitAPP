"""Stato del ciclo di sincronizzazione, persistente per studente e senza credenziali."""
import json
import threading
from datetime import datetime
from models import get_db

_lock = threading.Lock()
_pubblicazione_lock = threading.Lock()
_in_corso = False
_errori = {}

MESSAGGI = {
    'accesso': ('Accesso Argo non riuscito', 'Verifica il collegamento nelle Impostazioni.'),
    'permessi': ('Accesso ai dati non consentito', 'Verifica i permessi del profilo nelle Impostazioni.'),
    'limite': ('Limite richieste Argo raggiunto', 'Attendi il prossimo controllo automatico.'),
    'rete': ('Argo non raggiungibile', 'Verifica la connessione; il controllo periodico resta attivo se pianificato.'),
    'servizio': ('Servizio Argo non disponibile', 'Attendi il prossimo controllo automatico.'),
    'risposta': ('Risposta Argo non verificabile', 'I dati sono conservati. Verifica il prossimo controllo.'),
    'sincronizzazione': ('Sincronizzazione incompleta', 'Verifica il collegamento nelle Impostazioni.'),
}


def inizia():
    global _in_corso
    if not _lock.acquire(blocking=False):
        return False
    _in_corso = True
    _errori.clear()
    return True


def errore(nome, motivo="sincronizzazione"):
    if _in_corso:
        motivo = motivo if motivo in MESSAGGI else 'sincronizzazione'
        if nome not in _errori or motivo == 'accesso':
            _errori[nome] = motivo


def inizia_manutenzione():
    return _lock.acquire(blocking=False)


def termina_manutenzione():
    _lock.release()


def leggi(nome):
    conn = get_db()
    try:
        r = conn.execute('SELECT valore FROM meta WHERE chiave=?', ('sync_ui:' + nome,)).fetchone()
        try:
            valore = json.loads(r['valore']) if r else {}
        except (ValueError, TypeError):
            valore = {}
        if not isinstance(valore, dict):
            valore = {}
        if _in_corso and nome in _errori:
            valore.update(esito="errore", motivo=_errori[nome])
        return diagnostica(dict(valore, in_corso=_in_corso))
    finally:
        conn.close()


def termina(nomi, fallito=False):
    global _in_corso
    try:
        ora = datetime.now().astimezone().isoformat(timespec='seconds')
        conn = get_db()
        try:
            stati = []
            for nome in nomi:
                precedente = leggi(nome)
                ok = not fallito and nome not in _errori
                dati = {'ultimo_tentativo': ora, 'esito': 'ok' if ok else 'errore',
                        'ultimo_successo': ora if ok else precedente.get('ultimo_successo'),
                        'motivo': None if ok else _errori.get(nome, 'sincronizzazione')}
                stati.append(dati)
                conn.execute('INSERT OR REPLACE INTO meta (chiave,valore) VALUES (?,?)',
                             ('sync_ui:' + nome, json.dumps(dati)))
            conn.commit()
        finally:
            conn.close()
        if stati:
            try:
                from ha_client import avviso_sincronizzazione
                avviso_sincronizzazione(stati)
            except Exception:
                print('[HA] Avviso stato non aggiornato; riprovo al prossimo controllo')
    finally:
        _in_corso = False
        _lock.release()
    pubblica(nomi)


def diagnostica(stato):
    """Allowlisted public status: never copy exception text or profile data."""
    from scheduler import pianificazione_sync
    prossimo, intervallo = pianificazione_sync()
    ora = datetime.now().astimezone()
    def data(valore):
        try:
            dt = datetime.fromisoformat(valore)
            return dt if dt.tzinfo and dt <= ora else None
        except (ValueError, TypeError):
            return None
    ultimo = data(stato.get('ultimo_successo'))
    tentativo = data(stato.get('ultimo_tentativo'))
    obsoleti = ultimo is None or (ora - ultimo).total_seconds() > max(600, intervallo * 120)
    esito = stato.get('esito') if stato.get('esito') in ('ok', 'errore') else 'attesa'
    motivo = stato.get('motivo') if stato.get('motivo') in MESSAGGI else None
    in_corso = stato.get('in_corso') is True
    livello = 'errore' if esito == 'errore' else ('attesa' if obsoleti or in_corso else 'ok')
    messaggio, azione = MESSAGGI.get(motivo, MESSAGGI['sincronizzazione']) if esito == 'errore' else (
        ('Collegamento da verificare: nessuna sincronizzazione riuscita', 'Attendi una sincronizzazione completa.') if ultimo is None else
        ('Dati non aggiornati di recente', 'Verifica il collegamento nelle Impostazioni.') if obsoleti else
        ('Sincronizzazione in corso', 'Attendi il completamento.') if in_corso else
        ('Registro aggiornato', 'Nessuna azione necessaria.'))
    if esito == 'errore' and in_corso:
        messaggio += ' — nuovo tentativo in corso'
    if not prossimo and esito == 'errore' and motivo in ('limite', 'servizio'):
        azione = 'Nessun prossimo controllo confermato. Verifica le Impostazioni.'
    return dict(esito=esito, motivo=motivo, in_corso=in_corso,
                ultimo_successo=ultimo.isoformat() if ultimo else None,
                ultimo_tentativo=tentativo.isoformat() if tentativo else None,
                prossimo_tentativo=prossimo, dati_obsoleti=obsoleti, livello=livello,
                messaggio=messaggio, azione=azione, intervallo_minuti=intervallo,
                verificato_il=ora.isoformat())


def pubblica(nomi):
    from ha_client import pubblica_diagnostica
    # Read and deliver in order: heartbeat must not overwrite a newer failure.
    with _pubblicazione_lock:
        for nome in nomi:
            try:
                pubblica_diagnostica(nome, leggi(nome))
            except Exception:
                print('[SYNC] Diagnostica HA non consegnata; riprovo al prossimo controllo')
