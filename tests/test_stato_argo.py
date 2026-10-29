import os
import unittest
from unittest.mock import patch, Mock

import requests
from test_bacheca import DatabaseFixture, STUDENTI
import models
import sync_state
import ha_client
from app import app


class StatoTest(DatabaseFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        models.init_db()
        self.notice = patch.object(ha_client, 'avviso_sincronizzazione').start()
        self.addCleanup(patch.stopall)

    def test_error_persists_during_retry_until_complete_success(self):
        sync_state.inizia()
        sync_state.termina(['A', 'B'])
        last = sync_state.leggi('A')['ultimo_successo']
        sync_state.inizia()
        sync_state.errore('A', 'accesso')
        sync_state.errore('A')
        self.assertEqual(sync_state.leggi('A')['motivo'], 'accesso')
        sync_state.termina(['A', 'B'])
        self.assertEqual(sync_state.leggi('A')['ultimo_successo'], last)
        self.assertEqual(self.notice.call_args.args[0][0]['motivo'], 'accesso')
        sync_state.inizia()
        try:
            self.assertEqual(sync_state.leggi('A')['esito'], 'errore')
            self.assertTrue(sync_state.leggi('A')['in_corso'])
        finally:
            sync_state.termina(['A', 'B'])
        self.assertEqual(sync_state.leggi('A')['esito'], 'ok')
        self.assertIsNone(sync_state.leggi('A')['motivo'])

    def test_configuration_is_not_proof_of_connection(self):
        with patch('app.get_studenti', return_value=STUDENTI):
            client = app.test_client()
            html = client.get('/configurazione').text
            self.assertNotIn('Connesso come', html)
            self.assertIn('Collegamento da verificare', html)
            sync_state.inizia()
            sync_state.errore(STUDENTI[0]['nome'], 'accesso')
            sync_state.termina([s['nome'] for s in STUDENTI])
            sync_state.inizia()
            try:
                html = client.get('/configurazione').text
                self.assertIn('sync-info is-error', html)
                self.assertIn('Errore di accesso Argo', html)
                self.assertNotIn('sync-info is-ok', html)
            finally:
                sync_state.termina([s['nome'] for s in STUDENTI])

    def test_connection_test_reports_failed_login_for_selected_student(self):
        with patch('app.get_studenti', return_value=STUDENTI), \
                patch('argo_client.get_session', return_value=None) as session, \
                patch('argo_client._reset_session'):
            r = app.test_client().post('/addon/api/test-connessione?studente=Luca')
            self.assertFalse(r.json['ok'])
            self.assertEqual(session.call_args.args[0]['nome'], 'Luca')


class NotificationTest(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'SUPERVISOR_TOKEN': 'test-secret'})
        self.env.start()
        self.addCleanup(self.env.stop)
        for name, value in [('_ultimo_avviso_sync', None), ('_slug', 'test_uniscuola')]:
            p = patch.object(ha_client, name, value)
            p.start(); self.addCleanup(p.stop)

    def test_one_notice_until_all_profiles_recover(self):
        failed = [{'esito': 'errore', 'motivo': 'accesso'}, {'esito': 'ok'}]
        with patch.object(ha_client.requests, 'post') as post:
            ha_client.avviso_sincronizzazione(failed)
            ha_client.avviso_sincronizzazione(failed)
            self.assertEqual(post.call_count, 1)
            payload = post.call_args.kwargs['json']
            self.assertIn('accesso Argo fallito', payload['title'])
            self.assertNotIn('test-secret', str(payload))
            ha_client.avviso_sincronizzazione([{'esito': 'ok'}, {}])
            self.assertEqual(post.call_count, 1)
            ha_client.avviso_sincronizzazione([{'esito': 'ok'}, {'esito': 'ok'}])
            self.assertTrue(post.call_args.args[0].endswith('/dismiss'))
            self.assertEqual(post.call_args.kwargs['json']['notification_id'], payload['notification_id'])

    def test_failed_delivery_is_retried_and_restart_reconciles(self):
        state = [{'esito': 'errore'}]
        with patch.object(ha_client.requests, 'post', side_effect=requests.ConnectionError('secret')) as post:
            ha_client.avviso_sincronizzazione(state)
            ha_client.avviso_sincronizzazione(state)
            self.assertEqual(post.call_count, 2)
        with patch.object(ha_client.requests, 'post') as post:
            ha_client.avviso_sincronizzazione([{'esito': 'ok'}])
            self.assertTrue(post.call_args.args[0].endswith('/dismiss'))

    def test_without_supervisor_no_network(self):
        with patch.dict(os.environ, {'SUPERVISOR_TOKEN': ''}), patch.object(ha_client.requests, 'post') as post:
            ha_client.avviso_sincronizzazione([{'esito': 'errore'}])
            post.assert_not_called()
