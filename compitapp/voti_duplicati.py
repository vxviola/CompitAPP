"""Riconcilia gli identificativi equivalenti di un voto nella transazione di sync."""


def separa_identita_voti(conn, nome, uids_primari):
    """Due PK diversi presenti insieme smentiscono una precedente equivalenza."""
    if len(uids_primari) < 2:
        return
    mappa = dict(conn.execute('SELECT alias,uid FROM voti_alias WHERE studente=?', (nome,)))
    viste = set()
    conflitti = set()
    for uid in uids_primari:
        precedente = mappa.get(uid, uid)
        if precedente in viste:
            conflitti.add(precedente)
        viste.add(precedente)
    # Le vecchie associazioni di questo gruppo sono ormai ambigue. I voti e i
    # loro eventi restano intatti; il batch conferma nuovamente gli alias validi.
    conn.executemany('DELETE FROM voti_alias WHERE studente=? AND uid=?',
                     [(nome, precedente) for precedente in conflitti])


def riconcilia_identita_voto(conn, nome, uid, alias=(), primari=()):
    """Restituisce l'ID comune. Gli alias provengono da un'identità provata da Argo."""
    if not uid:
        return uid
    identificativi = {uid, *(a for a in alias if a and a not in primari)}
    parametri = ','.join('?' for _ in identificativi)
    mappa = dict(conn.execute(f'''SELECT alias, uid FROM voti_alias
        WHERE studente=? AND alias IN ({parametri})''', [nome, *identificativi]))
    if uid in primari:
        # Una vecchia associazione di un ID secondario non può riunire
        # nuovamente due PK che questa risposta documenta come distinti.
        mappa = {a: u for a, u in mappa.items() if u == uid or u not in primari}
    if len(identificativi) == 1:
        return mappa.get(uid, uid)
    # Una chiave che è già stata unificata mantiene il suo ID nelle risposte successive.
    canonico = mappa.get(uid, uid)
    identificativi.update(mappa.values())
    if all(mappa.get(a) == canonico for a in identificativi):
        return canonico

    parametri = ','.join('?' for _ in identificativi)
    args = [nome, *identificativi]
    voti = conn.execute(f'''SELECT * FROM voti WHERE studente=? AND argo_uid IN ({parametri})
        ORDER BY id''', args).fetchall()
    eventi = conn.execute(f'''SELECT uid, versione, eliminato FROM argo_eventi
        WHERE studente=? AND categoria='voti' AND uid IN ({parametri})''', args).fetchall()
    # Il registro degli eventi evita che un replay antecedente ripristini voti ritirati.
    # A parità di versione la cancellazione prevale, come nel percorso ordinario.
    versioni = {e['uid']: e['versione'] or '' for e in eventi}
    ultimo = max(eventi, key=lambda e: (e['versione'] or '', e['eliminato']), default=None)
    if ultimo and ultimo['eliminato']:
        conn.execute(f'DELETE FROM voti WHERE studente=? AND argo_uid IN ({parametri})', args)
    elif voti:
        storico = voti[0]
        recente = max(voti, key=lambda r: (versioni.get(r['argo_uid'], ''), r['argo_uid'] == canonico))
        conn.execute(f'''DELETE FROM voti WHERE studente=? AND argo_uid IN ({parametri})
            AND id<>?''', [*args, storico['id']])
        conn.execute('''UPDATE voti SET argo_uid=?, data=?, materia=?, voto=?, descrizione=?,
            notificato=? WHERE studente=? AND id=?''',
            (canonico, recente['data'], recente['materia'], recente['voto'], recente['descrizione'],
             max(r['notificato'] or 0 for r in voti), nome, storico['id']))
    if eventi:
        conn.execute(f'''DELETE FROM argo_eventi WHERE studente=? AND categoria='voti'
            AND uid IN ({parametri})''', args)
        conn.execute('''INSERT INTO argo_eventi(studente,categoria,uid,versione,eliminato)
            VALUES (?,'voti',?,?,?)''', (nome, canonico, ultimo['versione'], ultimo['eliminato']))
    conn.execute(f'UPDATE voti_alias SET uid=? WHERE studente=? AND uid IN ({parametri})',
                 [canonico, *args])
    conn.executemany('''INSERT INTO voti_alias(studente,alias,uid) VALUES (?,?,?)
        ON CONFLICT(studente,alias) DO UPDATE SET uid=excluded.uid''',
        [(nome, a, canonico) for a in identificativi])
    return canonico


def riconcilia_copia_anonima(conn, nome, uid, valori):
    """Solo dopo la conferma nello storico delle due rappresentazioni Argo."""
    if not uid:
        return False
    righe = conn.execute('''SELECT id, argo_uid, notificato FROM voti
        WHERE studente=? AND data=? AND materia=? AND voto=? AND COALESCE(descrizione,'')=?
        ORDER BY id''', (nome, valori['data'], valori['materia'], valori['voto'],
                         valori['descrizione'])).fetchall()
    if len(righe) != 2 or {r['argo_uid'] for r in righe} != {None, uid}:
        return False
    storico, copia = righe
    conn.execute('DELETE FROM voti WHERE studente=? AND id=?', (nome, copia['id']))
    conn.execute('UPDATE voti SET argo_uid=?, notificato=? WHERE studente=? AND id=?',
                 (uid, max(r['notificato'] or 0 for r in righe), nome, storico['id']))
    return True
