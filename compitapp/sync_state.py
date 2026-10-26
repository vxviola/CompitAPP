"""Stato del ciclo di sincronizzazione, persistente per studente e senza credenziali."""
import json
import threading
from datetime import datetime
from models import get_db

_lock = threading.Lock()
_in_corso = False
_errori = set()


def inizia():
    global _in_corso
    if not _lock.acquire(blocking=False):
        return False
    _in_corso = True
    _errori.clear()
    return True


def errore(nome):
    if _in_corso:
        _errori.add(nome)


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
        return dict(valore, in_corso=_in_corso)
    finally:
        conn.close()


def termina(nomi, fallito=False):
    global _in_corso
    try:
        ora = datetime.now().astimezone().isoformat(timespec='seconds')
        conn = get_db()
        try:
            for nome in nomi:
                precedente = leggi(nome)
                ok = not fallito and nome not in _errori
                dati = {'ultimo_tentativo': ora, 'esito': 'ok' if ok else 'errore',
                        'ultimo_successo': ora if ok else precedente.get('ultimo_successo')}
                conn.execute('INSERT OR REPLACE INTO meta (chiave,valore) VALUES (?,?)',
                             ('sync_ui:' + nome, json.dumps(dati)))
            conn.commit()
        finally:
            conn.close()
    finally:
        _in_corso = False
        _lock.release()
