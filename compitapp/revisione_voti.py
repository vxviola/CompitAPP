"""Confronto e correzioni locali reversibili dei voti con campi visibili identici."""
from hashlib import sha256
from itertools import groupby
import json


class RevisioneObsoleta(ValueError):
    """La coppia selezionata non corrisponde più al gruppo mostrato."""


def gruppi_voti(conn, nome):
    righe = conn.execute('''SELECT v.data, v.materia, v.voto, COALESCE(v.descrizione,'') AS descrizione,
            v.id, v.argo_uid, v.creato_il, e.conserva_id FROM voti v
            LEFT JOIN voti_esclusi e ON e.studente=v.studente AND e.copia_id=v.id
            WHERE v.studente=?
            ORDER BY v.data DESC, v.materia, v.voto, COALESCE(v.descrizione,''), v.id''', (nome,))
    gruppi = []
    campi = ('data', 'materia', 'voto', 'descrizione')
    for firma, uguali in groupby(righe, key=lambda r: tuple(r[k] for k in campi)):
        copie = list(uguali)
        if len(copie) < 2:
            continue
        # La versione lega la scelta a studente, contenuto, identità e decisioni
        # correnti. Gli identificativi di Argo restano nel processo del server.
        stato = [(r['id'], r['argo_uid'], r['conserva_id']) for r in copie]
        versione = sha256(json.dumps([nome, firma, stato], separators=(',', ':')).encode()).hexdigest()
        gruppi.append(dict(zip(campi, firma), versione=versione, righe=[
            {'id': r['id'], 'collegato': bool(r['argo_uid']), 'creato_il': r['creato_il'],
             'esclusa': r['conserva_id'] is not None, 'conserva_id': r['conserva_id']} for r in copie]))
    return gruppi


def _righe_correnti(conn, nome, versione):
    for gruppo in gruppi_voti(conn, nome):
        if gruppo['versione'] == versione:
            return {r['id']: r for r in gruppo['righe']}
    raise RevisioneObsoleta('Il gruppo è cambiato. Ricarica il confronto.')


def escludi_copia(conn, nome, copia_id, conserva_id, versione):
    """Esclude una copia, lasciando i dati Argo disponibili per la sincronizzazione."""
    with conn:
        conn.execute('BEGIN IMMEDIATE')
        righe = _righe_correnti(conn, nome, versione)
        if (type(copia_id) is not int or type(conserva_id) is not int or copia_id == conserva_id
                or copia_id not in righe or conserva_id not in righe
                or righe[copia_id]['esclusa'] or righe[conserva_id]['esclusa']):
            raise RevisioneObsoleta('Scegli due voti visibili dello stesso gruppo.')
        # Se la copia era il riferimento per altre righe uguali, queste restano
        # collegate direttamente alla riga visibile scelta, anche nei gruppi di 3+.
        conn.execute('UPDATE voti_esclusi SET conserva_id=? WHERE studente=? AND conserva_id=?',
                     (conserva_id, nome, copia_id))
        conn.execute('INSERT INTO voti_esclusi(studente,copia_id,conserva_id) VALUES (?,?,?)',
                     (nome, copia_id, conserva_id))


def ripristina_copia(conn, nome, copia_id, versione):
    with conn:
        conn.execute('BEGIN IMMEDIATE')
        righe = _righe_correnti(conn, nome, versione)
        if type(copia_id) is not int or copia_id not in righe or not righe[copia_id]['esclusa']:
            raise RevisioneObsoleta('La copia selezionata è già visibile o il gruppo è cambiato.')
        conn.execute('DELETE FROM voti_esclusi WHERE studente=? AND copia_id=?', (nome, copia_id))
