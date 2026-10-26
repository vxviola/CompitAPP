import sqlite3
import os

DB_PATH = os.environ.get('DB_PATH', '/data/compitapp.db')

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn

def init_db():
    conn = get_db()
    _backup_prima_eventi(conn)
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS compiti (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        studente TEXT NOT NULL DEFAULT 'default',
        data TEXT NOT NULL, materia TEXT NOT NULL, testo TEXT NOT NULL,
        notificato INTEGER DEFAULT 0,
        creato_il TEXT DEFAULT (datetime('now','localtime'))
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS voti (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        studente TEXT NOT NULL DEFAULT 'default',
        data TEXT NOT NULL, materia TEXT NOT NULL, voto TEXT NOT NULL,
        descrizione TEXT, notificato INTEGER DEFAULT 0,
        creato_il TEXT DEFAULT (datetime('now','localtime'))
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS assenze (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        studente TEXT NOT NULL DEFAULT 'default',
        data TEXT NOT NULL, tipo TEXT NOT NULL,
        descrizione TEXT, giustificata INTEGER DEFAULT 0,
        notificato INTEGER DEFAULT 0,
        creato_il TEXT DEFAULT (datetime('now','localtime'))
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS note_disciplinari (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        studente TEXT NOT NULL DEFAULT 'default',
        data TEXT NOT NULL, docente TEXT, testo TEXT,
        notificato INTEGER DEFAULT 0,
        creato_il TEXT DEFAULT (datetime('now','localtime'))
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS bacheca (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        studente TEXT NOT NULL DEFAULT 'default',
        data TEXT, titolo TEXT, testo TEXT, mittente TEXT, uid TEXT,
        allegati TEXT NOT NULL DEFAULT '[]',
        notificato INTEGER DEFAULT 0,
        creato_il TEXT DEFAULT (datetime('now','localtime')),
        UNIQUE (studente, uid)
    )''')
    _migra_bacheca(conn)

    c.execute('''CREATE TABLE IF NOT EXISTS argomenti (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        studente TEXT NOT NULL DEFAULT 'default',
        data TEXT NOT NULL, materia TEXT, argomento TEXT, attivita TEXT,
        creato_il TEXT DEFAULT (datetime('now','localtime'))
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS promemoria (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        studente TEXT NOT NULL DEFAULT 'default',
        data TEXT NOT NULL, testo TEXT, docente TEXT,
        notificato INTEGER DEFAULT 0,
        creato_il TEXT DEFAULT (datetime('now','localtime'))
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS meta (
        chiave TEXT PRIMARY KEY, valore TEXT,
        aggiornato_il TEXT DEFAULT (datetime('now','localtime'))
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS lezioni_registro (
        studente TEXT NOT NULL DEFAULT 'default',
        data TEXT NOT NULL, ora INTEGER NOT NULL,
        materia TEXT NOT NULL, docente TEXT,
        PRIMARY KEY (studente, data, ora, materia)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS orario (
        studente TEXT NOT NULL DEFAULT 'default',
        giorno INTEGER NOT NULL, ora INTEGER NOT NULL,
        materia TEXT NOT NULL, docente TEXT,
        aggiornato_il TEXT DEFAULT (datetime('now','localtime')),
        PRIMARY KEY (studente, giorno, ora)
    )''')

    _migra_eventi(conn)
    conn.commit()
    conn.close()
    print("[DB] Inizializzato correttamente")


TABELLE_EVENTI = ('compiti', 'voti', 'assenze', 'note_disciplinari', 'bacheca',
                 'argomenti', 'promemoria')


def _backup_prima_eventi(conn):
    """Una copia SQLite coerente prima di associare gli ID Argo ai dati preesistenti."""
    colonne = {r['name'] for r in conn.execute('PRAGMA table_info(compiti)')}
    if not colonne or 'argo_uid' in colonne or DB_PATH == ':memory:':
        return
    destinazione = DB_PATH + '.prima-eventi.sqlite'
    if os.path.exists(destinazione):
        return
    temporaneo = destinazione + '.tmp'
    try:
        backup = sqlite3.connect(temporaneo)
        try:
            conn.backup(backup)
        finally:
            backup.close()
        os.chmod(temporaneo, 0o600)
        os.replace(temporaneo, destinazione)
    finally:
        if os.path.exists(temporaneo):
            os.unlink(temporaneo)


def _aggiungi_colonna(conn, tabella, definizione):
    nome = definizione.split()[0]
    if nome not in {r['name'] for r in conn.execute(f'PRAGMA table_info({tabella})')}:
        conn.execute(f'ALTER TABLE {tabella} ADD COLUMN {definizione}')


def _migra_eventi(conn):
    for tabella in TABELLE_EVENTI:
        _aggiungi_colonna(conn, tabella, 'argo_uid TEXT')
        _aggiungi_colonna(conn, tabella, 'argo_gruppo TEXT')
        conn.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS ux_{tabella}_argo '
                     f'ON {tabella}(studente,argo_uid) WHERE argo_uid IS NOT NULL')
        conn.execute(f'CREATE INDEX IF NOT EXISTS ix_{tabella}_studente_data ON {tabella}(studente,data)')
    for definizione in ('completato INTEGER NOT NULL DEFAULT 0', 'completato_il TEXT'):
        _aggiungi_colonna(conn, 'compiti', definizione)
    for definizione in ('letta INTEGER NOT NULL DEFAULT 0', 'preferito INTEGER NOT NULL DEFAULT 0',
                        'promemoria_locale TEXT'):
        _aggiungi_colonna(conn, 'bacheca', definizione)
    conn.execute('''CREATE TABLE IF NOT EXISTS argo_eventi (
        studente TEXT NOT NULL, categoria TEXT NOT NULL, uid TEXT NOT NULL,
        versione TEXT, eliminato INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(studente,categoria,uid))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS registro_argo (
        studente TEXT NOT NULL, uid TEXT NOT NULL, data TEXT, ora INTEGER,
        materia TEXT, docente TEXT, PRIMARY KEY(studente,uid))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS allegati_letti (
        studente TEXT NOT NULL, messaggio_id INTEGER NOT NULL, uid TEXT NOT NULL,
        letto INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(studente,messaggio_id,uid))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS zaino_materiali (
        id INTEGER PRIMARY KEY AUTOINCREMENT, studente TEXT NOT NULL,
        materia TEXT NOT NULL DEFAULT '', testo TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS zaino_spunte (
        materiale_id INTEGER NOT NULL, data TEXT NOT NULL, fatto INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(materiale_id,data))''')


def _migra_bacheca(conn):
    """Conserva le comunicazioni esistenti e permette lo stesso avviso per più figli."""
    colonne = {r['name'] for r in conn.execute('PRAGMA table_info(bacheca)')}
    if 'allegati' not in colonne:
        conn.execute("ALTER TABLE bacheca ADD COLUMN allegati TEXT NOT NULL DEFAULT '[]'")
    uid_globale = False
    for indice in conn.execute('PRAGMA index_list(bacheca)').fetchall():
        if not indice['unique']:
            continue
        nome = indice['name'].replace('"', '""')
        campi = [r['name'] for r in conn.execute(f'PRAGMA index_info("{nome}")')]
        uid_globale |= campi == ['uid']
    if uid_globale:
        conn.execute('''CREATE TABLE bacheca_migrazione (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            studente TEXT NOT NULL DEFAULT 'default',
            data TEXT, titolo TEXT, testo TEXT, mittente TEXT, uid TEXT,
            allegati TEXT NOT NULL DEFAULT '[]', notificato INTEGER DEFAULT 0,
            creato_il TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE (studente, uid)
        )''')
        conn.execute('''INSERT INTO bacheca_migrazione
            (id,studente,data,titolo,testo,mittente,uid,allegati,notificato,creato_il)
            SELECT id,studente,data,titolo,testo,mittente,NULLIF(uid,''),allegati,notificato,creato_il
            FROM bacheca''')
        conn.execute('DROP TABLE bacheca')
        conn.execute('ALTER TABLE bacheca_migrazione RENAME TO bacheca')


def _num(v):
    """Numero da un valore Argo (8.15, "8,15", "8.15"); None se assente, non numerico o 0."""
    if v in (None, ''):
        return None
    try:
        n = round(float(str(v).replace(',', '.')), 2)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def media_argo(conn, nome):
    """Medie calcolate da Argo (salvate dallo scheduler): {'generale': float|None, 'materie': {materia: float}}.
    Sono le stesse dell'app DiDUP: escludono già i voti «non fa media». None se non disponibili."""
    import json
    r = conn.execute('SELECT valore FROM meta WHERE chiave=?', (f"media_argo:{nome}",)).fetchone()
    if not r:
        return None
    try:
        d = json.loads(r['valore'])
    except Exception:
        return None
    materie = {m: _num(v) for m, v in (d.get('materie') or {}).items()}
    materie = {m: v for m, v in materie.items() if v is not None}
    generale = _num(d.get('generale'))
    if generale is None and not materie:
        return None
    return {'generale': generale, 'materie': materie}


def svuota_studente(conn, nome):
    """Cancella tutti i dati salvati di uno studente e i segni di «storico già caricato»,
    così al prossimo giro l'anno scolastico viene riletto da capo (senza notifiche)."""
    for t in ('compiti', 'voti', 'assenze', 'note_disciplinari', 'bacheca',
              'argomenti', 'promemoria', 'orario', 'lezioni_registro', 'argo_eventi', 'registro_argo',
              'allegati_letti'):
        conn.execute(f'DELETE FROM {t} WHERE studente=?', (nome,))
    conn.execute("DELETE FROM meta WHERE chiave LIKE ? OR chiave = ? OR chiave = ?",
                 (f"storico:%:{nome}", f"media_argo:{nome}", f"sync_ui:{nome}"))
    for categoria in ('compiti', 'voti', 'assenze', 'note', 'bacheca', 'argomenti', 'promemoria', 'registro'):
        conn.execute('DELETE FROM meta WHERE chiave=?', (f'sync_eventi:v1:{categoria}:{nome}',))
