"""Transport contract from official Famiglia WEB plus real V2/V3 probe shapes."""
from datetime import datetime
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'compitapp'))
import argo_auth
import argo_client
from argo_backend import ENDPOINT, api_headers
import test_argo_auth as auth_tests


class WebBackendTest(unittest.TestCase):
    def test_login_and_profile_selection_share_single_profiles_response(self):
        helper = auth_tests.LoginTest()
        profiles = [{'token': 'first', 'codMin': 'school1'}, {'token': 'second', 'codMin': 'school2'}]
        obj, transport = helper.run_login([helper.challenge(), helper.callback(),
            auth_tests.response(data={'access_token': 'oauth'}), auth_tests.response(data={'data': profiles})])
        call = transport.request.call_args
        self.assertEqual(call.args, ('POST', ENDPOINT + 'login'))
        self.assertEqual(call.kwargs['json'], {})
        self.assertEqual(call.kwargs['headers']['os-type'], 'WEB')
        self.assertFalse(call.kwargs['allow_redirects'])
        with patch('argo_client.requests.post') as post, patch('argo_client._controlla_cambio_profilo'):
            argo_client._scegli_profilo(obj, {'nome': 'Synthetic', 'alunno': 2})
        post.assert_not_called()
        self.assertEqual(obj._ArgoFamiglia__headers['x-auth-token'], 'second')
        self.assertEqual(obj._ArgoFamiglia__headers['x-cod-min'], 'school2')

    def test_all_dashboard_paths_use_web_contract(self):
        obj = object.__new__(argo_auth.ArgoPassword)
        obj._ArgoFamiglia__headers = api_headers('oauth', 'school', 'selected')
        r = Mock(status_code=200)
        r.json.return_value = {'success': True, 'data': {'dati': [{'registro': [], 'voti': [], 'promemoria': []}]}}
        student = {'nome': 'Synthetic'}
        with patch('argo_client.get_session', return_value=obj), patch('argo_client.requests.post', return_value=r) as post:
            obj.dashboard(False)
            obj.getCompitiByDate()
            argo_client._dashboard_dal(student, 4)
            argo_client.dashboard_sync(student, datetime(2026, 11, 17, 10, 13))
        self.assertEqual(post.call_count, 4)
        for call in post.call_args_list:
            self.assertEqual(call.args[0], ENDPOINT + 'dashboard/dashboard')
            self.assertIsNone(call.kwargs['json']['opzioni'])
            self.assertFalse(call.kwargs['allow_redirects'])
            self.assertEqual(call.kwargs['headers']['x-auth-token'], 'selected')
        self.assertEqual(post.call_args.kwargs['json']['dataultimoaggiornamento'], '2026-11-17 10:13:00')

    def test_spid_keeps_refresh_then_uses_same_web_profiles_and_dashboard(self):
        profiles = [{'token': 'selected'}]
        with patch('spid_auth.rinnova', return_value={'access_token': 'oauth'}) as refresh, \
             patch('argo_client.get_profiles', return_value=profiles) as fetch:
            obj = argo_client.ArgoSpid('school', 'Synthetic')
        refresh.assert_called_once_with('Synthetic')
        fetch.assert_called_once_with({'access_token': 'oauth'})
        self.assertEqual(obj._argo_profiles, profiles)
        self.assertEqual(obj._ArgoFamiglia__headers, api_headers('oauth', 'school', 'selected'))
        self.assertIsInstance(obj, argo_auth.ArgoWebSession)

    def test_profile_failure_does_not_create_an_authenticated_session(self):
        helper = auth_tests.LoginTest()
        with self.assertRaises(argo_auth.ArgoLoginError):
            helper.run_login([helper.challenge(), helper.callback(), auth_tests.response(data={'access_token': 'oauth'}),
                              auth_tests.response(503)])


if __name__ == '__main__':
    unittest.main()
