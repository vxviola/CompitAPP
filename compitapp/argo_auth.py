"""Login password con diagnostica priva di dati personali.

Flusso derivato da argofamiglia 0.1.2 (Salvatore Abello, MIT).
Non modifica globalmente la libreria: SPID e le altre richieste restano separati.

Copyright © 2022 salvatore.abello

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
import base64
import secrets
from hashlib import sha256
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlsplit

import requests
from argofamiglia import ArgoFamiglia
from argofamiglia.auth import CHALLENGE_URL, LOGIN_URL, TOKEN_URL, REDIRECT_URI, CLIENT_ID
from argofamiglia.CONSTANTS import ENDPOINT, USER_AGENT


class ArgoLoginError(ValueError):
    """Messaggio composto esclusivamente da metadati controllati."""


class _AppRedirectParser(HTMLParser):
    """Legge il link usato da initializeAppRedirect nel JavaScript pubblico Argo."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.targets = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == 'a' and 'data-auth-app-redirect' in attributes:
            self.targets.append(attributes.get('href') or '')


def _html_app_redirect(response, hop):
    # Argo mostra ora una pagina di conferma prima dell'ultimo hop OAuth.
    # Non eseguiamo JavaScript e non seguiamo link generici della pagina.
    origin = urlsplit(response.url)
    if (response.status_code != 200 or origin.scheme != 'https'
            or origin.netloc != 'www.portaleargo.it'
            or origin.path.rstrip('/') != '/auth/sso/consent'
            or response.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'text/html'):
        return None
    if len(response.content) > 1024 * 1024:
        _fail('consent_html', 'pagina_troppo_grande', response, hop)
    parser = _AppRedirectParser()
    parser.feed(response.text)
    if not parser.targets:
        return None
    if len(parser.targets) != 1 or not parser.targets[0]:
        _fail('consent_html', 'link_app_non_univoco', response, hop)
    target = urljoin(response.url, parser.targets[0])
    try:
        destination = urlsplit(target)
    except ValueError:
        _fail('consent_html', 'destinazione_non_prevista', response, hop)
    expected = urlsplit(CHALLENGE_URL)
    if ((destination.scheme, destination.netloc, destination.path) !=
            (expected.scheme, expected.netloc, expected.path)
            or destination.fragment or not destination.query):
        _fail('consent_html', 'destinazione_non_prevista', response, hop)
    return target


def _fail(stage, reason, response=None, hop=0):
    status = response.status_code if response is not None else 'nessuna'
    location = 'si' if response is not None and response.headers.get('Location') else 'no'
    raise ArgoLoginError(
        f'ARGO-AUTH fase={stage} passo={hop} HTTP={status} '
        f'location={location} motivo={reason}. '
        'Accesso non completato; questo messaggio non prova che la password sia errata.'
    ) from None


def _request(session, method, url, stage, hop=0, **kwargs):
    try:
        response = session.request(method, url, timeout=(10, 30), **kwargs)
    except requests.Timeout:
        _fail(stage, 'timeout', hop=hop)
    except requests.RequestException:
        # Le eccezioni requests possono includere URL, query e token.
        _fail(stage, 'errore_rete', hop=hop)
    if not 200 <= response.status_code < 400:
        _fail(stage, 'stato_http_inatteso', response, hop)
    return response


def _json(response, stage):
    try:
        data = response.json()
    except ValueError:
        _fail(stage, 'json_non_valido', response)
    if not isinstance(data, dict):
        _fail(stage, 'struttura_non_valida', response)
    return data


def login(school, username, password):
    verifier = secrets.token_hex(64)
    challenge = base64.urlsafe_b64encode(sha256(verifier.encode()).digest()).decode().rstrip('=')
    state = secrets.token_urlsafe(32)
    with requests.Session() as session:
        response = _request(session, 'GET', CHALLENGE_URL, 'challenge', params={
            'redirect_uri': REDIRECT_URI, 'client_id': CLIENT_ID,
            'response_type': 'code', 'prompt': 'login', 'state': state,
            'scope': 'openid offline profile user.roles argo',
            'code_challenge': challenge, 'code_challenge_method': 'S256'})
        challenge_values = parse_qs(urlsplit(response.url).query).get('login_challenge', [])
        if not challenge_values:
            _fail('challenge', 'challenge_assente', response)
        response = _request(session, 'POST', LOGIN_URL, 'credenziali', allow_redirects=False, data={
            'challenge': challenge_values[0], 'client_id': CLIENT_ID, 'prefill': 'true',
            'famiglia_customer_code': school, 'username': username,
            'password': password, 'login': 'true'})
        for hop in range(11):
            stage = 'credenziali' if hop == 0 else 'redirect'
            location = response.headers.get('Location')
            if not location:
                location = _html_app_redirect(response, hop)
            if not location:
                _fail(stage, 'location_assente', response, hop)
            target = urljoin(response.url, location)
            parts = urlsplit(target)
            callback = urlsplit(REDIRECT_URI)
            if (parts.scheme, parts.netloc, parts.path) == (callback.scheme, callback.netloc, callback.path):
                query = parse_qs(parts.query)
                if 'error' in query:
                    _fail('callback', 'oauth_rifiutato', response, hop)
                if not query.get('code'):
                    _fail('callback', 'code_assente', response, hop)
                # La libreria precedente non richiedeva state; se presente, deve coincidere.
                if 'state' in query and query['state'] != [state]:
                    _fail('callback', 'state_non_valido', response, hop)
                code = query['code'][0]
                break
            if hop == 10:
                _fail('redirect', 'limite_redirect', response, hop)
            if (parts.scheme != 'https' or parts.username or parts.password
                    or parts.hostname not in {'www.portaleargo.it', 'auth.portaleargo.it', 'portaleargo.it'}):
                _fail('redirect', 'destinazione_non_prevista', response, hop)
            response = _request(session, 'GET', target, 'redirect', hop + 1, allow_redirects=False)
        response = _request(session, 'POST', TOKEN_URL, 'token', allow_redirects=False, data={
            'code': code, 'grant_type': 'authorization_code', 'redirect_uri': REDIRECT_URI,
            'code_verifier': verifier, 'client_id': CLIENT_ID})
        tokens = _json(response, 'token')
        if not isinstance(tokens.get('access_token'), str) or not tokens['access_token']:
            _fail('token', 'access_token_assente', response)
        response = _request(session, 'POST', ENDPOINT + 'login', 'profili', allow_redirects=False,
            headers={'User-Agent': USER_AGENT, 'Content-Type': 'Application/json',
                     'Authorization': 'Bearer ' + tokens['access_token'], 'Accept': 'Application/json'},
            json={'clientID': secrets.token_urlsafe(64), 'lista-x-auth-token': '[]',
                  'x-auth-token-corrente': 'null', 'lista-opzioni-notifiche': '{}'})
        profiles = _json(response, 'profili').get('data')
        if (not isinstance(profiles, list) or not profiles or not isinstance(profiles[0], dict)
                or not isinstance(profiles[0].get('token'), str) or not profiles[0]['token']):
            _fail('profili', 'profilo_token_assente', response)
        return profiles[0]['token'], tokens


class ArgoPassword(ArgoFamiglia):
    def connect(self):
        token, data = login(self.school, self.username, self._ArgoFamiglia__password)
        self._ArgoFamiglia__token = token
        self._ArgoFamiglia__login_data = data
        self._ArgoFamiglia__headers = {
            'Content-Type': 'Application/json', 'Accept': 'Application/json',
            'Authorization': 'Bearer ' + data['access_token'],
            'x-cod-min': self.school, 'x-auth-token': token}
        return self
