from contextlib import closing
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from test_bacheca import DatabaseFixture
import argo_client
import models
import sync_argo
from app import app


class RevisioneRegistroTest(DatabaseFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        models.init_db()
        self.client = app.test_client()

    def test_appello_corrente_e_archivio_precedente(self):
        studente = {'nome': 'Demo'}
        assenza = {'pk': 'a', 'data': '2026-10-12', 'codEvento': 'A'}
        for sezione, quanti in [
            ({'appello': [assenza], 'assenze': [dict(assenza, pk='vecchio')]}, 1),
            ({'appello': [], 'assenze': [assenza]}, 0),
            ({'assenze': [assenza]}, 1),
        ]:
            with self.subTest(sezione=sezione):
                self.assertEqual(len(sync_argo.normalizza('assenze', sezione)), quanti)
                with patch('argo_client.fetch_dashboard', return_value={'data': {'dati': [sezione]}}):
                    self.assertEqual(len(argo_client.fetch_assenze(studente)), quanti)
        for errata in ({}, {'appello': {}, 'assenze': [assenza]}):
            with self.assertRaises(argo_client.ArgoSyncError):
                sync_argo.normalizza('assenze', errata)

    def test_cambio_profilo_pulisce_solo_i_propri_alias_e_cursori(self):
        with closing(models.get_db()) as conn, conn:
            for nome in ('A_B', 'AXB'):
                conn.execute("INSERT INTO voti_alias VALUES (?, 'prima', 'ora')", (nome,))
                conn.execute("INSERT INTO meta(chiave,valore) VALUES (?, '1')", ('storico:voti:' + nome,))
            models.svuota_studente(conn, 'A_B')
            self.assertEqual([r[0] for r in conn.execute('SELECT studente FROM voti_alias')], ['AXB'])
            self.assertEqual([r[0] for r in conn.execute("SELECT chiave FROM meta WHERE chiave LIKE 'storico:%'")],
                             ['storico:voti:AXB'])
        self.assertEqual(self.client.post('/api/reset-db').status_code, 200)
        with closing(models.get_db()) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM voti_alias').fetchone()[0], 0)

    def test_statistiche_contano_i_gruppi_solo_per_lo_studente_selezionato(self):
        with closing(models.get_db()) as conn, conn:
            for nome, descrizione in [('A', None), ('A', ''), ('A', 'Orale'), ('B', '')]:
                conn.execute("INSERT INTO voti(studente,data,materia,voto,descrizione) "
                             "VALUES (?, '2026-10-12', 'Storia', '8', ?)", (nome, descrizione))
        for nome, totali, gruppi in [('A', 3, 1), ('B', 1, 0)]:
            dati = self.client.get('/api/stats', query_string={'studente': nome}).get_json()
            self.assertEqual((dati['totale_voti'], dati['gruppi_voti_uguali']), (totali, gruppi))

    def test_diagnostica_prefissi_espone_solo_indicatori(self):
        self.assertEqual(self.client.get('/debug-headers', headers={'X-Ingress-Path': '/test'}).get_json(),
                         {'ingress_path_presente': True, 'forwarded_prefix_presente': False,
                          'script_root_presente': False})

    def test_copia_prima_del_recupero_coerente_e_conservata_ai_riavvii(self):
        backup = Path(models.DB_PATH + '.prima-voti-2.4.11.sqlite')
        self.assertFalse(backup.exists())
        with closing(models.get_db()) as conn, conn:
            conn.execute('DROP TABLE voti_alias')  # schema della versione 2.4.10
            conn.execute("INSERT INTO voti(studente,data,materia,voto) "
                         "VALUES ('A','2026-11-01','Storia','7')")
        models.init_db()
        with closing(models.get_db()) as conn, conn:
            conn.execute("UPDATE voti SET voto='8'")
        models.init_db()
        with closing(sqlite3.connect(backup)) as copia:
            self.assertEqual(copia.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(copia.execute('SELECT voto FROM voti').fetchone()[0], '7')
            self.assertIsNone(copia.execute("SELECT 1 FROM sqlite_master WHERE name='voti_alias'").fetchone())
