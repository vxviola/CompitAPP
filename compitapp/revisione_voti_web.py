"""Revisione volontaria delle copie locali dei voti."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hmac
import secrets
from threading import Lock
from urllib.parse import urlencode

from flask import Blueprint, abort, make_response, redirect, render_template, request

from argo_client import get_studenti
from confronto_voti import confronta_gruppi_voti
from models import get_db
from revisione_voti import RevisioneObsoleta, escludi_copia, gruppi_voti, ripristina_copia
from ui import base_ingress, orario_registro

bp = Blueprint('revisione_voti', __name__)
_chiave_modulo = secrets.token_bytes(32)
_riscontri = {}
_lock_riscontri = Lock()
_pagina = '/voti/duplicati'
_avvisi = {
    'esclusa': 'Copia esclusa dai voti di UniScuola. Puoi ripristinarla da questa pagina.',
    'ripristinata': 'Copia ripristinata nei voti di UniScuola.',
}


def _id_locale(campo):
    valore = request.form.get(campo, '')
    if not valore.isascii() or not valore.isdecimal() or len(valore) > 19:
        abort(400)
    numero = int(valore)
    if not 0 < numero <= 2**63 - 1:
        abort(400)
    return numero


def _riscontri_correnti(nome, gruppi, nuovi=None):
    ora = datetime.now(timezone.utc)
    versioni = {gruppo['versione'] for gruppo in gruppi}
    with _lock_riscontri:
        validi = {v: risultato for v, risultato in _riscontri.pop(nome, {}).items()
                  if v in versioni and ora - risultato[0] < timedelta(minutes=15)}
        for versione, risultato in (nuovi or {}).items():
            if versione in versioni:
                validi[versione] = (ora, risultato)
        if validi:
            if len(_riscontri) >= 16:
                del _riscontri[next(iter(_riscontri))]
            # Lo schermo corrente mostra tutti gli esiti. Conserva soltanto i 128 più recenti.
            _riscontri[nome] = dict(sorted(validi.items(), key=lambda voce: voce[1][0])[-128:])
    return {v: dict(risultato, ora=orario_registro(istante.isoformat()))
            for v, (istante, risultato) in validi.items()}


def _pagina_gruppi(studenti, nome, token, gruppi, *, avviso='', errore='', nuovi=None):
    escluse = 0
    da_verificare, risolti = [], []
    for gruppo in gruppi:
        nascoste = sum(r['esclusa'] for r in gruppo['righe'])
        escluse += nascoste
        if len(gruppo['righe']) - nascoste > 1:
            da_verificare.append(gruppo)
        else:
            risolti.append(gruppo)
    risposta = make_response(render_template('revisione_voti.html', studenti=studenti, studente_sel=nome,
                             token_modulo=token, gruppi=da_verificare + risolti, avviso=avviso, errore=errore,
                             gruppi_multipli=len(da_verificare), copie_escluse=escluse,
                             riscontri=_riscontri_correnti(nome, gruppi, nuovi)), 409 if errore else 200)
    risposta.cache_control.no_store = True
    return risposta


@bp.route(_pagina, methods=['GET', 'POST'])
@bp.route('/<path:prefix>' + _pagina, methods=['GET', 'POST'])
def revisione(prefix=None):
    studenti = get_studenti()
    nomi = request.args.getlist('studente')
    if len(nomi) != 1:
        abort(404)
    nome = nomi[0]
    studente = next((s for s in studenti if s['nome'] == nome), None)
    if studente is None:
        abort(404)
    token = hmac.digest(_chiave_modulo, nome.encode(), 'sha256').hex()
    with closing(get_db()) as conn:
        gruppi = gruppi_voti(conn, nome)
    if request.method == 'GET':
        return _pagina_gruppi(studenti, nome, token, gruppi, avviso=_avvisi.get(request.args.get('esito'), ''))

    if not secrets.compare_digest(token.encode(), request.form.get('token', '').encode()):
        abort(403)
    azione = request.form.get('azione')
    versione = request.form.get('versione', '')
    selezionati = gruppi if azione == 'confronta_tutti' else [g for g in gruppi if g['versione'] == versione]
    if azione not in ('confronta', 'confronta_tutti', 'escludi', 'ripristina'):
        abort(400)
    obsoleto = 'Il gruppo è cambiato. Controlla le registrazioni aggiornate prima di scegliere.'
    if not selezionati:
        return _pagina_gruppi(studenti, nome, token, gruppi, errore=obsoleto)
    if azione in ('confronta', 'confronta_tutti'):
        risultati = confronta_gruppi_voti(studente, selezionati)
        with closing(get_db()) as conn:
            gruppi = gruppi_voti(conn, nome)
        correnti = {g['versione'] for g in gruppi}
        cambiati = any(g['versione'] not in correnti for g in selezionati)
        return _pagina_gruppi(studenti, nome, token, gruppi, nuovi=risultati, errore=obsoleto if cambiati else '')

    copia = _id_locale('copia_id')
    if azione == 'escludi' and _riscontri_correnti(nome, gruppi).get(versione, {}).get('esito') == 'distinti':
        return _pagina_gruppi(studenti, nome, token, gruppi,
                              errore='Argo ha confermato che queste prove sono distinte. Conserva le registrazioni.')
    with closing(get_db()) as conn:
        try:
            if azione == 'escludi':
                if request.form.get('conferma') != 'si':
                    abort(400)
                escludi_copia(conn, nome, copia, _id_locale('conserva_id'), versione)
                esito = 'esclusa'
            else:
                ripristina_copia(conn, nome, copia, versione)
                esito = 'ripristinata'
        except RevisioneObsoleta:
            return _pagina_gruppi(studenti, nome, token, gruppi_voti(conn, nome), errore=obsoleto)
    destinazione = base_ingress() + _pagina + '?' + urlencode({'studente': nome, 'esito': esito})
    return redirect(destinazione, code=303)
