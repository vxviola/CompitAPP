import json
import unittest
from contextlib import closing
from datetime import datetime
from unittest.mock import patch

from test_bacheca import DatabaseFixture, STUDENTI
import argo_client
import models
import sync_argo


class RecuperoLinkTest(DatabaseFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        models.init_db()
        self.studente = STUDENTI[0]
        self.nome = self.studente['nome']
        self.ora = datetime(2026, 11, 20, 15)
        self.inizio = sync_argo.inizio_anno(self.ora)
        self.incrementale = datetime(2026, 11, 10, 12)
        self.precedente = dict(ultimo='2026-11-17T11:00:00+00:00', inizio=self.inizio.isoformat(), completo=True)
        self.msg = dict(pk='b1', data='2026-09-30', titolo='Comunicazione', url='https://example.org/documento')
        with closing(models.get_db()) as conn, conn:
            for cat in ('voti', 'bacheca'):
                conn.execute('INSERT INTO meta(chiave,valore) VALUES (?,?)',
                             (sync_argo._chiave(cat, self.nome), json.dumps(self.precedente)))

    def cursore(self, cat):
        with closing(models.get_db()) as conn:
            return json.loads(conn.execute('SELECT valore FROM meta WHERE chiave=?',
                              (sync_argo._chiave(cat, self.nome),)).fetchone()[0])

    def test_recupero_una_volta_per_studente_conserva_lettura_e_isola_le_altre_categorie(self):
        with closing(models.get_db()) as conn, conn:
            rid = conn.execute('''INSERT INTO bacheca(studente,argo_uid,uid,letta,preferito)
                VALUES (?,?,?,1,1)''', (self.nome, 'b1', 'b1')).lastrowid
        nuovo = dict(self.msg, pk='b3', data='2026-11-20', titolo='Comunicazione nuova')
        storico = {'voti': [{'pk': 'vecchio', 'datGiorno': '2026-09-25','valore': 8}],
                   'bacheca': [self.msg, dict(self.msg, pk='b2'), nuovo]}
        def dati(studente, dal):
            return storico if dal == self.inizio else {'voti': [], 'bacheca': [nuovo]}
        with patch('sync_argo.adesso', return_value=self.ora), \
             patch('argo_client.dashboard_sync', side_effect=dati) as fetch, \
             patch('notifier.notifica_bacheca') as avviso:
            self.assertTrue(sync_argo.sincronizza([self.studente], ('voti','bacheca')))
            self.assertEqual([c.args[1] for c in fetch.call_args_list], [self.incrementale, self.inizio])
            fetch.reset_mock()
            self.assertTrue(sync_argo.sincronizza([self.studente], ('voti','bacheca')))
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(avviso.call_count, 1)
            self.assertEqual(avviso.call_args.args[1], nuovo['titolo'])
        with closing(models.get_db()) as conn:
            row = conn.execute('SELECT id,letta,preferito,url FROM bacheca WHERE argo_uid=?', ('b1',)).fetchone()
            self.assertEqual(tuple(row), (rid,1,1,self.msg['url']))
            self.assertEqual(conn.execute('SELECT count(*) FROM voti').fetchone()[0], 0)
        self.assertEqual(self.cursore('bacheca')['link_bacheca'], 1)

    def test_scuola_nuovo_anno_o_profilo_nuovo_una_sola_lettura_silenziosa(self):
        prossimo = datetime(2027, 9, 1, 9)
        with patch('sync_argo.adesso', return_value=prossimo), \
             patch('argo_client.dashboard_sync', return_value={'bacheca': []}) as fetch:
            self.assertTrue(sync_argo.sincronizza(STUDENTI, ('bacheca',)))
            self.assertEqual([c.args for c in fetch.call_args_list], [
                (st, datetime(2027, 8, 25)) for st in STUDENTI])

    def test_replay_non_riuscito_non_consuma_marcatore_o_cursore(self):
        with patch('sync_argo.adesso', return_value=self.ora), \
             patch('argo_client.dashboard_sync', side_effect=[{'voti': [], 'bacheca': []},
                      argo_client.ArgoSyncError('offline','rete')]):
            self.assertFalse(sync_argo.sincronizza([self.studente], ('bacheca','voti')))
        self.assertEqual(self.cursore('bacheca'), self.precedente)
        self.assertEqual(self.cursore('voti')['ultimo'], self.ora.isoformat())

    def test_link_cambiato_senza_uid_su_messaggio_univoco_non_duplica(self):
        msg = dict(self.msg)
        del msg['pk']
        with patch('sync_argo.adesso', return_value=self.ora), \
             patch('argo_client.dashboard_sync', return_value={'bacheca':[msg]}):
            with closing(models.get_db()) as conn, conn:
                rid = conn.execute('''INSERT INTO bacheca(studente,data,titolo,letta)
                    VALUES (?,?,?,1)''',(self.nome,msg['data'],msg['titolo'])).lastrowid
            self.assertTrue(sync_argo.sincronizza([self.studente], ('bacheca',)))
            msg['url'] = 'https://example.org/sostituzione'
            self.assertTrue(sync_argo.sincronizza([self.studente], ('bacheca',)))
        with closing(models.get_db()) as conn:
            rows = conn.execute('SELECT id,letta,url FROM bacheca').fetchall()
            self.assertEqual([tuple(row) for row in rows], [(rid,1,msg['url'])])
