"""Presentazione e URL condivisi tra accesso diretto e Ingress Home Assistant."""
from datetime import date, datetime
from urllib.parse import urlencode
from flask import request

MESI = ('gennaio', 'febbraio', 'marzo', 'aprile', 'maggio', 'giugno',
        'luglio', 'agosto', 'settembre', 'ottobre', 'novembre', 'dicembre')
GIORNI = ('Lunedì', 'Martedì', 'Mercoledì', 'Giovedì', 'Venerdì', 'Sabato', 'Domenica')


def data_leggibile(valore, estesa=False):
    try:
        giorno = date.fromisoformat(str(valore)[:10])
    except (ValueError, TypeError):
        return str(valore or '')
    if estesa:
        return f'{GIORNI[giorno.weekday()]} {giorno.day} {MESI[giorno.month - 1]}'
    return f'{giorno.day} {MESI[giorno.month - 1][:3]}'


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
        'orario': ('Orario', 'La settimana di scuola, a colpo d’occhio.'),
        'assenze': ('Presenze e assenze', 'Assenze, ritardi e giustificazioni.'),
        'argomenti': ('Lezioni', 'Quello che si impara, giorno dopo giorno.'),
        'configurazione': ('Impostazioni', 'Collegamenti e preferenze della famiglia.'),
    }
    endpoint = (request.endpoint or 'index').removeprefix('slug_').removeprefix('hassio_')
    if endpoint == 'home':
        endpoint = 'index'
    titolo, sottotitolo = pagine.get(endpoint, ('CompitAPP', 'La scuola, con un po’ più di calma.'))
    ultimo = stato.get('ultimo_successo')
    try:
        dt = datetime.fromisoformat(ultimo) if ultimo else None
        etichetta = ('Oggi' if dt and dt.date() == date.today() else data_leggibile(ultimo)) + (f' alle {dt:%H:%M}' if dt else '')
    except (ValueError, TypeError):
        etichetta = ''
    return dict(ui_link=link, ui_base=base, ui_asset=lambda p: base + '/static/' + p,
                pagina=endpoint, titolo_pagina=titolo, sottotitolo_pagina=sottotitolo,
                ui_studente=scelto, sync_stato=stato, sync_etichetta=etichetta if ultimo else '',
                data_oggi=data_leggibile(date.today(), True))
