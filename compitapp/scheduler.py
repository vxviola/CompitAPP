import os
import threading
import sync_state
from datetime import date, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from argo_client import get_studenti
from models import get_db, media_argo
from notifier import reminder_compiti_domani, sync_sensori_ha

TZ = pytz.timezone('Europe/Rome')
ORARIO_REMINDER = os.environ.get('ORARIO_REMINDER', '20:00')
POLLING_MINUTI = int(os.environ.get('POLLING_MINUTI', 30))

def _sincronizza_categoria(categoria):
    from sync_argo import sincronizza
    return sincronizza(get_studenti(), (categoria,))


def sync_compiti(): return _sincronizza_categoria('compiti')
def sync_voti(): return _sincronizza_categoria('voti')
def sync_assenze(): return _sincronizza_categoria('assenze')
def sync_note(): return _sincronizza_categoria('note')
def sync_bacheca(): return _sincronizza_categoria('bacheca')
def sync_argomenti(): return _sincronizza_categoria('argomenti')
def sync_promemoria(): return _sincronizza_categoria('promemoria')


def sync_orario():
    """Ricostruisce l'orario dalle lezioni già verificate nel ciclo corrente."""
    from orario_utils import ricostruisci_orario
    for studente in get_studenti():
        nome = studente.get('nome', 'Studente')
        conn = get_db()
        try:
            storico = conn.execute('SELECT data,ora,materia,docente FROM lezioni_registro WHERE studente=?', (nome,)).fetchall()
            slot = ricostruisci_orario([{'datGiorno': r['data'], 'ora': r['ora'], 'materia': r['materia'], 'docente': r['docente']} for r in storico])
            if slot or not storico:
                conn.execute('DELETE FROM orario WHERE studente=?', (nome,))
                conn.executemany('INSERT INTO orario(studente,giorno,ora,materia,docente) VALUES (?,?,?,?,?)',
                                 [(nome, r['giorno'], r['ora'], r['materia'], r['docente']) for r in slot])
                conn.commit()
        except Exception:
            conn.rollback()
            sync_state.errore(nome)
            print(f'[SYNC] {nome}: orario non aggiornato')
        finally:
            conn.close()


def sync_tutto():
    """Sync completo di tutto"""
    if not sync_state.inizia():
        return False
    return _esegui_sync()


def avvia_sync_manuale():
    if not sync_state.inizia():
        return False
    try:
        threading.Thread(target=_esegui_sync, daemon=True, name='sync-manuale').start()
    except Exception:
        sync_state.termina([s.get('nome', 'Studente') for s in get_studenti()], fallito=True)
        raise
    return True


def _esegui_sync():
    nomi = [s.get('nome', 'Studente') for s in get_studenti()]
    fallito = False
    try:
        _ciclo_sync()
    except Exception:
        fallito = True
        print('[SCHEDULER] Sincronizzazione interrotta: controllare connessione e configurazione')
    finally:
        sync_state.termina(nomi, fallito=fallito)
    return not fallito


def _ciclo_sync():
    from sync_argo import sincronizza
    sincronizza(get_studenti())
    sync_orario()
    for studente in get_studenti():
        _aggiorna_sensori(studente.get('nome', 'Studente'))
    import ha_client
    ha_client.promemoria_documenti(get_studenti())


def _giorni_scuola(conn, nome):
    """Giorni della settimana (0=lun … 6=dom) con lezione, ricavati dall'orario ricostruito.
    Se l'orario non c'è ancora si assume lunedì-venerdì."""
    giorni = {r['giorno'] for r in conn.execute('SELECT DISTINCT giorno FROM orario WHERE studente=?', (nome,)).fetchall()}
    return giorni or {0, 1, 2, 3, 4}

def reminder_sera():
    print("[SCHEDULER] Reminder serale")
    domani_data = date.today() + timedelta(days=1)
    domani = domani_data.strftime('%Y-%m-%d')
    for studente in get_studenti():
        nome = studente.get('nome', 'Studente')
        try:
            conn = get_db()
            rows = conn.execute('SELECT materia, testo FROM compiti WHERE studente=? AND data=? ORDER BY materia', (nome, domani)).fetchall()
            domani_scuola = domani_data.weekday() in _giorni_scuola(conn, nome)
            orario_domani = [(r['ora'], r['materia']) for r in conn.execute(
                'SELECT ora, materia FROM orario WHERE studente=? AND giorno=? ORDER BY ora',
                (nome, domani_data.weekday())).fetchall()]
            conn.close()
            compiti_domani = {'materie':[r['materia'] for r in rows], 'compiti':[r['testo'] for r in rows]} if rows else None
            reminder_compiti_domani(nome, compiti_domani, domani_scuola=domani_scuola, orario_domani=orario_domani)
        except Exception as e:
            print(f"[SCHEDULER] Errore reminder {nome}: {e}")

def _taglia(s, n=400):
    s = str(s or '').strip()
    return s if len(s) <= n else s[:n - 1] + '…'


def _dettagli_sensori(conn, nome, oggi, domani):
    """Elenchi per il popup della card (attributo `elenco` dei sensori). Tenuti corti:
    Home Assistant sconsiglia attributi molto grandi."""
    def compiti(giorno):
        return [{'materia': r['materia'], 'testo': _taglia(r['testo']), 'completato': bool(r['completato'])} for r in conn.execute(
            'SELECT materia, testo, completato FROM compiti WHERE studente=? AND data=? ORDER BY materia', (nome, giorno))]
    voti = [{'data': r['data'], 'materia': r['materia'], 'voto': r['voto'], 'descrizione': _taglia(r['descrizione'], 150)}
            for r in conn.execute(
                "SELECT data, materia, voto, descrizione FROM voti WHERE studente=? "
                "AND voto NOT IN ('0','0.0','0,0','N','') ORDER BY data DESC, id DESC LIMIT 15", (nome,))]
    per_materia = {}
    for r in conn.execute("SELECT materia, voto FROM voti WHERE studente=? AND voto NOT IN ('0','0.0','0,0','N','')", (nome,)):
        try:
            per_materia.setdefault(r['materia'], []).append(float(str(r['voto']).replace(',', '.')))
        except Exception:
            pass
    medie = sorted(({'materia': m, 'media': round(sum(v) / len(v), 2), 'n': len(v)} for m, v in per_materia.items()),
                   key=lambda x: x['materia'])
    assenze = [{'data': r['data'], 'tipo': r['tipo'], 'descrizione': _taglia(r['descrizione'], 150),
                'giustificata': bool(r['giustificata'])} for r in conn.execute(
                'SELECT data, tipo, descrizione, giustificata FROM assenze WHERE studente=? ORDER BY data DESC, id DESC LIMIT 20', (nome,))]
    bacheca = [{'data': r['data'], 'titolo': _taglia(r['titolo'], 120), 'mittente': r['mittente'] or '',
                'testo': _taglia(r['testo'], 500)} for r in conn.execute(
                'SELECT data, titolo, testo, mittente FROM bacheca WHERE studente=? ORDER BY data DESC, id DESC LIMIT 8', (nome,))]
    return {'compiti_oggi': compiti(oggi), 'compiti_domani': compiti(domani), 'voti': voti,
            'medie': medie, 'assenze': assenze, 'bacheca': bacheca}


def _aggiorna_sensori(nome):
    try:
        oggi = date.today().strftime('%Y-%m-%d')
        domani = (date.today() + timedelta(days=1)).strftime('%Y-%m-%d')
        conn = get_db()
        n_oggi   = conn.execute('SELECT COUNT(*) as n FROM compiti WHERE studente=? AND data=?', (nome, oggi)).fetchone()['n']
        n_domani = conn.execute('SELECT COUNT(*) as n FROM compiti WHERE studente=? AND data=?', (nome, domani)).fetchone()['n']
        n_assenze = conn.execute('SELECT COUNT(*) as n FROM assenze WHERE studente=?', (nome,)).fetchone()['n']
        n_bacheca = conn.execute('SELECT COUNT(*) as n FROM bacheca WHERE studente=? AND data>=?', (nome, (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))).fetchone()['n']
        ultimo_voto = conn.execute("SELECT voto, materia FROM voti WHERE studente=? AND voto NOT IN ('0','0.0','0,0','N','') ORDER BY data DESC, id DESC LIMIT 1", (nome,)).fetchone()
        tutti_voti = conn.execute("SELECT voto FROM voti WHERE studente=? AND voto NOT IN ('0','0.0','0,0','N','')", (nome,)).fetchall()
        dettagli = _dettagli_sensori(conn, nome, oggi, domani)
        ma = media_argo(conn, nome)
        conn.close()
        valori = []
        for v in tutti_voti:
            try:
                valori.append(float(str(v['voto']).replace(',','.')))
            except Exception:
                pass
        media = round(sum(valori)/len(valori), 2) if valori else 'N/D'
        if ma and ma['generale'] is not None:
            media = ma['generale']
        if ma and ma['materie']:
            conteggi = {m['materia']: m['n'] for m in dettagli.get('medie', [])}
            dettagli['medie'] = sorted(({'materia': m, 'media': v, 'n': conteggi.get(m, 0)}
                                        for m, v in ma['materie'].items()), key=lambda x: x['materia'])
        sync_sensori_ha(nome, {
            'compiti_oggi': n_oggi, 'compiti_domani': n_domani,
            'assenze_totali': n_assenze, 'bacheca_non_lette': n_bacheca,
            'ultimo_voto': ultimo_voto['voto'] if ultimo_voto else 'N/D',
            'ultima_materia': ultimo_voto['materia'] if ultimo_voto else '',
            'media_voti': media,
            'dettagli': dettagli
        })
    except Exception as e:
        print(f"[SCHEDULER] Errore sensori {nome}: {e}")

def heartbeat():
    """Log ogni 5 minuti per verificare che lo scheduler giri"""
    from datetime import datetime
    print(f"[SCHEDULER] ❤️ Heartbeat — {datetime.now().strftime('%H:%M:%S')}")

def avvia_scheduler():
    scheduler = BackgroundScheduler(timezone=TZ)
    scheduler.add_job(sync_tutto, 'interval', minutes=POLLING_MINUTI, id='sync_tutto')
    scheduler.add_job(heartbeat, 'interval', minutes=5, id='heartbeat')
    try:
        ora, minuto = ORARIO_REMINDER.split(':')
        scheduler.add_job(reminder_sera, CronTrigger(hour=int(ora), minute=int(minuto)), id='reminder_sera')
    except Exception:
        scheduler.add_job(reminder_sera, CronTrigger(hour=20, minute=0), id='reminder_sera')
    scheduler.start()
    print(f"[SCHEDULER] Avviato — polling ogni {POLLING_MINUTI} min, reminder alle {ORARIO_REMINDER}")
    sync_tutto()
    return scheduler
