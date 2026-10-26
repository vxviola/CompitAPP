"""Azioni personali del registro: restano locali e non confermano letture su Argo."""
from datetime import date, timedelta
import json
import unicodedata
from urllib.parse import urlencode
from flask import Blueprint, abort, jsonify, render_template, request
from argo_client import get_studenti
from allegati import leggi_allegati
from models import get_db
import ha_client

bp = Blueprint('funzioni', __name__)


def _studente(obbligatorio=False):
    nomi = [s['nome'] for s in get_studenti()]
    nome = request.args.get('studente', '')
    if nome in nomi:
        return nome
    if obbligatorio or not nomi:
        abort(404)
    return nomi[0]


def _json():
    dati = request.get_json(silent=True)
    if not isinstance(dati, dict):
        abort(400)
    return dati


def _bool(dati, chiave):
    if not isinstance(dati.get(chiave), bool):
        abort(400)
    return int(dati[chiave])


def _giorno(valore, facoltativo=False):
    if facoltativo and not valore:
        return None
    try:
        return date.fromisoformat(str(valore)).isoformat()
    except (ValueError, TypeError):
        abort(400)


@bp.route('/api/compiti/<int:rid>', methods=['POST'])
@bp.route('/<path:prefix>/api/compiti/<int:rid>', methods=['POST'])
def completa_compito(rid, prefix=None):
    nome = _studente(True)
    completato = _bool(_json(), 'completato')
    conn = get_db()
    try:
        r = conn.execute("UPDATE compiti SET completato=?,completato_il=CASE WHEN ? THEN datetime('now') ELSE NULL END WHERE id=? AND studente=?",
                         (completato, completato, rid, nome))
        if not r.rowcount:
            abort(404)
        conn.commit()
    finally:
        conn.close()
    return jsonify(ok=True, completato=bool(completato))


@bp.route('/api/bacheca/<int:rid>', methods=['POST'])
@bp.route('/<path:prefix>/api/bacheca/<int:rid>', methods=['POST'])
def preferenza_documento(rid, prefix=None):
    nome, dati = _studente(True), _json()
    valori = {}
    for campo in ('letta', 'preferito'):
        if campo in dati:
            valori[campo] = _bool(dati, campo)
    if 'promemoria_locale' in dati:
        valori['promemoria_locale'] = _giorno(dati['promemoria_locale'], True)
    if not valori:
        abort(400)
    conn = get_db()
    try:
        r = conn.execute('UPDATE bacheca SET ' + ','.join(k + '=?' for k in valori) + ' WHERE id=? AND studente=?',
                         [*valori.values(), rid, nome])
        if not r.rowcount:
            abort(404)
        conn.commit()
    finally:
        conn.close()
    return jsonify(ok=True)


@bp.route('/api/bacheca/<int:rid>/allegati/<int:indice>/letto', methods=['POST'])
@bp.route('/<path:prefix>/api/bacheca/<int:rid>/allegati/<int:indice>/letto', methods=['POST'])
def letto_allegato(rid, indice, prefix=None):
    nome, letto = _studente(True), _bool(_json(), 'letto')
    conn = get_db()
    try:
        r = conn.execute('SELECT allegati FROM bacheca WHERE id=? AND studente=?', (rid, nome)).fetchone()
        allegati = leggi_allegati(r['allegati']) if r else []
        if indice >= len(allegati):
            abort(404)
        conn.execute('''INSERT INTO allegati_letti(studente,messaggio_id,uid,letto) VALUES (?,?,?,?)
                        ON CONFLICT(studente,messaggio_id,uid) DO UPDATE SET letto=excluded.letto''',
                     (nome, rid, allegati[indice]['uid'], letto))
        conn.commit()
    finally:
        conn.close()
    return jsonify(ok=True)


@bp.route('/zaino')
@bp.route('/<path:prefix>/zaino')
def zaino(prefix=None):
    nome = _studente()
    giorno = _giorno(request.args.get('data') or (date.today() + timedelta(days=1)).isoformat())
    conn = get_db()
    try:
        materie_giorno = [r['materia'] for r in conn.execute('SELECT materia FROM orario WHERE studente=? AND giorno=? ORDER BY ora', (nome, date.fromisoformat(giorno).weekday()))]
        materiali = [dict(r) for r in conn.execute('''SELECT m.*,COALESCE(s.fatto,0) AS fatto FROM zaino_materiali m
                       LEFT JOIN zaino_spunte s ON s.materiale_id=m.id AND s.data=? WHERE m.studente=? ORDER BY m.materia,m.id''', (giorno, nome))]
        materie = [r[0] for r in conn.execute('SELECT DISTINCT materia FROM orario WHERE studente=? UNION SELECT DISTINCT materia FROM compiti WHERE studente=? ORDER BY materia', (nome, nome)) if r[0]]
    finally:
        conn.close()
    normalize = lambda s: s.strip().casefold()
    visibili = [m for m in materiali if not m['materia'] or normalize(m['materia']) in {normalize(v) for v in materie_giorno}]
    return render_template('zaino.html', studenti=get_studenti(), studente_sel=nome,
                           giorno=giorno, materie_giorno=materie_giorno, materie=materie,
                           materiali=materiali, checklist=visibili, fatti=sum(m['fatto'] for m in visibili))


@bp.route('/api/zaino', methods=['POST'])
@bp.route('/<path:prefix>/api/zaino', methods=['POST'])
def aggiungi_materiale(prefix=None):
    nome, dati = _studente(True), _json()
    testo, materia = dati.get('testo'), dati.get('materia', '')
    if not isinstance(testo, str) or not 1 <= len(testo.strip()) <= 200 or not isinstance(materia, str) or len(materia) > 150:
        abort(400)
    conn = get_db()
    try:
        cur = conn.execute('INSERT INTO zaino_materiali(studente,materia,testo) VALUES (?,?,?)', (nome, materia.strip(), testo.strip()))
        conn.commit()
        rid = cur.lastrowid
    finally:
        conn.close()
    return jsonify(ok=True, id=rid)


@bp.route('/api/zaino/<int:rid>', methods=['POST', 'DELETE'])
@bp.route('/<path:prefix>/api/zaino/<int:rid>', methods=['POST', 'DELETE'])
def spunta_materiale(rid, prefix=None):
    nome = _studente(True)
    dati = _json() if request.method == 'POST' else {}
    conn = get_db()
    try:
        if not conn.execute('SELECT 1 FROM zaino_materiali WHERE id=? AND studente=?', (rid, nome)).fetchone():
            abort(404)
        if request.method == 'DELETE':
            conn.execute('DELETE FROM zaino_spunte WHERE materiale_id=?', (rid,))
            conn.execute('DELETE FROM zaino_materiali WHERE id=?', (rid,))
        else:
            giorno, fatto = _giorno(dati.get('data')), _bool(dati, 'fatto')
            conn.execute('''INSERT INTO zaino_spunte(materiale_id,data,fatto) VALUES (?,?,?)
                            ON CONFLICT(materiale_id,data) DO UPDATE SET fatto=excluded.fatto''', (rid, giorno, fatto))
        conn.commit()
    finally:
        conn.close()
    return jsonify(ok=True)


def _fold(testo):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(testo or '')).casefold() if not unicodedata.combining(c))


@bp.route('/ricerca')
@bp.route('/<path:prefix>/ricerca')
def ricerca(prefix=None):
    nome = _studente()
    q = request.args.get('q', '').strip()[:200]
    risultati = []
    sezioni = [('compiti','Compiti',('materia','testo'),'/calendario'),
               ('voti','Voti',('materia','voto','descrizione'),'/voti'),
               ('argomenti','Lezioni',('materia','argomento','attivita'),'/argomenti'),
               ('bacheca','Comunicazioni e documenti',('titolo','testo','mittente','allegati'),'/bacheca'),
               ('promemoria','Promemoria',('testo','docente'),'/')]
    conn = get_db()
    try:
        conn.create_function('ricerca_fold', 1, _fold)
        if q:
            for tabella, titolo, campi, pagina in sezioni:
                where = ' OR '.join(f'instr(ricerca_fold({k}),?)>0' for k in campi)
                righe = [dict(r) for r in conn.execute(f'SELECT * FROM {tabella} WHERE studente=? AND ({where}) ORDER BY data DESC,id DESC LIMIT 31', [nome] + [_fold(q)]*len(campi))]
                risultati.append({'titolo': titolo, 'righe': righe[:30], 'altri': len(righe)>30, 'pagina': pagina, 'tipo': tabella})
    finally:
        conn.close()
    return render_template('ricerca.html', studenti=get_studenti(), studente_sel=nome, q=q,
                           risultati=risultati, totale=sum(len(r['righe']) for r in risultati))


@bp.route('/api/ha/servizi')
@bp.route('/<path:prefix>/api/ha/servizi')
def servizi_ha(prefix=None):
    _studente(True)
    try:
        return jsonify(servizi=ha_client.servizi())
    except Exception:
        return jsonify(errore='Non riesco a leggere i dispositivi. Verifica che UniScuola sia avviata in Home Assistant.'), 503


@bp.route('/api/ha/notifiche', methods=['GET', 'POST'])
@bp.route('/<path:prefix>/api/ha/notifiche', methods=['GET', 'POST'])
def notifiche_ha(prefix=None):
    nome = _studente(True)
    if request.method == 'GET':
        return jsonify(ha_client.configurazione(nome))
    try:
        ha_client.salva(nome, _json())
        return jsonify(ok=True)
    except ValueError as e:
        return jsonify(errore=str(e)), 400
    except Exception:
        return jsonify(errore='Home Assistant non disponibile: impostazioni non salvate.'), 503


@bp.route('/api/ha/test', methods=['POST'])
@bp.route('/<path:prefix>/api/ha/test', methods=['POST'])
def test_notifica_ha(prefix=None):
    nome = _studente(True)
    cfg = ha_client.configurazione(nome)
    categoria = next(iter(cfg['eventi']), '')
    ok = ha_client.invia(nome, categoria, 'UniScuola · prova', 'Le notifiche di ' + nome + ' sono configurate.', '/?' + urlencode({'studente': nome}))
    return jsonify(ok=ok), 200 if ok else 502
