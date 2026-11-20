"""Presentazione e URL condivisi tra accesso diretto e Ingress Home Assistant."""
from datetime import date, datetime
from urllib.parse import urlencode
from flask import request
from preferenze import palette_studente
from pytz import timezone

MESI = ('gennaio', 'febbraio', 'marzo', 'aprile', 'maggio', 'giugno',
        'luglio', 'agosto', 'settembre', 'ottobre', 'novembre', 'dicembre')
GIORNI = ('Lunedì', 'Martedì', 'Mercoledì', 'Giovedì', 'Venerdì', 'Sabato', 'Domenica')
FUSO_SCUOLA = timezone('Europe/Rome')


def data_leggibile(valore, estesa=False):
    try:
        giorno = date.fromisoformat(str(valore)[:10])
    except (ValueError, TypeError):
        return str(valore or '')
    if estesa:
        return f'{GIORNI[giorno.weekday()]} {giorno.day} {MESI[giorno.month - 1]}'
    return f'{giorno.day} {MESI[giorno.month - 1][:3]}'


def orario_registro(valore, futuro=False):
    try:
        dt = datetime.fromisoformat(valore)
    except (TypeError, ValueError):
        return ''
    if dt.tzinfo is None:
        return ''
    dt = dt.astimezone(FUSO_SCUOLA)
    if futuro and dt <= datetime.now(FUSO_SCUOLA):
        return ''
    return f'{data_leggibile(dt)}, {dt:%H:%M}'


def base_ingress():
    for valore in (request.headers.get('X-Ingress-Path'), request.script_root):
        if valore and valore.startswith('/') and not valore.startswith('//') and not any(c in valore for c in '\r\n?#\\'):
            return valore.rstrip('/')
    args = request.view_args or {}
    if args.get('prefix'):
        return '/' + args['prefix'].strip('/')
    if args.get('token'):
        return '/api/hassio_ingress/' + args['token']
    if args.get('slug'):
        return ('/app/' if request.path.startswith('/app/') else '/') + args['slug']
    return ''


def contesto_ui(studenti, stato):
    nomi = [s.get('nome', '') for s in studenti]
    scelto = request.args.get('studente')
    scelto = scelto if scelto in nomi else (nomi[0] if nomi else '')
    base = base_ingress()

    def link(pagina='/', studente=None, **parametri):
        parametri['studente'] = scelto if studente is None else studente
        query = urlencode({k: v for k, v in parametri.items() if v not in (None, '')})
        return base + pagina + ('?' + query if query else '')

    pagine = {
        'index': ('La tua giornata', 'Una cosa alla volta. Tutto sotto controllo.'),
        'calendario': ('Calendario', 'Le prossime consegne, con il tempo per organizzarsi.'),
        'bacheca': ('Bacheca', 'Comunicazioni e documenti, tutti al loro posto.'),
        'voti': ('Voti e progressi', 'Uno sguardo al percorso, materia per materia.'),
        'revisione': ('Verifica voti duplicati', 'Confronta le voci di UniScuola con le valutazioni nel registro Argo.'),
        'orario': ('Orario', 'La settimana di scuola, a colpo d’occhio.'),
        'assenze': ('Presenze e assenze', 'Assenze, ritardi e giustificazioni.'),
        'argomenti': ('Lezioni', 'Quello che si impara, giorno dopo giorno.'),
        'configurazione': ('Impostazioni', 'Collegamenti e preferenze della famiglia.'),
        'zaino': ('Prepara lo zaino', 'Un piccolo controllo, per partire più tranquilli.'),
        'ricerca': ('Cerca nel registro', 'Compiti, lezioni e documenti: trova quello che ti serve.'),
    }
    endpoint = (request.endpoint or 'index').rsplit('.', 1)[-1].removeprefix('slug_').removeprefix('hassio_')
    if endpoint == 'home':
        endpoint = 'index'
    titolo, sottotitolo = pagine.get(endpoint, ('UniScuola', 'La scuola, con un po’ più di calma.'))
    return dict(ui_link=link, ui_base=base, ui_palette=palette_studente(scelto), ui_asset=lambda p: base + '/static/' + p,
                pagina=endpoint, titolo_pagina=titolo, sottotitolo_pagina=sottotitolo,
                ui_studente=scelto, sync_stato=stato, sync_etichetta=orario_registro(stato.get('ultimo_successo')),
                sync_prossimo=orario_registro(stato.get('prossimo_tentativo'), futuro=True),
                data_oggi=data_leggibile(date.today(), True))
