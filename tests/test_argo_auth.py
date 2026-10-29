import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

import requests
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'compitapp'))
import argo_auth as auth
import argo_client


def response(status=200, location=None, data=None, url=auth.LOGIN_URL):
    r = Mock(status_code=status, url=url)
    r.headers = requests.structures.CaseInsensitiveDict()
    if location is not None:
        r.headers['location'] = location
    r.json.return_value = data
    return r


class LoginTest(unittest.TestCase):
    def run_login(self, replies):
        session = Mock()
        session.request.side_effect = replies
        with patch.object(auth.requests, 'Session') as factory:
            factory.return_value.__enter__.return_value = session
            result = auth.ArgoPassword('school-secret', 'username-secret', 'password-secret')
        return result, session

    def challenge(self):
        return response(url=auth.LOGIN_URL + '?login_challenge=challenge-secret')

    def callback(self):
        return response(302, auth.REDIRECT_URI + '?code=code-secret')

    def test_success_and_private_headers(self):
        obj, session = self.run_login([self.challenge(), response(302, '/next'), self.callback(),
            response(data={'access_token': 'access-secret'}), response(data={'data': [{'token': 'profile-secret'}]})])
        self.assertEqual(obj._ArgoFamiglia__headers['x-auth-token'], 'profile-secret')
        self.assertEqual(session.request.call_count, 5)
        self.assertTrue(all(c.kwargs['timeout'] == (10, 30) for c in session.request.call_args_list))

    def test_missing_location_at_first_and_later_response(self):
        for prefix, phase, step in [([], 'credenziali', 0), ([response(302, '/next')], 'redirect', 1)]:
            with self.subTest(phase=phase):
                with self.assertRaises(auth.ArgoLoginError) as ctx:
                    self.run_login([self.challenge(), *prefix, response(data={'secret': 'body-secret'})])
                self.assertIn(f'fase={phase} passo={step} HTTP=200 location=no motivo=location_assente', str(ctx.exception))
                self.assertNotIn('secret', str(ctx.exception))

    def test_failures_are_sanitized(self):
        cases = [
            ([response(url=auth.LOGIN_URL)], 'challenge_assente'),
            ([self.challenge(), response(403)], 'HTTP=403'),
            ([self.challenge(), response(429)], 'HTTP=429'),
            ([self.challenge(), requests.Timeout('password-secret')], 'timeout'),
            ([self.challenge(), requests.ConnectionError('https://secret')], 'errore_rete'),
            ([self.challenge(), response(302, 'https://untrusted.example/secret')], 'destinazione_non_prevista'),
            ([self.challenge(), response(302, auth.REDIRECT_URI + '?error=secret')], 'oauth_rifiutato'),
            ([self.challenge(), response(302, auth.REDIRECT_URI + '?code=secret&state=secret')], 'state_non_valido'),
            ([self.challenge(), self.callback(), response(data={})], 'access_token_assente'),
            ([self.challenge(), self.callback(), response(data={'access_token': 'secret'}), response(data={'data': []})], 'profilo_token_assente'),
            ([self.challenge()] + [response(302, '/next')] * 11, 'limite_redirect'),
        ]
        for replies, expected in cases:
            with self.subTest(expected=expected):
                with self.assertRaises(auth.ArgoLoginError) as ctx:
                    self.run_login(replies)
                self.assertIn(expected, str(ctx.exception))
                self.assertNotIn('secret', str(ctx.exception))

    def test_invalid_json(self):
        bad = response()
        bad.json.side_effect = ValueError('body-secret')
        with self.assertRaisesRegex(auth.ArgoLoginError, 'json_non_valido'):
            self.run_login([self.challenge(), self.callback(), bad])

    def test_integration_cleans_failed_session_and_preserves_safe_message(self):
        student = {'nome': 'Test', 'codice_scuola': 'school', 'username': 'user', 'password': 'secret'}
        for error in [auth.ArgoLoginError('ARGO-AUTH fase=redirect'), RuntimeError('secret')]:
            with patch.dict(argo_client._sessions, {}, clear=True), patch.object(argo_client, 'ArgoPassword', side_effect=error):
                output = io.StringIO()
                with redirect_stdout(output):
                    self.assertIsNone(argo_client.get_session(student))
                self.assertNotIn('secret', output.getvalue())
                self.assertNotIn('Test', argo_client._sessions)
                if isinstance(error, auth.ArgoLoginError):
                    self.assertIn('ARGO-AUTH fase=redirect', output.getvalue())


if __name__ == '__main__':
    unittest.main()
