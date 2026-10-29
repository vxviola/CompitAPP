"""Stato del ciclo di sincronizzazione, persistente per studente e senza credenziali."""
import json
import threading
from datetime import datetime
from models import get_db

_lock = threading.Lock()
_in_corso = False
_errori = {}


def inizia():
    global _in_corso
    if not _lock.acquire(blocking=False):
        return False
    _in_corso = True
    _errori.clear()
    return True


def errore(nome, motivo="sincronizzazione"):
    if _in_corso:
        _errori[nome] = "accesso" if motivo == "accesso" or _errori.get(nome) == "accesso" else "sincronizzazione"


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
        return dict(valore, in_corso=_in_corso)
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
