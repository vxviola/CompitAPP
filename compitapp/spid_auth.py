"""Accesso ad Argo con SPID/CIE (sperimentale).

Con SPID non si può fare il login automatico: l'utente si autentica una volta nel browser, copia
l'indirizzo finale (che contiene un codice temporaneo) e lo incolla in UniScuola. L'app scambia il
codice con i token e poi rinnova da sola il token di accesso usando quello di rinnovo.

Il token di rinnovo di Argo cambia a ogni uso ("rotazione"): quello nuovo viene salvato SUBITO, prima
di usare il nuovo token di accesso, e la scrittura del file è atomica. I token stanno solo in
/data (spazio privato dell'app), con permessi 600, e non vengono mai scritti nei registri.
"""
import os
import re
import json
import time
import base64
import secrets
import tempfile
import threading
from hashlib import sha256
from urllib.parse import urlencode

import requests

try:  # stessi valori della libreria, così restano allineati
    from argofamiglia import auth as _auth
    CHALLENGE_URL = _auth.CHALLENGE_URL
    TOKEN_URL = _auth.TOKEN_URL
    REDIRECT_URI = _auth.REDIRECT_URI
    CLIENT_ID = _auth.CLIENT_ID
except Exception:  # pragma: no cover
    CHALLENGE_URL = "https://auth.portaleargo.it/oauth2/auth"
    TOKEN_URL = "https://auth.portaleargo.it/oauth2/token"
    REDIRECT_URI = "it.argosoft.didup.famiglia.new://login-callback"
    CLIENT_ID = "72fd6dea-d0ab-4bb9-8eaa-3ac24c84886c"

SCOPE = "openid offline profile user.roles argo"
STORE = os.environ.get('SPID_STORE', '/data/spid_tokens.json')
ATTESA_MAX_SECONDI = 15 * 60   # il codice di Argo scade in pochi minuti
_lock = threading.RLock()


class SpidError(Exception):
    """Accesso non riuscito: serve ricollegare con SPID."""


class SpidTemporaneo(Exception):
    """Problema passeggero (rete, Argo non raggiungibile): non si perde il collegamento."""


# ── archivio ────────────────────────────────────────────────────────────────

def _carica():
    try:
        with open(STORE) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _salva(d):
    """Scrittura atomica: file temporaneo nella stessa cartella, poi os.replace."""
    cartella = os.path.dirname(STORE) or '.'
    os.makedirs(cartella, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=cartella, prefix='.spid_', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(d, f)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, STORE)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _studente(d, nome):
    return d.setdefault('studenti', {}).setdefault(nome, {})


# ── stato (per la pagina Configurazione) ────────────────────────────────────

def stato(nome):
    """{'stato': 'non_collegato'|'collegato'|'da_ricollegare', 'collegato_il', 'ultimo_rinnovo', 'motivo'}"""
    with _lock:
        s = _carica().get('studenti', {}).get(nome, {})
    if not s.get('refresh_token'):
        return {'stato': 'da_ricollegare' if s.get('da_ricollegare') else 'non_collegato',
                'collegato_il': s.get('collegato_il'), 'ultimo_rinnovo': s.get('ultimo_rinnovo'),
                'motivo': s.get('motivo', '')}
    return {'stato': 'da_ricollegare' if s.get('da_ricollegare') else 'collegato',
            'collegato_il': s.get('collegato_il'), 'ultimo_rinnovo': s.get('ultimo_rinnovo'),
            'motivo': s.get('motivo', '')}


# ── collegamento (una volta) ────────────────────────────────────────────────

def genera_link(nome):
    verifier = secrets.token_hex(64)
    challenge = base64.urlsafe_b64encode(sha256(verifier.encode()).digest()).replace(b"=", b"").decode()
    state = secrets.token_urlsafe(32)
    with _lock:
        d = _carica()
        d.setdefault('attese', {})[nome] = {'verifier': verifier, 'state': state, 'creato': time.time()}
        _salva(d)
    return CHALLENGE_URL + "?" + urlencode({
        "redirect_uri": REDIRECT_URI, "client_id": CLIENT_ID, "response_type": "code", "prompt": "login",
        "state": state, "scope": SCOPE, "code_challenge": challenge, "code_challenge_method": "S256"})


def collega(nome, testo):
    """Scambia il codice (o l'indirizzo copiato) con i token. Ritorna (ok, messaggio)."""
    testo = (testo or '').strip()
    if not testo:
        return False, "Incolla l'indirizzo copiato dal browser."
    with _lock:
        d = _carica()
        attesa = d.get('attese', {}).get(nome)
        if not attesa:
            return False, "Prima premi «Genera link» e accedi con SPID."
        if time.time() - attesa['creato'] > ATTESA_MAX_SECONDI:
            return False, "Il link è scaduto: premi di nuovo «Genera link» e ripeti l'accesso."
        m = re.search(r'code=([0-9a-zA-Z\-_.]+)', testo)
        code = m.group(1) if m else testo
        if not re.fullmatch(r'[0-9a-zA-Z\-_.]{10,}', code):
            return False, "Non trovo il codice: copia l'indirizzo intero che comincia con it.argosoft.didup.famiglia.new://login-callback?code=…"
        s = re.search(r'state=([0-9a-zA-Z\-_.]+)', testo)
        if s and s.group(1) != attesa['state']:
            return False, "L'indirizzo appartiene a un altro tentativo: usa l'ultimo link generato."
        try:
            r = requests.post(TOKEN_URL, timeout=30,
                              headers={"Accept": "Application/json", "Content-Type": "application/x-www-form-urlencoded"},
                              data={"code": code, "grant_type": "authorization_code", "redirect_uri": REDIRECT_URI,
                                    "code_verifier": attesa['verifier'], "client_id": CLIENT_ID})
            t = r.json()
        except Exception as e:
            return False, f"Argo non raggiungibile ({type(e).__name__}): riprova tra poco."
        if 'refresh_token' not in t:
            err = t.get('error_description') or t.get('error') or 'risposta senza token di rinnovo'
            return False, f"Argo ha rifiutato il codice ({err}). Il codice vale pochi minuti e una sola volta: rifai l'accesso e incolla subito."
        ora = time.time()
        s_ = _studente(d, nome)
        s_.update({'refresh_token': t['refresh_token'], 'collegato_il': ora, 'ultimo_rinnovo': ora,
                   'da_ricollegare': False, 'avvisato': False, 'motivo': ''})
        d.get('attese', {}).pop(nome, None)
        _salva(d)
    return True, "Collegato! L'app rinnoverà l'accesso da sola."


# ── rinnovo (ogni volta che serve una sessione) ─────────────────────────────

def _avvisa_da_ricollegare(nome):
    try:
        from notifier import send_telegram
        send_telegram(f"⚠️ <b>UniScuola</b>\nL'accesso ad Argo per <b>{nome}</b> con SPID è scaduto.\n"
                      "Apri UniScuola → Configurazione → «Collega con SPID» per ricollegarlo.")
    except Exception as e:
        print(f"[SPID] Avviso Telegram non inviato ({e})")


def rinnova(nome):
    """Rinnova il token di accesso di `nome` e ne ritorna i dati. Salva SUBITO il nuovo token di rinnovo."""
    with _lock:
        d = _carica()
        s = d.get('studenti', {}).get(nome)
        if not s or not s.get('refresh_token'):
            raise SpidError(f"{nome}: accesso con SPID non ancora collegato")
        if s.get('da_ricollegare'):
            raise SpidError(f"{nome}: accesso con SPID scaduto, serve ricollegare")
        try:
            r = requests.post(TOKEN_URL, timeout=30,
                              headers={"Accept": "Application/json", "Content-Type": "application/x-www-form-urlencoded"},
                              data={"refresh_token": s['refresh_token'], "grant_type": "refresh_token", "scope": SCOPE,
                                    "redirect_uri": REDIRECT_URI, "client_id": CLIENT_ID})
        except requests.RequestException as e:
            raise SpidTemporaneo(f"{nome}: Argo non raggiungibile ({type(e).__name__})")
        if r.status_code >= 500:
            raise SpidTemporaneo(f"{nome}: Argo risponde con errore {r.status_code}")
        try:
            t = r.json()
        except ValueError:
            raise SpidTemporaneo(f"{nome}: risposta di Argo non valida (HTTP {r.status_code})")
        if 'access_token' not in t:
            # rifiutato davvero (es. invalid_grant): la catena è finita
            s.update({'da_ricollegare': True, 'motivo': str(t.get('error') or 'rinnovo rifiutato')})
            avvisare = not s.get('avvisato')
            s['avvisato'] = True
            _salva(d)
            print(f"[SPID] {nome}: rinnovo rifiutato da Argo ({t.get('error')}): serve ricollegare")
            if avvisare:
                _avvisa_da_ricollegare(nome)
            raise SpidError(f"{nome}: accesso con SPID scaduto, serve ricollegare")
        if t.get('refresh_token'):
            s['refresh_token'] = t['refresh_token']     # ruotato: va conservato subito
        s['ultimo_rinnovo'] = time.time()
        _salva(d)
        return t
