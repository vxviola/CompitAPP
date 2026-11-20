import sqlite3
import os
from math import isfinite

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
    _backup_prima_voti(conn)
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
    _crea_revisione_voti(conn)
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
    _copia_database(conn, '.prima-eventi.sqlite')


def _backup_prima_voti(conn):
    if DB_PATH == ':memory:':
        return
    colonne = {r['name'] for r in conn.execute('PRAGMA table_info(voti)')}
    if 'argo_uid' not in colonne or conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='voti_alias'").fetchone():
        return
    if conn.execute('SELECT 1 FROM voti LIMIT 1').fetchone():
        _copia_database(conn, '.prima-voti-2.4.11.sqlite')


def _copia_database(conn, suffisso):
    from tempfile import mkstemp
    destinazione = DB_PATH + suffisso
    if os.path.exists(destinazione):
        return
    fd, temporaneo = mkstemp(dir=os.path.dirname(os.path.abspath(destinazione)),
                              prefix=os.path.basename(destinazione) + '.', suffix='.tmp')
    os.close(fd)
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
                        'promemoria_locale TEXT', "url TEXT NOT NULL DEFAULT ''"):
        _aggiungi_colonna(conn, 'bacheca', definizione)
    conn.execute('''CREATE TABLE IF NOT EXISTS argo_eventi (
        studente TEXT NOT NULL, categoria TEXT NOT NULL, uid TEXT NOT NULL,
        versione TEXT, eliminato INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(studente,categoria,uid))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS voti_alias (
        studente TEXT NOT NULL, alias TEXT NOT NULL, uid TEXT NOT NULL,
        PRIMARY KEY(studente,alias))''')
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


def _crea_revisione_voti(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS voti_esclusi (
        studente TEXT NOT NULL, copia_id INTEGER NOT NULL, conserva_id INTEGER NOT NULL,
        PRIMARY KEY(studente,copia_id), CHECK(copia_id <> conserva_id))''')
    conn.execute('CREATE INDEX IF NOT EXISTS ix_voti_esclusi_conserva ON voti_esclusi(studente,conserva_id)')
    conn.execute('''CREATE VIEW IF NOT EXISTS voti_visibili AS
        SELECT v.* FROM voti v WHERE NOT EXISTS (
            SELECT 1 FROM voti_esclusi e WHERE e.studente=v.studente AND e.copia_id=v.id)''')
    # La decisione è valida per la coppia verificata. Se Argo ritira o corregge
    # una delle righe, le altre tornano subito visibili nella stessa transazione.
    annulla = '''DELETE FROM voti_esclusi WHERE studente=OLD.studente
                 AND (copia_id=OLD.id OR conserva_id=OLD.id);'''
    conn.execute(f'''CREATE TRIGGER IF NOT EXISTS voti_esclusi_ritiro AFTER DELETE ON voti
                     BEGIN {annulla} END''')
    conn.execute(f'''CREATE TRIGGER IF NOT EXISTS voti_esclusi_modifica
        AFTER UPDATE OF id,studente,data,materia,voto,descrizione,argo_uid ON voti
        WHEN NEW.id IS NOT OLD.id OR NEW.studente IS NOT OLD.studente OR NEW.data IS NOT OLD.data
          OR NEW.materia IS NOT OLD.materia OR NEW.voto IS NOT OLD.voto
          OR COALESCE(NEW.descrizione,'') <> COALESCE(OLD.descrizione,'')
          OR NEW.argo_uid IS NOT OLD.argo_uid
        BEGIN {annulla} END''')


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


def voto_numerico(v):
    """Restituisce il valore numerico positivo, oppure None per giudizi e segnaposto."""
    try:
        n = float(str(v).replace(',', '.'))
    except (TypeError, ValueError):
        return None
    return n if isfinite(n) and n > 0 else None


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
    if not isinstance(d, dict):
        return None
    valori = d.get('materie')
    materie = {m: voto_numerico(v) for m, v in valori.items()} if isinstance(valori, dict) else {}
    materie = {m: round(v, 2) for m, v in materie.items() if v is not None}
    generale = voto_numerico(d.get('generale'))
    if generale is None and not materie:
        return None
    return {'generale': round(generale, 2) if generale is not None else None, 'materie': materie}


def riepilogo_medie(conn, nome, righe=None):
    """Stesse medie per dashboard, sensori e bot. Il conteggio si riferisce ai voti numerici locali."""
    if righe is None:
        righe = conn.execute('SELECT materia, voto FROM voti_visibili WHERE studente=?', (nome,))
    valori = []
    per_materia = {}
    for riga in righe:
        numero = voto_numerico(riga['voto'])
        if numero is not None:
            valori.append(numero)
            per_materia.setdefault(riga['materia'], []).append(numero)

    ufficiali = media_argo(conn, nome) or {}
    generale = ufficiali.get('generale')
    materie_argo = ufficiali.get('materie') or {}
    materie = {m: round(sum(v) / len(v), 2) for m, v in per_materia.items()}
    materie.update(materie_argo)
    if generale is None and valori:
        generale = round(sum(valori) / len(valori), 2)
    return {
        'generale': generale,
        'materie': materie,
        'conteggi': {m: len(v) for m, v in per_materia.items()},
        'generale_argo': ufficiali.get('generale') is not None,
        'materie_argo': set(materie_argo),
        'fonti_miste': bool(materie_argo and per_materia.keys() - materie_argo.keys()),
    }


def svuota_studente(conn, nome):
    """Cancella tutti i dati salvati di uno studente e i segni di «storico già caricato»,
    così al prossimo giro l'anno scolastico viene riletto da capo (senza notifiche)."""
    for t in ('compiti', 'voti', 'assenze', 'note_disciplinari', 'bacheca',
              'argomenti', 'promemoria', 'orario', 'lezioni_registro', 'argo_eventi', 'registro_argo',
              'allegati_letti', 'voti_alias', 'voti_esclusi'):
        conn.execute(f'DELETE FROM {t} WHERE studente=?', (nome,))
    chiavi = [f'media_argo:{nome}', f'sync_ui:{nome}', f'storico:bacheca_allegati:{nome}']
    for categoria in ('compiti', 'voti', 'assenze', 'note', 'bacheca', 'argomenti', 'promemoria', 'registro'):
        chiavi.extend((f'storico:{categoria}:{nome}', f'sync_eventi:v1:{categoria}:{nome}'))
    conn.executemany('DELETE FROM meta WHERE chiave=?', [(chiave,) for chiave in chiavi])
