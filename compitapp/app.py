import sys
import os
import json
from urllib.parse import urlencode
from flask import Flask, render_template, jsonify, request, send_file, abort, send_from_directory
from datetime import date, timedelta
from models import init_db, get_db, media_argo
from argo_client import get_studenti, link_allegato_bacheca
from allegati import leggi_allegati, nome_download, scarica_file, tipo_file
from orario_utils import GIORNI, anno_scolastico, stile_materia, etichetta_breve

# Redirect errori su stdout per vederli nei log HA
from scheduler import avvia_scheduler
from bot import avvia_bot

app = Flask(__name__)
from funzioni import bp as funzioni_bp
app.register_blueprint(funzioni_bp)

from ui import contesto_ui, data_leggibile, base_ingress
import sync_state
app.jinja_env.filters['data_breve'] = data_leggibile


@app.context_processor
def ui_context():
    studenti = get_studenti()
    return contesto_ui(studenti, sync_state.leggi(_sel(studenti)))


@app.route('/<path:prefix>/static/<path:filename>')
def ingress_static(prefix, filename):
    return send_from_directory(app.static_folder, filename)

def _maschera_token(token):
    """Mostra solo i primi 10 caratteri del token"""
    if not token:
        return ''
    if ':' in token:
        parts = token.split(':')
        return parts[0] + ':' + '*' * len(parts[1])
    return token[:6] + '*' * (len(token) - 6)

def _sel(studenti):
    nomi = [s['nome'] for s in studenti]
    scelto = request.args.get('studente')
    return scelto if scelto in nomi else (nomi[0] if nomi else '')

def _media(voti):
    valori = []
    for v in voti:
        try:
            valori.append(float(str(v['voto']).replace(',','.')))
        except Exception:
            pass
    return round(sum(valori)/len(valori), 2) if valori else None

@app.route('/healthz')
@app.route('/health')
def healthz():
    return 'OK', 200

@app.route('/debug-headers')
def debug_headers():
    headers = dict(request.headers)
    env_keys = ['PATH_INFO', 'SCRIPT_NAME', 'HTTP_X_INGRESS_PATH', 
                'HTTP_X_FORWARDED_PREFIX', 'HTTP_X_REAL_IP']
    env_info = {k: request.environ.get(k, 'N/A') for k in env_keys}
    return jsonify({
        'headers': headers,
        'environ': env_info,
        'path': request.path,
        'script_root': request.script_root,
        'url': request.url
    })



@app.route('/')
def index():
    print(f"[FLASK] PATH: {request.path} | SCRIPT_ROOT: {request.script_root} | FULL: {request.url}")
    studenti = get_studenti()
    sel = _sel(studenti)
    oggi = date.today().strftime('%Y-%m-%d')
    domani = (date.today() + timedelta(days=1)).strftime('%Y-%m-%d')
    conn = get_db()
    compiti_oggi   = conn.execute('SELECT * FROM compiti WHERE studente=? AND data=? ORDER BY materia', (sel, oggi)).fetchall()
    compiti_domani = conn.execute('SELECT * FROM compiti WHERE studente=? AND data=? ORDER BY materia', (sel, domani)).fetchall()
    prossimi       = conn.execute('SELECT * FROM compiti WHERE studente=? AND data>? ORDER BY data,materia LIMIT 30', (sel, domani)).fetchall()
    ultimi_voti    = conn.execute('SELECT * FROM voti WHERE studente=? ORDER BY data DESC, id DESC LIMIT 5', (sel,)).fetchall()
    tutti_voti     = conn.execute('SELECT voto FROM voti WHERE studente=?', (sel,)).fetchall()
    bacheca        = conn.execute('SELECT * FROM bacheca WHERE studente=? ORDER BY data DESC,id DESC LIMIT 3', (sel,)).fetchall()
    promemoria     = conn.execute('SELECT * FROM promemoria WHERE studente=? AND data>=? ORDER BY data', (sel, oggi)).fetchall()
    assenze_tot    = conn.execute("SELECT COUNT(*) as n FROM assenze WHERE studente=? AND tipo='A'", (sel,)).fetchone()['n']
    ma             = media_argo(conn, sel)
    orario_domani  = conn.execute('SELECT * FROM orario WHERE studente=? AND giorno=? ORDER BY ora',
                                 (sel, (date.today() + timedelta(days=1)).weekday())).fetchall()
    conn.close()
    bacheca = [dict(m, allegati=leggi_allegati(m['allegati'])) for m in bacheca]
    tutti_voti     = [v for v in tutti_voti if str(v['voto']).strip() not in ('0', '0.0', '0,0', 'N', '')]
    media          = ma['generale'] if ma and ma['generale'] is not None else _media(tutti_voti)
    return render_template('index.html',
        studenti=studenti, studente_sel=sel,
        compiti_oggi=compiti_oggi, compiti_domani=compiti_domani,
        prossimi=prossimi, ultimi_voti=ultimi_voti,
        bacheca=bacheca, promemoria=promemoria, assenze_mese=assenze_tot,
        media=media, oggi=oggi, domani=domani, orario_domani=orario_domani,
        soglia_voto=float(os.environ.get('SOGLIA_VOTO', 7))
    )

@app.route('/calendario')
def calendario():
    studenti = get_studenti()
    sel = _sel(studenti)
    da = (date.today() - timedelta(days=60)).strftime('%Y-%m-%d')
    a  = (date.today() + timedelta(days=30)).strftime('%Y-%m-%d')
    conn = get_db()
    compiti = conn.execute('SELECT * FROM compiti WHERE studente=? AND data BETWEEN ? AND ? ORDER BY data,materia', (sel, da, a)).fetchall()
    conn.close()
    return render_template('calendario.html', compiti=compiti, studenti=studenti,
        studente_sel=sel, oggi=date.today().strftime('%Y-%m-%d'))

@app.route('/voti')
def voti():
    studenti = get_studenti()
    sel = _sel(studenti)
    conn = get_db()
    tutti_voti = conn.execute('SELECT * FROM voti WHERE studente=? ORDER BY data DESC', (sel,)).fetchall()
    ma = media_argo(conn, sel)
    conn.close()
    medie = {}
    per_materia = {}
    for v in tutti_voti:
        try:
            per_materia.setdefault(v['materia'], []).append(float(str(v['voto']).replace(',','.')))
        except Exception:
            pass
    for m, vals in per_materia.items():
        medie[m] = round(sum(vals)/len(vals), 2)
    if ma and ma['materie']:
        medie = dict(ma['materie'])
    return render_template('voti.html', voti=tutti_voti, medie=medie,
        soglia=float(os.environ.get('SOGLIA_VOTO', 7)),
        studenti=studenti, studente_sel=sel)

@app.route('/bacheca')
def bacheca():
    studenti = get_studenti()
    sel = _sel(studenti)
    conn = get_db()
    msgs = conn.execute('SELECT * FROM bacheca WHERE studente=? ORDER BY data DESC', (sel,)).fetchall()
    letti = {(r['messaggio_id'], r['uid']): bool(r['letto']) for r in conn.execute(
        'SELECT messaggio_id,uid,letto FROM allegati_letti WHERE studente=?', (sel,))}
    conn.close()
    msgs = [dict(msg, allegati=leggi_allegati(msg['allegati'])) for msg in msgs]
    for msg in msgs:
        for allegato in msg['allegati']:
            allegato['letto'] = letti.get((msg['id'], allegato['uid']), False)
        msg['da_leggere'] = not msg['letta'] or any(not a['letto'] for a in msg['allegati'])
    return render_template('bacheca.html', messaggi=msgs, studenti=studenti, studente_sel=sel)

@app.route('/bacheca/<int:messaggio_id>/allegati/<int:indice>')
@app.route('/<path:prefix>/bacheca/<int:messaggio_id>/allegati/<int:indice>')
def download_allegato(messaggio_id, indice, prefix=None):
    studenti = get_studenti()
    sel = request.args.get('studente', '')
    studente = next((s for s in studenti if s['nome'] == sel), None)
    if studente is None:
        abort(404)
    conn = get_db()
    try:
        msg = conn.execute('SELECT allegati FROM bacheca WHERE id=? AND studente=?',
                           (messaggio_id, sel)).fetchone()
    finally:
        conn.close()
    allegati = leggi_allegati(msg['allegati']) if msg else []
    if indice >= len(allegati):
        abort(404)
    allegato = allegati[indice]
    try:
        url = link_allegato_bacheca(studente, allegato)
        file = scarica_file(url)
    except Exception:
        # Le eccezioni HTTP possono contenere URL firmati: non inserirle nei log.
        bacheca_url = base_ingress() + '/bacheca?' + urlencode({'studente': sel})
        return render_template('errore_allegato.html', studenti=studenti,
                               studente_sel=sel, bacheca_url=bacheca_url), 502
    risposta = send_file(file, as_attachment=True,
                         download_name=nome_download(allegato.get('nome')),
                         mimetype=tipo_file(file, allegato.get('nome')), max_age=0)
    risposta.headers['Cache-Control'] = 'private, no-store'
    risposta.headers['X-Content-Type-Options'] = 'nosniff'
    risposta.call_on_close(file.close)
    return risposta

@app.route('/assenze')
def assenze():
    studenti = get_studenti()
    sel = _sel(studenti)
    conn = get_db()
    assenze_list = conn.execute('SELECT * FROM assenze WHERE studente=? ORDER BY data DESC', (sel,)).fetchall()
    stats = {
        'assenze': conn.execute("SELECT COUNT(*) as n FROM assenze WHERE studente=? AND tipo='A'", (sel,)).fetchone()['n'],
        'ritardi': conn.execute("SELECT COUNT(*) as n FROM assenze WHERE studente=? AND tipo='R'", (sel,)).fetchone()['n'],
        'uscite':  conn.execute("SELECT COUNT(*) as n FROM assenze WHERE studente=? AND tipo='U'", (sel,)).fetchone()['n'],
    }
    conn.close()
    return render_template('assenze.html', assenze=assenze_list, stats=stats,
        studenti=studenti, studente_sel=sel)

@app.route('/argomenti')
def argomenti():
    studenti = get_studenti()
    sel = _sel(studenti)
    da = (date.today() - timedelta(days=30)).strftime('%Y-%m-%d')
    conn = get_db()
    args = conn.execute('SELECT * FROM argomenti WHERE studente=? AND data>=? ORDER BY data DESC, materia', (sel, da)).fetchall()
    conn.close()
    return render_template('argomenti.html', argomenti=args, studenti=studenti, studente_sel=sel)

@app.route('/orario')
def orario():
    studenti = get_studenti()
    sel = _sel(studenti)
    giorno_oggi = date.today().weekday() + 1
    if giorno_oggi > 6:
        giorno_oggi = 0

    conn = get_db()
    righe = conn.execute(
        'SELECT giorno, ora, materia, docente, aggiornato_il FROM orario '
        'WHERE studente=? ORDER BY giorno, ora', (sel,)
    ).fetchall()
    conn.close()

    per_giorno = {g[0]: [] for g in GIORNI}
    tabella = {}
    for r in righe:
        if r['giorno'] not in per_giorno:
            continue
        slot = {
            'ora': r['ora'], 'materia': r['materia'], 'docente': r['docente'] or '',
            'breve': etichetta_breve(r['materia']), 'stile': stile_materia(r['materia']),
        }
        per_giorno[r['giorno']].append(slot)
        tabella[(r['ora'], r['giorno'])] = slot
    giorni_vis = [g for g in GIORNI if g[0] < 5 or per_giorno[g[0]]]
    max_ora = max([r['ora'] for r in righe], default=0)
    aggiornato = max([r['aggiornato_il'] for r in righe if r['aggiornato_il']], default='')

    return render_template('orario.html', giorno_oggi=giorno_oggi,
        anno_scolastico=anno_scolastico(),
        nome_studente=(sel.split()[0] if sel else 'Studente'),
        giorni=giorni_vis, per_giorno=per_giorno, tabella=tabella,
        ore=range(1, max_ora + 1), ha_orario=bool(righe), aggiornato=aggiornato,
        studenti=studenti, studente_sel=sel)

@app.route('/configurazione')
def configurazione():
    studenti = get_studenti()
    sel = _sel(studenti)
    
    # Parsing chat_ids
    raw = os.environ.get('TELEGRAM_CHAT_IDS','')
    ids = [x.strip() for x in raw.replace('\n',',').split(',') if x.strip()]
    from notifier import get_studente_chat_id
    studente_chat = get_studente_chat_id(sel)
    
    # Trova credenziali studente selezionato
    cred = next((s for s in studenti if s['nome'] == sel), {})
    
    spid = None
    if cred.get('accesso') == 'spid':
        import spid_auth
        spid = spid_auth.stato(sel)
    cfg = {
        'spid': spid,
        'connesso': len(studenti) > 0 and bool(cred.get('codice_scuola')) and (not spid or spid['stato'] == 'collegato'),
        'username': cred.get('username',''),
        'codice_scuola': cred.get('codice_scuola',''),
        'genitore1_nome': os.environ.get('GENITORE1_NOME', 'Genitore 1'),
        'genitore1': os.environ.get('GENITORE1_CHAT_ID', ''),
        'genitore2_nome': os.environ.get('GENITORE2_NOME', 'Genitore 2'),
        'genitore2': os.environ.get('GENITORE2_CHAT_ID', ''),
        'studente_nome': (sel.split()[0] if sel else os.environ.get('STUDENTE_NOME', 'Studente')),
        'studente_chat_id': studente_chat,
        'totale_destinatari': len(ids) + (1 if studente_chat else 0),
        'soglia_voto': os.environ.get('SOGLIA_VOTO', 7),
        'orario_reminder': os.environ.get('ORARIO_REMINDER', '20:00'),
        'polling_minuti': os.environ.get('POLLING_MINUTI', 30),
        'token_masked': _maschera_token(os.environ.get('TELEGRAM_TOKEN', '')),
    }
    import ha_client
    cfg['ha_notify'] = ha_client.configurazione(sel)
    return render_template('configurazione.html', config=cfg, studenti=studenti, studente_sel=sel)

# ── API ──────────────────────────────────────────────────────────────────────

@app.route('/api/palette', methods=['POST'])
@app.route('/<path:prefix>/api/palette', methods=['POST'])
def api_palette(prefix=None):
    from preferenze import PALETTE, salva_palette
    nome = request.args.get('studente', '')
    if nome not in [s['nome'] for s in get_studenti()]:
        abort(404)
    payload = request.get_json(silent=True)
    palette = payload.get('palette') if isinstance(payload, dict) else None
    if palette not in PALETTE:
        return jsonify({'ok': False, 'errore': 'Scegli Salvia, Rosa o Azzurro.'}), 400
    salva_palette(nome, palette)
    return jsonify({'ok': True, 'palette': palette})

@app.route('/api/sync', methods=['POST'])
def api_sync():
    from scheduler import avvia_sync_manuale
    if not get_studenti():
        return jsonify({'ok': False, 'errore': 'Configura almeno uno studente nelle opzioni dell’app.'}), 400
    if not avvia_sync_manuale():
        return jsonify({'ok': False, 'errore': 'Una sincronizzazione è già in corso.'}), 409
    return jsonify({'ok': True, 'in_corso': True}), 202


@app.route('/api/sync-status')
@app.route('/<path:prefix>/api/sync-status')
def api_sync_status(prefix=None):
    return jsonify(sync_state.leggi(_sel(get_studenti())))

@app.route('/api/test-connessione', methods=['POST'])
def api_test_connessione():
    try:
        from argo_client import get_session, _reset_session
        studenti = get_studenti()
        if not studenti:
            return jsonify({'ok': False, 'errore': 'Nessuno studente configurato'})
        nome = _sel(studenti)
        studente = next(s for s in studenti if s['nome'] == nome)
        _reset_session(nome)
        if get_session(studente) is None:
            return jsonify({'ok': False, 'errore': 'Accesso Argo non riuscito. Controlla configurazione e log.'})
        return jsonify({'ok': True})
    except Exception:
        return jsonify({'ok': False, 'errore': 'Verifica Argo non riuscita. Riprova più tardi.'})

# ── SPID ─────────────────────────────────────────────────────────────────────

@app.route('/api/spid/<azione>', methods=['POST'])
@app.route('/<path:prefix>/api/spid/<azione>', methods=['POST'])
def api_spid(azione, prefix=None):
    """link / collega / stato per l'accesso con SPID (sperimentale)."""
    import spid_auth
    dati = request.get_json(silent=True) or {}
    nome = dati.get('studente', '')
    if nome not in [s['nome'] for s in get_studenti() if s.get('accesso') == 'spid']:
        return jsonify({'ok': False, 'errore': 'Studente non configurato con accesso SPID'}), 400
    if azione == 'link':
        return jsonify({'ok': True, 'link': spid_auth.genera_link(nome)})
    if azione == 'collega':
        ok, msg = spid_auth.collega(nome, dati.get('testo', ''))
        if ok:
            from argo_client import _reset_session
            _reset_session(nome)
        return jsonify({'ok': ok, 'messaggio': msg, 'stato': spid_auth.stato(nome)})
    if azione == 'stato':
        return jsonify({'ok': True, 'stato': spid_auth.stato(nome)})
    return jsonify({'ok': False, 'errore': 'Azione sconosciuta'}), 404

@app.route('/api/test-telegram', methods=['POST'])
def api_test_telegram():
    from notifier import send_telegram_to
    data = request.get_json()
    chat_id = data.get('chat_id','')
    nome = data.get('nome','utente')
    if not chat_id:
        return jsonify({'ok': False})
    ok = send_telegram_to(chat_id, f"🧪 <b>UniScuola — Test notifica</b>\n✅ Tutto funziona!\nMessaggio per <b>{nome}</b>.")
    return jsonify({'ok': ok})

@app.route('/api/test-broadcast', methods=['POST'])
def api_test_broadcast():
    from notifier import send_telegram
    ok = send_telegram("🧪 <b>UniScuola — Test broadcast</b>\n✅ Tutti i destinatari ricevono correttamente!")
    ids = [x.strip() for x in os.environ.get('TELEGRAM_CHAT_IDS','').replace('\n',',').split(',') if x.strip()]
    from notifier import get_studente_chat_id
    n = len(ids) + sum(1 for s in get_studenti() if get_studente_chat_id(s['nome']))
    return jsonify({'ok': ok, 'n': n})

@app.route('/api/reset-db', methods=['POST'])
def api_reset_db():
    if not sync_state.inizia_manutenzione():
        return jsonify({'ok': False, 'errore': 'Attendi la fine della sincronizzazione prima di azzerare i dati.'}), 409
    conn = None
    try:
        conn = get_db()
        for tabella in ['compiti','voti','assenze','note_disciplinari','bacheca','argomenti','promemoria','orario','lezioni_registro','argo_eventi','registro_argo','allegati_letti']:
            conn.execute(f'DELETE FROM {tabella}')
        # senza questo, dopo lo svuotamento l'app rileggeva solo gli ultimi 7 giorni
        conn.execute("DELETE FROM meta WHERE chiave LIKE 'storico:%' OR chiave LIKE 'media_argo:%' OR chiave LIKE 'sync_ui:%'")
        conn.execute("DELETE FROM meta WHERE chiave LIKE 'sync_eventi:%'")
        conn.commit()
        return jsonify({'ok': True})
    except Exception:
        if conn:
            conn.rollback()
        return jsonify({'ok': False, 'errore': 'Azzeramento non riuscito: dati conservati.'}), 500
    finally:
        if conn:
            conn.close()
        sync_state.termina_manutenzione()

@app.route('/api/stats')
def api_stats():
    sel = request.args.get('studente', '')
    oggi = date.today().strftime('%Y-%m-%d')
    domani = (date.today() + timedelta(days=1)).strftime('%Y-%m-%d')
    conn = get_db()
    n_oggi     = conn.execute('SELECT COUNT(*) as n FROM compiti WHERE studente=? AND data=?', (sel, oggi)).fetchone()['n']
    n_domani   = conn.execute('SELECT COUNT(*) as n FROM compiti WHERE studente=? AND data=?', (sel, domani)).fetchone()['n']
    tot_comp   = conn.execute('SELECT COUNT(*) as n FROM compiti WHERE studente=?', (sel,)).fetchone()['n']
    tot_voti   = conn.execute('SELECT COUNT(*) as n FROM voti WHERE studente=?', (sel,)).fetchone()['n']
    tot_ass    = conn.execute('SELECT COUNT(*) as n FROM assenze WHERE studente=?', (sel,)).fetchone()['n']
    tot_bach   = conn.execute('SELECT COUNT(*) as n FROM bacheca WHERE studente=?', (sel,)).fetchone()['n']
    conn.close()
    return jsonify({
        'compiti_oggi': n_oggi, 'compiti_domani': n_domani,
        'totale_compiti': tot_comp, 'totale_voti': tot_voti,
        'totale_assenze': tot_ass, 'totale_bacheca': tot_bach,
        'ultimo_sync': sync_state.leggi(sel).get('ultimo_successo') or 'In attesa del primo controllo completo'
    })

# Route API — prefisso /app/<slug>/
@app.route('/app/<slug>/api/sync', methods=['POST'])
def ingress_api_sync(slug): return api_sync()
@app.route('/app/<slug>/api/stats')
def ingress_api_stats(slug): return api_stats()
@app.route('/app/<slug>/api/test-connessione', methods=['POST'])
def ingress_api_test_conn(slug): return api_test_connessione()
@app.route('/app/<slug>/api/test-telegram', methods=['POST'])
def ingress_api_test_tg(slug): return api_test_telegram()
@app.route('/app/<slug>/api/test-broadcast', methods=['POST'])
def ingress_api_broadcast(slug): return api_test_broadcast()
@app.route('/app/<slug>/api/reset-db', methods=['POST'])
def ingress_api_reset(slug): return api_reset_db()

# Route API — prefisso /api/hassio_ingress/<token>/
@app.route('/api/hassio_ingress/<token>/api/sync', methods=['POST'])
def hassio_api_sync(token): return api_sync()
@app.route('/api/hassio_ingress/<token>/api/stats')
def hassio_api_stats(token): return api_stats()
@app.route('/api/hassio_ingress/<token>/api/test-connessione', methods=['POST'])
def hassio_api_test_conn(token): return api_test_connessione()
@app.route('/api/hassio_ingress/<token>/api/test-telegram', methods=['POST'])
def hassio_api_test_tg(token): return api_test_telegram()
@app.route('/api/hassio_ingress/<token>/api/test-broadcast', methods=['POST'])
def hassio_api_broadcast(token): return api_test_broadcast()
@app.route('/api/hassio_ingress/<token>/api/reset-db', methods=['POST'])
def hassio_api_reset(token): return api_reset_db()

# Route API — prefisso /<slug>/ (Ingress senza /app/)
@app.route('/<slug>/api/sync', methods=['POST'])
def slug_api_sync(slug): return api_sync()
@app.route('/<slug>/api/stats')
def slug_api_stats(slug): return api_stats()
@app.route('/<slug>/api/test-connessione', methods=['POST'])
def slug_api_test_conn(slug): return api_test_connessione()
@app.route('/<slug>/api/test-telegram', methods=['POST'])
def slug_api_test_tg(slug): return api_test_telegram()
@app.route('/<slug>/api/test-broadcast', methods=['POST'])
def slug_api_broadcast(slug): return api_test_broadcast()
@app.route('/<slug>/api/reset-db', methods=['POST'])
def slug_api_reset(slug): return api_reset_db()

# Route pagine — prefisso /<slug>/
@app.route('/<slug>/')
@app.route('/<slug>')
@app.route('/app/<slug>/')
@app.route('/app/<slug>')
def slug_home(slug): return index()
@app.route('/<slug>/calendario')
@app.route('/app/<slug>/calendario')
def slug_calendario(slug): return calendario()
@app.route('/<slug>/voti')
@app.route('/app/<slug>/voti')
def slug_voti(slug): return voti()
@app.route('/<slug>/orario')
@app.route('/app/<slug>/orario')
def slug_orario(slug): return orario()
@app.route('/<slug>/bacheca')
@app.route('/app/<slug>/bacheca')
def slug_bacheca(slug): return bacheca()
@app.route('/<slug>/assenze')
@app.route('/app/<slug>/assenze')
def slug_assenze(slug): return assenze()
@app.route('/<slug>/argomenti')
@app.route('/app/<slug>/argomenti')
def slug_argomenti(slug): return argomenti()
@app.route('/<slug>/configurazione')
@app.route('/app/<slug>/configurazione')
def slug_configurazione(slug): return configurazione()

# Route pagine — prefisso /api/hassio_ingress/<token>/
@app.route('/api/hassio_ingress/<token>/')
@app.route('/api/hassio_ingress/<token>')
def hassio_home(token): return index()
@app.route('/api/hassio_ingress/<token>/calendario')
def hassio_calendario(token): return calendario()
@app.route('/api/hassio_ingress/<token>/voti')
def hassio_voti(token): return voti()
@app.route('/api/hassio_ingress/<token>/orario')
def hassio_orario(token): return orario()
@app.route('/api/hassio_ingress/<token>/bacheca')
def hassio_bacheca(token): return bacheca()
@app.route('/api/hassio_ingress/<token>/assenze')
def hassio_assenze(token): return assenze()
@app.route('/api/hassio_ingress/<token>/argomenti')
def hassio_argomenti(token): return argomenti()
@app.route('/api/hassio_ingress/<token>/configurazione')
def hassio_configurazione(token): return configurazione()

if __name__ == '__main__':
    init_db()
    avvia_bot()
    avvia_scheduler()
    app.run(host='0.0.0.0', port=5002, debug=False)
