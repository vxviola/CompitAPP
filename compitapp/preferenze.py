"""Preferenze grafiche per studente, condivise tra dashboard e sensori HA."""
from models import get_db

PALETTE = ('salvia', 'rosa', 'azzurro')


def palette_studente(nome):
    conn = get_db()
    try:
        row = conn.execute('SELECT valore FROM meta WHERE chiave=?', ('ui_palette:' + nome,)).fetchone()
        return row['valore'] if row and row['valore'] in PALETTE else 'salvia'
    finally:
        conn.close()


def salva_palette(nome, palette):
    if palette not in PALETTE:
        raise ValueError('Stile non valido')
    conn = get_db()
    try:
        conn.execute('INSERT OR REPLACE INTO meta (chiave,valore) VALUES (?,?)', ('ui_palette:' + nome, palette))
        conn.commit()
    finally:
        conn.close()
