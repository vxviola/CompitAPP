import unittest
from unittest.mock import Mock, patch
import ha_client


class NotifyEntityTest(unittest.TestCase):
    def response(self, data):
        return Mock(json=Mock(return_value=data))

    def test_discovery_motorola_legacy_and_same_name_are_distinct(self):
        actions = [{'domain': 'notify', 'services': {'send_message': {}, 'mobile_app_demo': {}, 'mobile_app': {}}}]
        states = [
            {'entity_id': 'notify.motorola_razn_60_ultra', 'state': 'unknown', 'attributes': {'friendly_name': 'Motorola'}},
            {'entity_id': 'notify.mobile_app_demo', 'state': '2026-10-30', 'attributes': {}},
            {'entity_id': 'sensor.other', 'state': '1'},
            {'entity_id': 'notify.offline', 'state': 'unavailable'},
        ]
        with patch('ha_client._headers', return_value={}), patch('ha_client.requests.get', side_effect=[self.response(actions), self.response(states)]) as get:
            result = ha_client.servizi()
        self.assertEqual({s['id'] for s in result}, {'notify.mobile_app_demo', 'entity:notify.mobile_app_demo', 'entity:notify.motorola_razn_60_ultra'})
        self.assertTrue(get.call_args.args[0].endswith('/api/states'))
        self.assertIn('Motorola (entità)', [s['nome'] for s in result])

    def test_older_ha_does_not_require_states(self):
        actions = [{'domain': 'notify', 'services': {'mobile_app_demo': {}}}]
        with patch('ha_client._headers', return_value={}), patch('ha_client.requests.get', return_value=self.response(actions)) as get:
            self.assertEqual(ha_client.servizi()[0]['id'], 'notify.mobile_app_demo')
        self.assertEqual(get.call_count, 1)

    def test_failed_entity_discovery_is_not_silently_an_empty_list(self):
        actions = [{'domain': 'notify', 'services': {'send_message': {}}}]
        with patch('ha_client._headers', return_value={}), patch('ha_client.requests.get', side_effect=[self.response(actions), ha_client.requests.Timeout()]):
            with self.assertRaises(ha_client.requests.Timeout):
                ha_client.servizi()

    def test_entity_uses_explicit_target_and_portable_payload(self):
        with patch('ha_client._headers', return_value={}), patch('ha_client.requests.post') as post, patch('ha_client._apertura') as opening:
            self.assertTrue(ha_client._invia_dispositivo('entity:notify.motorola_razn_60_ultra', 'Titolo', 'Messaggio', '/'))
        self.assertEqual(post.call_args.args[0], 'http://supervisor/core/api/services/notify/send_message')
        self.assertEqual(post.call_args.kwargs['json'], {'entity_id': 'notify.motorola_razn_60_ultra', 'message': 'Titolo\nMessaggio'})
        opening.assert_not_called()

    def test_entity_failures_do_not_block_legacy_service(self):
        cfg = {'attive': True, 'eventi': ['voti'], 'servizi': ['entity:notify.motorola', 'notify.mobile_app_iphone']}
        with patch('ha_client.configurazione', return_value=cfg), patch('ha_client._headers', return_value={}), patch('ha_client._apertura', return_value='/app/demo'), patch('ha_client.requests.post', side_effect=[ha_client.requests.HTTPError(), Mock()]) as post:
            results = ha_client.invia_dettaglio('Studente', 'voti', 'Titolo', 'Messaggio')
        self.assertEqual(results, {'entity:notify.motorola': False, 'notify.mobile_app_iphone': True})
        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args.kwargs['json']['data']['url'], '/app/demo')

    def test_invalid_entity_targets_are_rejected_before_any_request(self):
        for target in ['entity:light.lamp', 'entity:notify.*', 'entity:notify.one,notify.two', 'entity:notify.one/other', 'notify.send_message']:
            with self.subTest(target=target), patch('ha_client.requests.post') as post:
                with self.assertRaises(ValueError):
                    ha_client._destinatari({'servizi': [target]})
                self.assertFalse(ha_client._invia_dispositivo(target, 'Title', 'Message', '/'))
                post.assert_not_called()
