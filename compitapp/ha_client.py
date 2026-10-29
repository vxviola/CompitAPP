"""Notifiche HA opzionali: il destinatario viene scelto esplicitamente dall'utente."""
import json
import os
import re
from urllib.parse import urlencode
from datetime import date
import requests
from models import get_db

EVENTI = ('compiti', 'voti', 'assenze', 'note', 'bacheca', 'promemoria', 'documenti')
_slug = None
_ultimo_avviso_sync = None


def avviso_sincronizzazione(stati):
    """Un solo avviso tecnico HA, indipendente dalle notifiche scolastiche."""
    global _ultimo_avviso_sync
    if not stati or not os.environ.get('SUPERVISOR_TOKEN'):
        return
    errori = [s for s in stati if s.get('esito') == 'errore']
    accesso = sum(s.get('motivo') == 'accesso' for s in errori)
    firma = (len(errori), accesso)
    if firma == _ultimo_avviso_sync:
        return
    # Non cancellare un avviso se manca una verifica completa di qualche profilo.
    if not errori and any(s.get('esito') != 'ok' for s in stati):
        return
    _apertura('/')  # recupera lo slug per separare installazioni diverse
    if not _slug:
        return  # al prossimo ciclo si riprova, senza ID condivisi tra installazioni
    payload = {'notification_id': _slug + '_sincronizzazione'}
    azione = 'dismiss'
    if errori:
        azione = 'create'
        payload.update(
            title='UniScuola — accesso Argo fallito' if accesso else 'UniScuola — sincronizzazione fallita',
            message=(f'Dati non aggiornati per {len(errori)} profilo/i. '
                     'Apri UniScuola per verificare lo stato e l’ultimo aggiornamento riuscito. '
                     'I dati già scaricati sono conservati. L’avviso verrà rimosso dopo una '
                     'sincronizzazione completa riuscita per tutti i profili.'))
    try:
        r = requests.post('http://supervisor/core/api/services/persistent_notification/' + azione,
                          headers=_headers(), json=payload, timeout=(3, 8))
        r.raise_for_status()
        _ultimo_avviso_sync = firma
    except (requests.RequestException, RuntimeError):
        print('[HA] Avviso stato non consegnato; riprovo al prossimo controllo')


def configurazione(nome):
    conn = get_db()
    try:
        row = conn.execute('SELECT valore FROM meta WHERE chiave=?', ('ha_notify:' + nome,)).fetchone()
        try:
            cfg = json.loads(row['valore']) if row else {}
        except (ValueError, TypeError):
            cfg = {}
        return {'attive': cfg.get('attive') is True, 'servizio': cfg.get('servizio', ''),
                'eventi': [e for e in cfg.get('eventi', EVENTI) if e in EVENTI]}
    finally:
        conn.close()


def _headers():
    token = os.environ.get('SUPERVISOR_TOKEN', '')
    if not token:
        raise RuntimeError('Disponibile quando UniScuola è eseguita in Home Assistant')
    return {'Authorization': 'Bearer ' + token}


def servizi():
    r = requests.get('http://supervisor/core/api/services', headers=_headers(), timeout=(3, 8))
    r.raise_for_status()
    result = []
    for dominio in r.json():
        for servizio, info in dominio.get('services', {}).items():
            nome = dominio.get('domain', '') + '.' + servizio
            if nome == 'persistent_notification.create' or (dominio.get('domain') == 'notify' and servizio.startswith('mobile_app_')):
                result.append({'id': nome, 'nome': info.get('name') or nome})
    return sorted(result, key=lambda s: s['nome'])


def salva(nome, cfg):
    servizio = cfg.get('servizio', '')
    if (not isinstance(cfg.get('attive'), bool) or not isinstance(cfg.get('eventi'), list)
            or not isinstance(servizio, str) or len(servizio) > 150):
        raise ValueError('Configurazione non valida')
    if any(e not in EVENTI for e in cfg['eventi']):
        raise ValueError('Categoria di notifica non valida')
    if cfg['attive'] and servizio not in {s['id'] for s in servizi()}:
        raise ValueError('Seleziona un dispositivo di Home Assistant disponibile')
    dati = {'attive': cfg['attive'], 'servizio': servizio, 'eventi': list(dict.fromkeys(cfg['eventi']))}
    conn = get_db()
    try:
        conn.execute('INSERT OR REPLACE INTO meta(chiave,valore) VALUES (?,?)', ('ha_notify:' + nome, json.dumps(dati)))
        conn.commit()
    finally:
        conn.close()


def _apertura(percorso):
    global _slug
    if _slug is None:
        try:
            r = requests.get('http://supervisor/addons/self/info', headers=_headers(), timeout=(3, 8))
            r.raise_for_status()
            valore = r.json().get('data', {}).get('slug', '')
            if re.fullmatch(r'[A-Za-z0-9_-]+', valore):
                _slug = valore
        except (requests.RequestException, ValueError, RuntimeError):
            pass
    return '/app/' + _slug + '?' + urlencode({'uniscuola': percorso}) if _slug else '/'


def invia(nome, categoria, titolo, messaggio, percorso='/'):
    cfg = configurazione(nome)
    if not cfg['attive'] or categoria not in cfg['eventi']:
        return False
    servizio = cfg['servizio']
    if not (servizio == 'persistent_notification.create' or re.fullmatch(r'notify\.mobile_app_[a-z0-9_]+', servizio)):
        return False
    dominio, azione = servizio.split('.', 1)
    payload = {'title': titolo[:150], 'message': str(messaggio)[:1500]}
    if dominio == 'notify':
        url = _apertura(percorso)
        payload['data'] = {'url': url, 'clickAction': url}
    try:
        r = requests.post(f'http://supervisor/core/api/services/{dominio}/{azione}',
                          headers=_headers(), json=payload, timeout=(3, 8))
        r.raise_for_status()
        return True
    except (requests.RequestException, RuntimeError):
        print('[HA] Notifica non consegnata; controllare il dispositivo nelle impostazioni')
        return False


def promemoria_documenti(studenti):
    for studente in studenti:
        nome = studente['nome']
        cfg = configurazione(nome)
        if not cfg['attive'] or 'documenti' not in cfg['eventi']:
            continue
        conn = get_db()
        try:
            righe = conn.execute('''SELECT id,titolo,promemoria_locale,letta,allegati FROM bacheca WHERE studente=?
                AND promemoria_locale IS NOT NULL AND promemoria_locale<=?''',
                                 (nome, date.today().isoformat())).fetchall()
            for r in righe:
                from allegati import leggi_allegati
                letti = {a['uid'] for a in conn.execute('SELECT uid FROM allegati_letti WHERE studente=? AND messaggio_id=? AND letto=1', (nome, r['id']))}
                if r['letta'] and all(a['uid'] in letti for a in leggi_allegati(r['allegati'])):
                    continue
                chiave = f'prom_doc:{nome}:{r["id"]}'
                inviato = conn.execute('SELECT valore FROM meta WHERE chiave=?', (chiave,)).fetchone()
                if inviato and inviato['valore'] == r['promemoria_locale']:
                    continue
                ok = invia(nome, 'documenti', f'UniScuola · {nome} · Da leggere', r['titolo'],
                           '/bacheca?' + urlencode({'studente': nome}) + '#msg-' + str(r['id']))
                if ok:
                    conn.execute('INSERT OR REPLACE INTO meta(chiave,valore) VALUES (?,?)', (chiave, r['promemoria_locale']))
                    conn.commit()
        finally:
            conn.close()
