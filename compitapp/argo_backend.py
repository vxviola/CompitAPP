"""API Famiglia WEB, verificate sul client ufficiale 4.3.0 il 17/11/2026."""
ENDPOINT = 'https://didattica.portaleargo.it/famiglia/api/'


def api_headers(access_token, school=None, profile_token=None):
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json',
               'Authorization': 'Bearer ' + access_token,
               'os-type': 'WEB', 'argo-client-version': '4.3.0'}
    if school:
        headers['x-cod-min'] = school
    if profile_token:
        headers['x-auth-token'] = profile_token
    return headers


def dashboard_body(since):
    # null asks the official backend for the available sections for this profile.
    return {'dataultimoaggiornamento': since, 'opzioni': None}
