from datetime import date
from html import unescape
import json
from pathlib import Path
import re
import sys
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'compitapp'))
from app import app
import models
import scheduler
import sync_state
from test_bacheca import DatabaseFixture, STUDENTI, ALLEGATO


class DashboardTest(DatabaseFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        models.init_db()
        self.client = app.test_client()
        p = patch('app.get_studenti', return_value=STUDENTI)
        p.start()
        self.addCleanup(p.stop)

    def test_palette_per_figlio_persistente_e_prefissi_ingress(self):
        from preferenze import palette_studente
        for prefix in ('', '/addon', '/app/addon', '/api/hassio_ingress/token'):
            r = self.client.post(prefix + '/api/palette?studente=Luca', json={'palette': 'azzurro'})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(palette_studente('Luca'), 'azzurro')
            self.assertEqual(palette_studente('Anna & Leo'), 'salvia')
            html = self.client.get(prefix + '/?studente=Luca').text
            self.assertIn('data-palette="azzurro"', html)
            self.assertIn('Stile per Luca', html)
        self.client.post('/api/palette?studente=Anna+%26+Leo', json={'palette': 'rosa'})
        self.assertEqual(palette_studente('Anna & Leo'), 'rosa')
        self.assertEqual(palette_studente('Luca'), 'azzurro')

    def test_palette_rifiuta_stili_o_studenti_non_validi(self):
        for payload in ({'palette': '<script>'}, {'palette': None}, [], {}):
            self.assertEqual(self.client.post('/api/palette?studente=Luca', json=payload).status_code, 400)
        self.assertEqual(self.client.post('/api/palette?studente=inesistente', json={'palette': 'rosa'}).status_code, 404)

    def test_sensori_mantengono_entita_e_pubblicano_nome_e_palette(self):
        import notifier
        from preferenze import salva_palette
        salva_palette('Luca', 'azzurro')
        with patch.object(notifier, 'SUPERVISOR_TOKEN', 'test'), patch.object(notifier.requests, 'post') as post:
            notifier.sync_sensori_ha('Luca', {'compiti_oggi': 2})
            self.assertEqual(post.call_count, 6)
            for call in post.call_args_list:
                self.assertIn('/sensor.compitapp_luca_', call.args[0])
                attrs = call.kwargs['json']['attributes']
                self.assertEqual(attrs['palette'], 'azzurro')
                self.assertTrue(attrs['friendly_name'].startswith('UniScuola Luca'))

    def test_tutte_le_pagine_e_i_prefissi(self):
        for prefix in ('', '/addon', '/app/addon', '/api/hassio_ingress/token'):
            for page in ('/', '/bacheca', '/voti', '/calendario', '/orario', '/assenze', '/argomenti', '/configurazione'):
                with self.subTest(prefix=prefix, page=page):
                    r = self.client.get(prefix + page, query_string={'studente': 'Luca'})
                    self.assertEqual(r.status_code, 200)
                    self.assertIn('Luca', r.text)
                    self.assertIn(prefix + '/static/dashboard.css', r.text)
                    self.assertIn(prefix + '/bacheca?studente=Luca', unescape(r.text))
                    self.assertNotIn('fonts.googleapis.com', r.text)

    def test_ingress_con_path_rimosso_dal_proxy(self):
        r = self.client.get('/bacheca?studente=Luca', headers={'X-Ingress-Path': '/api/hassio_ingress/reale'})
        self.assertIn('/api/hassio_ingress/reale/static/dashboard.js', r.text)
        self.assertIn('/api/hassio_ingress/reale/voti?studente=Luca', unescape(r.text))

    def test_ignora_prefisso_esterno(self):
        r = self.client.get('/', headers={'X-Ingress-Path': '//example.invalid'})
        self.assertNotIn('example.invalid', r.text)

    def test_errore_download_conserva_il_percorso_ingress(self):
        identita = self.inserisci()
        with patch('app.link_allegato_bacheca', side_effect=RuntimeError('simulato')):
            r = self.client.get(f'/bacheca/{identita}/allegati/0',
                                query_string={'studente': 'Anna & Leo'},
                                headers={'X-Ingress-Path': '/api/hassio_ingress/reale'})
        self.assertEqual(r.status_code, 502)
        self.assertIn('/api/hassio_ingress/reale/bacheca?studente=', r.text)

    def test_asset_prefissati_e_nessun_accesso_a_file_esterni(self):
        for prefix in ('', '/addon', '/app/addon', '/api/hassio_ingress/token'):
            r = self.client.get(prefix + '/static/dashboard.css')
            self.assertEqual(r.status_code, 200)
            r.close()
        self.assertEqual(self.client.get('/addon/static/../../models.py').status_code, 404)

    def test_studente_non_valido_usa_il_primo(self):
        r = self.client.get('/?studente=inesistente')
        self.assertIn('Uno spazio per Anna &amp; Leo.', r.text)
        self.assertNotIn('studente=inesistente', r.text)

    def test_home_mostra_compiti_avvisi_e_allegati(self):
        self.inserisci()
        conn = models.get_db()
        conn.execute('INSERT INTO compiti (studente,data,materia,testo) VALUES (?,?,?,?)',
                     ('Anna & Leo', date.today().isoformat(), 'Italiano', 'Leggere il racconto'))
        conn.commit()
        conn.close()
        r = self.client.get('/')
        self.assertIn('Leggere il racconto', r.text)
        self.assertIn('Circolare', r.text)
        self.assertIn('1 allegato', r.text)

    def test_testo_della_scuola_viene_escapato(self):
        conn = models.get_db()
        conn.execute('INSERT INTO bacheca (studente,titolo,testo,allegati) VALUES (?,?,?,?)',
                     ('Anna & Leo', '<script>alert(1)</script>', '<img src=x onerror=alert(1)>', json.dumps([ALLEGATO])))
        conn.commit()
        conn.close()
        r = self.client.get('/bacheca')
        self.assertIn('&lt;script&gt;', r.text)
        self.assertNotIn('<script>alert(1)</script>', r.text)
        self.assertNotIn('<img src=x', r.text)

    def test_syncronizzazione_avviata_in_background_e_non_duplicata(self):
        gate = threading.Event()
        done = threading.Event()

        def attendi():
            gate.wait(timeout=3)

        originale = sync_state.termina

        def termina(*args, **kwargs):
            try:
                return originale(*args, **kwargs)
            finally:
                done.set()

        with patch('scheduler.get_studenti', return_value=STUDENTI), \
                patch('scheduler._ciclo_sync', side_effect=attendi), \
                patch('sync_state.termina', side_effect=termina):
            try:
                r = self.client.post('/api/sync')
                self.assertEqual(r.status_code, 202)
                self.assertTrue(self.client.get('/api/sync-status').json['in_corso'])
                self.assertEqual(self.client.post('/addon/api/sync').status_code, 409)
                gate.set()
                self.assertTrue(done.wait(timeout=3))
            finally:
                gate.set()
                done.wait(timeout=3)
        stato = self.client.get('/api/sync-status').json
        self.assertFalse(stato['in_corso'])
        self.assertEqual(stato['esito'], 'ok')
        self.assertTrue(stato['ultimo_successo'])

    def test_errore_sync_conserva_ultimo_successo(self):
        conn = models.get_db()
        conn.execute('INSERT INTO meta (chiave,valore) VALUES (?,?)',
                     ('sync_ui:Luca', json.dumps({'ultimo_successo': '2026-10-25T12:00:00+01:00'})))
        conn.commit()
        conn.close()
        self.assertTrue(sync_state.inizia())
        sync_state.errore('Luca')
        sync_state.termina(['Luca', 'Anna & Leo'])
        luca = self.client.get('/addon/api/sync-status?studente=Luca').json
        self.assertEqual(luca['esito'], 'errore')
        self.assertEqual(luca['ultimo_successo'], '2026-10-25T12:00:00+01:00')
        self.assertEqual(self.client.get('/api/sync-status?studente=Anna+%26+Leo').json['esito'], 'ok')

    def test_api_sync_senza_studenti_non_avvia_richieste(self):
        with patch('app.get_studenti', return_value=[]), patch('scheduler.avvia_sync_manuale') as avvia:
            self.assertEqual(self.client.post('/api/sync').status_code, 400)
            avvia.assert_not_called()

    def test_orario_sabato_senza_lezioni_seleziona_un_giorno_disponibile(self):
        class Sabato(date):
            @classmethod
            def today(cls):
                return cls(2026, 10, 31)
        conn = models.get_db()
        conn.execute('INSERT INTO orario (studente,giorno,ora,materia) VALUES (?,?,?,?)',
                     ('Anna & Leo', 0, 1, 'Italiano'))
        conn.commit()
        conn.close()
        with patch('app.date', Sabato):
            r = self.client.get('/orario')
        self.assertEqual(r.status_code, 200)
        self.assertIn('showDay(0);', r.text)

    def test_fallimento_del_ciclo_rilascia_il_blocco(self):
        with patch('scheduler.get_studenti', return_value=STUDENTI), \
                patch('scheduler._ciclo_sync', side_effect=RuntimeError('simulato')):
            self.assertFalse(scheduler.sync_tutto())
        self.assertFalse(sync_state.leggi('Luca')['in_corso'])
        self.assertEqual(sync_state.leggi('Luca')['esito'], 'errore')
        self.assertTrue(sync_state.inizia())
        sync_state.termina([])


if __name__ == '__main__':
    unittest.main()
