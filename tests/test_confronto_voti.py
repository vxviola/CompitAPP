from contextlib import closing
from datetime import datetime
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from test_bacheca import DatabaseFixture, STUDENTI
import argo_client
import confronto_voti
import models
from revisione_voti import gruppi_voti


class ConfrontoTest(DatabaseFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        models.init_db()
        self.st = STUDENTI[0]
        self.nome = self.st['nome']
        self.giorno = '2026-11-13'

    def gruppo(self, uid1='ufficiale-A', uid2='ufficiale-B', giorno=None, materia='Storia'):
        giorno = giorno or self.giorno
        with closing(models.get_db()) as conn, conn:
            conn.executemany("""INSERT INTO voti(studente,data,materia,voto,descrizione,argo_uid)
                VALUES (?,?,?,'8','Prova',?)""", [(self.nome, giorno, materia, uid) for uid in (uid1, uid2)])
            return next(g for g in gruppi_voti(conn, self.nome) if g['data'] == giorno and g['materia'] == materia)

    def voto(self, uid, **altri):
        return dict(dict(pk=uid, data=self.giorno, materia='Storia', valore=8, desCommento='Prova'), **altri)

    def confronta(self, gruppo, voti):
        with patch('argo_client.dashboard_sync', return_value={'voti': voti}) as fetch:
            esito = confronto_voti.confronta_voti(self.st, gruppo)
        fetch.assert_called_once_with(self.st, datetime(2026,8,25), solo_sessione_attiva=True)
        return esito

    def test_due_prove_distinte_con_aspetto_uguale(self):
        gruppo = self.gruppo()
        r = self.confronta(gruppo, [self.voto('ufficiale-A'), self.voto('ufficiale-B')])
        self.assertEqual((r['esito'], r['trovati']), ('distinti', 2))
        self.assertTrue(all('coincidono' in s for s in r['righe'].values()))
        self.assertNotIn('ufficiale', json.dumps(r))

    def test_assenza_di_riscontro_e_anonimi_non_provano_un_duplicato(self):
        gruppo = self.gruppo('ufficiale-A', None)
        r = self.confronta(gruppo, [])
        self.assertEqual((r['esito'], r['trovati']), ('nessun_riscontro',0))
        r = self.confronta(gruppo, [self.voto('ufficiale-A'), self.voto(None)])
        self.assertEqual((r['esito'],r['trovati']), ('incerto',1))
        self.assertIn('Nessun identificativo', r['righe'][gruppo['righe'][1]['id']])

    def test_alias_correzioni_e_ritiri_rispettano_le_versioni(self):
        gruppo = self.gruppo()
        nuova = '2026-11-18T08:10:00'
        vecchia = '2026-11-15T08:10:00'
        r = self.confronta(gruppo, [
            self.voto('ufficiale-A', pkVoto='alias-A', datEvento=vecchia),
            self.voto(None, pkVoto='alias-A', valore=7, datEvento=nuova),
            {'pk':'ufficiale-B', 'operazione':'D', 'datEvento':nuova},
            self.voto('ufficiale-B', datEvento=vecchia)])
        self.assertEqual(r['trovati'],0)
        self.assertIn('diversi', r['righe'][gruppo['righe'][0]['id']])
        self.assertIn('ritiro', r['righe'][gruppo['righe'][1]['id']])
        r = self.confronta(gruppo, [self.voto('ufficiale-B'), {'pk':'ufficiale-B', 'operazione':'D'}])
        self.assertEqual(r['esito'],'incerto')
        self.assertNotIn('ritiro',r['righe'][gruppo['righe'][1]['id']])

    def test_unica_lettura_per_sedici_gruppi_e_errore_di_altro_anno_isolato(self):
        gruppi = [self.gruppo(f'a{i}', f'b{i}', materia=f'Materia {i}') for i in range(16)]
        vecchio = self.gruppo('prec-a','prec-b','2025-11-13')
        def dashboard(st, dal, **kwargs):
            if dal.year == 2025:
                raise argo_client.ArgoSyncError('dato privato','servizio')
            return {'voti': [self.voto(f'a{i}',materia=f'Materia {i}') for i in range(16)]}
        with patch('argo_client.dashboard_sync', side_effect=dashboard) as api:
            r = confronto_voti.confronta_gruppi_voti(self.st, gruppi + [vecchio])
        self.assertEqual(api.call_count,2)
        self.assertEqual({r[g['versione']]['trovati'] for g in gruppi},{1})
        self.assertEqual(r[vecchio['versione']]['esito'],'indisponibile')
        self.assertNotIn('dato privato',str(r))
        with patch('argo_client.dashboard_sync') as api:
            altro = confronto_voti.confronta_voti(STUDENTI[1], gruppi[0])
        self.assertEqual(altro['esito'],'indisponibile')
        api.assert_not_called()

    def test_versione_locale_piu_recente_e_progressivi_incompleti_restano_incerti(self):
        gruppo = self.gruppo()
        with closing(models.get_db()) as conn, conn:
            conn.execute("""INSERT INTO argo_eventi VALUES (?, 'voti','ufficiale-A','2026-11-18T09:00:00',0)""",
                         (self.nome,))
        r = self.confronta(gruppo, [self.voto('ufficiale-A', datEvento='2026-11-14T09:00:00'),
                                    self.voto(None, prgVoto=1)])
        self.assertEqual(r['esito'], 'incerto')
        self.assertIn('verificare',r['righe'][gruppo['righe'][0]['id']])
        with patch('argo_client.dashboard_sync',return_value={'voti':None}):
            self.assertEqual(confronto_voti.confronta_voti(self.st,gruppo)['esito'], 'indisponibile')

    def test_confronto_non_rinnova_o_riseleziona_il_profilo(self):
        gruppo = self.gruppo()
        session = SimpleNamespace(_argo_profiles=[{'token':'A'}, {'token':'B'}],
            _ArgoFamiglia__headers={'x-auth-token':'B'}, _ArgoFamiglia__login_data={'expires_in':3600})
        st = dict(self.st, alunno=2)
        with patch.dict(argo_client._sessions,{self.nome:session}), \
                patch.dict(argo_client._sessioni_creata,{self.nome:1000}), patch('argo_client.time.time',return_value=1200), \
                patch('argo_client.get_session') as login, patch('argo_client._reset_session') as reset, \
                patch('argo_client.requests.post') as post:
            with closing(models.get_db()) as conn:
                prima = list(conn.iterdump())
            post.return_value = Mock(status_code=401)
            self.assertEqual(confronto_voti.confronta_voti(st,gruppo)['esito'],'indisponibile')
            self.assertEqual(post.call_count,1)
            self.assertIs(argo_client._sessions[self.nome],session)
            post.reset_mock()
            self.assertEqual(confronto_voti.confronta_voti(dict(st, alunno=1),gruppo)['esito'],'indisponibile')
            with patch('argo_client.time.time',return_value=8000):
                self.assertEqual(confronto_voti.confronta_voti(st,gruppo)['esito'],'indisponibile')
            post.assert_not_called()
            post.return_value = Mock(status_code=200)
            post.return_value.json.return_value = {'data':{'dati':[{'voti':[], 'parziale':'S'}]}}
            self.assertEqual(confronto_voti.confronta_voti(st,gruppo)['esito'],'indisponibile')
            login.assert_not_called()
            reset.assert_not_called()
            with closing(models.get_db()) as conn:
                self.assertEqual(list(conn.iterdump()), prima)
