from contextlib import closing
from datetime import datetime
import json
import unittest
from unittest.mock import patch

from test_bacheca import DatabaseFixture, STUDENTI
import argo_client
import models
import sync_argo


class IdentitaVotiTest(DatabaseFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        models.init_db()
        self.ora = datetime(2026, 11, 20, 13)
        self.inizio = sync_argo.inizio_anno(self.ora)
        self.st = STUDENTI[0]
        self.nome = self.st['nome']
        self.voto = dict(data='2026-09-25', desMateria='Storia', valore=8, desCommento='Prova')
        self.delta = datetime(2026, 11, 10, 12)
        self.vecchio_stato = dict(ultimo='2026-11-17T12:00:00', inizio=self.inizio.isoformat(), completo=True)
        clock = patch('sync_argo.adesso', return_value=self.ora)
        clock.start()
        self.addCleanup(clock.stop)

    def precedente(self, uids):
        with closing(models.get_db()) as c, c:
            c.execute('INSERT INTO meta(chiave,valore) VALUES (?,?)',
                      (sync_argo._chiave('voti', self.nome), json.dumps(self.vecchio_stato)))
            for uid in uids:
                c.execute('INSERT INTO voti(studente,argo_uid,data,materia,voto,descrizione) VALUES (?,?,?,?,?,?)',
                          (self.nome, uid, '2026-09-25', 'Storia', '8', 'Prova'))

    def righe(self):
        with closing(models.get_db()) as c:
            return [tuple(row) for row in c.execute('SELECT argo_uid,voto FROM voti WHERE studente=? ORDER BY id',
                                                     (self.nome,))]

    def sync(self, risposta):
        with patch('argo_client.dashboard_sync', return_value=risposta):
            self.assertTrue(sync_argo.sincronizza([self.st], ('voti',)))

    def test_lista_ufficiale_anche_vuota_e_ripiego_solo_su_vecchio_formato(self):
        a = dict(self.voto, pk='a')
        sezione = {'voti': [a], 'votiGiornalieri': [self.voto]}
        self.sync(sezione)
        self.sync(sezione)
        self.sync({'voti': [], 'votiGiornalieri': [dict(self.voto, pk='ignorato')]})
        self.assertEqual(self.righe(), [('a','8')])
        self.sync({'votiGiornalieri': [dict(self.voto, pk='b')]})
        self.assertEqual(self.righe(), [('a','8'), ('b','8')])
        with patch('argo_client.fetch_dashboard', return_value={'data': {'dati': [sezione]}}):
            self.assertEqual(len(argo_client.fetch_voti(self.st)), 1)

    def test_storico_corregge_la_copia_anonima_notifica_solo_un_voto_nuovo(self):
        self.precedente(['a', None])
        nuovo = dict(self.voto, pk='b', data='2026-11-20')
        storico = {'voti': [dict(self.voto, pk='a'), nuovo], 'votiGiornalieri': [self.voto]}
        def dati(st, dal):
            return storico if dal == self.inizio else {'voti': [nuovo]}
        with patch('argo_client.dashboard_sync', side_effect=dati) as fetch, \
             patch('notifier.notifica_nuovo_voto') as notifica:
            self.assertTrue(sync_argo.sincronizza([self.st], ('voti',)))
            self.assertEqual([c.args[1] for c in fetch.call_args_list], [self.delta, self.inizio])
            self.assertTrue(sync_argo.sincronizza([self.st], ('voti',)))
            self.assertEqual(fetch.call_count, 3)
            self.assertEqual(notifica.call_count, 1)
            self.assertEqual(self.righe(), [('a','8'), ('b','8')])

    def test_storico_vuoto_o_senza_copia_dimostrata_conserva_anche_righe_identiche(self):
        self.precedente(['a', None, 'b'])
        self.sync({'voti': []})
        self.sync({'voti': [dict(self.voto, pk='a'), dict(self.voto, pk='b')], 'votiGiornalieri': [self.voto]})
        self.assertEqual(self.righe(), [('a','8'), (None,'8'), ('b','8')])

    def test_due_primari_identici_con_alias_ambiguo_non_si_fondono(self):
        self.sync({'voti': [dict(self.voto, pk='a', pkVoto='alias'), dict(self.voto, pk='b', pkVoto='alias')]})
        self.assertEqual(self.righe(), [('a','8'), ('b','8')])

    def test_alias_provati_aggiornano_anche_con_formati_alternati_e_cancellazione(self):
        self.precedente(['a', 'vecchio'])
        self.sync({'voti': [dict(self.voto, pk='a', pkVoto='v1')],
                   'votiGiornalieri': [dict(self.voto, pk='vecchio', pkVoto='v1')]})
        self.assertEqual(self.righe(), [('a','8')])
        self.sync({'votiGiornalieri': [dict(self.voto, pk='vecchio', valore=9, datEvento='2026-11-18')]})
        self.assertEqual(self.righe(), [('a','9')])
        self.sync({'voti': [dict(pkVoto='v1', operazione='D', datEvento='2026-11-19')]})
        self.sync({'voti': [dict(self.voto, pk='a', datEvento='2026-11-17')]})
        self.assertEqual(self.righe(), [])

    def test_due_pk_distinti_smentiscono_un_alias_riutilizzato(self):
        self.sync({'voti': [dict(self.voto, pk='a', pkVoto='b')]})
        self.sync({'voti': [dict(self.voto, pk='a', pkVoto='b'), dict(self.voto, pk='b')]})
        self.assertEqual(self.righe(), [('a','8'), ('b','8')])

    def test_bozza_malformata_non_cancella_un_voto_e_non_avanza_il_cursore(self):
        self.precedente(['a'])
        for valore in ({}, {'valore': []}, {'valore': {}}, {'valore': True}, {'valore': '1e999'}):
            with self.subTest(valore=valore), patch('argo_client.dashboard_sync',
                    return_value={'voti': [dict(pk='a', operazione='U', **valore)]}):
                self.assertFalse(sync_argo.sincronizza([self.st], ('voti',)))
                self.assertEqual(self.righe(), [('a','8')])
                with closing(models.get_db()) as c:
                    cursore = c.execute('SELECT valore FROM meta WHERE chiave=?',
                                        (sync_argo._chiave('voti', self.nome),)).fetchone()[0]
                    self.assertEqual(json.loads(cursore), self.vecchio_stato)

    def test_giudizio_e_segnaposto_espliciti(self):
        for indice, valore in enumerate(('', '  ', 'N', '--', 0)):
            with self.subTest(valore=valore):
                uid = f'voto-{indice}'
                self.sync({'voti': [dict(self.voto, pk=uid, valore='Ottimo', datEvento='2026-11-19')]})
                self.assertEqual(self.righe(), [(uid,'Ottimo')])
                self.sync({'voti': [{'pk': uid, 'valore': valore, 'operazione': 'U'}]})
                self.assertEqual(self.righe(), [])

    def test_recupero_fallito_lascia_il_cursore_e_riprova(self):
        self.precedente(['a', 'vecchio'])
        with patch('argo_client.dashboard_sync', side_effect=[{'voti': []}, argo_client.ArgoSyncError('offline')]):
            self.assertFalse(sync_argo.sincronizza([self.st], ('voti',)))
        with closing(models.get_db()) as c:
            stato = c.execute('SELECT valore FROM meta WHERE chiave=?',
                              (sync_argo._chiave('voti', self.nome),)).fetchone()[0]
            self.assertEqual(json.loads(stato), self.vecchio_stato)
        self.sync({'voti': [dict(self.voto, pk='a', pkVoto='vecchio')]})
        self.assertEqual(self.righe(), [('a','8')])
