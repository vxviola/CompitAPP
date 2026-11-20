import json
import unittest
from contextlib import closing
from unittest.mock import patch

from test_bacheca import DatabaseFixture, STUDENTI
from app import app
import bot
import models
import notifier
import scheduler


class MedieVotiTest(DatabaseFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        models.init_db()
        self.nome = STUDENTI[0]['nome']
        self.client = app.test_client()
        studenti = patch('app.get_studenti', return_value=STUDENTI)
        studenti.start()
        self.addCleanup(studenti.stop)

    def inserisci_voti(self, righe, nome=None):
        with closing(models.get_db()) as conn, conn:
            conn.executemany("INSERT INTO voti(studente,data,materia,voto) VALUES (?,'2026-11-01',?,?)",
                             [(nome or self.nome, materia, valore) for materia, valore in righe])

    def leggi_canali(self):
        with patch.object(scheduler, 'sync_sensori_ha') as pubblica:
            scheduler._aggiorna_sensori(self.nome)
            pubblica.assert_called_once()
            sensori = pubblica.call_args.args[1]
        with patch.object(bot, '_studenti_bot', return_value=[self.nome]), patch.object(bot, 'send_message') as invia:
            bot._cmd_voti('chat-test')
            invia.assert_called_once()
            messaggio = invia.call_args.args[1]
        pagine = []
        for url in ('/', '/voti'):
            risposta = self.client.get(url, query_string={'studente': self.nome})
            self.assertEqual(risposta.status_code, 200)
            pagine.append(risposta.text)
        return *pagine, sensori, messaggio

    def test_solo_giudizi_restano_visibili_senza_colorazione_numerica(self):
        self.inserisci_voti([('Religione', 'Ottimo')])
        self.inserisci_voti([('Storia', '8')], STUDENTI[1]['nome'])
        home, voti, sensori, bot_html = self.leggi_canali()
        for pagina in (home, voti):
            self.assertIn('badge badge-primary">Ottimo</span>', pagina)
            self.assertIn('Nessuna media numerica disponibile', pagina)
        self.assertEqual(sensori['media_voti'], 'N/D')
        self.assertEqual(sensori['dettagli']['voti'][0]['voto'], 'Ottimo')
        self.assertEqual(sensori['dettagli']['medie'], [])
        self.assertIn('Religione: <b>Ottimo</b>', bot_html)
        self.assertNotIn('Storia', bot_html)

    def test_media_locale_su_tutto_archivio_e_medie_ufficiali_prioritarie(self):
        self.inserisci_voti([('Storia', '4,25')] + [('Storia', '8,25')] * 15 + [('Religione', 'Ottimo')])
        home, voti, sensori, bot_html = self.leggi_canali()
        self.assertIn('8,00', home)
        self.assertIn('Medie calcolate dai voti numerici in archivio', voti)
        self.assertEqual(sensori['media_voti'], 8)
        self.assertEqual(sensori['dettagli']['medie'], [{'materia': 'Storia', 'media': 8, 'n': 16, 'fonte': 'UniScuola'}])
        self.assertIn('<b>Storia</b>: 8,00', bot_html)
        self.assertEqual(bot_html.count('<i>('), 8)
        with closing(models.get_db()) as conn, conn:
            conn.execute('INSERT INTO meta (chiave,valore) VALUES (?,?)',
                         ('media_argo:' + self.nome, json.dumps({'generale': '7,40', 'materie': {'Storia': '7,75'}})))
        home, voti, sensori, bot_html = self.leggi_canali()
        self.assertIn('7,40', home)
        self.assertIn('7,75', voti)
        self.assertIn('Medie comunicate da Argo', voti)
        self.assertEqual(sensori['media_voti'], 7.4)
        self.assertEqual(sensori['dettagli']['medie'], [{'materia': 'Storia', 'media': 7.75, 'n': 16, 'fonte': 'Argo'}])
        self.assertIn('<b>Storia</b>: 7,75', bot_html)

    def test_medie_argo_parziali_distinte_dal_calcolo_locale(self):
        self.inserisci_voti([('Storia', '6'), ('Arte', '8,5'), ('Religione', 'Ottimo')])
        with closing(models.get_db()) as conn, conn:
            conn.execute('INSERT INTO meta (chiave,valore) VALUES (?,?)',
                         ('media_argo:' + self.nome, json.dumps({'materie': {'Storia': 7}})))
        home, voti, sensori, bot_html = self.leggi_canali()
        self.assertIn('7,25', home)
        self.assertIn('Media Argo', voti)
        self.assertIn('Dai voti numerici in archivio', voti)
        self.assertEqual(sensori['dettagli']['medie'], [
            {'materia': 'Arte', 'media': 8.5, 'n': 1, 'fonte': 'UniScuola'},
            {'materia': 'Storia', 'media': 7, 'n': 1, 'fonte': 'Argo'}])
        self.assertIn('<b>Arte</b>: 8,50 (UniScuola)', bot_html)
        self.assertIn('<b>Storia</b>: 7,00 (Argo)', bot_html)

    def test_notifica_giudizio_telegram_senza_allarme_e_con_testo_letterale(self):
        with patch.object(notifier, 'send_telegram') as invia:
            notifier.notifica_nuovo_voto('Anna', 'Arte & musica', 'Buono', 'A < B')
            messaggio = invia.call_args.args[0]
        self.assertTrue(messaggio.startswith('📊'))
        self.assertNotIn('Sotto soglia', messaggio)
        self.assertIn('Arte &amp; musica', messaggio)
        self.assertIn('A &lt; B', messaggio)

    def test_copia_esclusa_e_ripristinata_su_tutti_i_canali(self):
        from revisione_voti import escludi_copia, gruppi_voti, ripristina_copia
        self.inserisci_voti([('Storia', '8'), ('Storia', '8'), ('Storia', '5')])
        with closing(models.get_db()) as conn:
            gruppo, = gruppi_voti(conn, self.nome)
            prima, seconda = [r['id'] for r in gruppo['righe']]
            escludi_copia(conn, self.nome, seconda, prima, gruppo['versione'])
        for quanti, media in ((1, 6.5), (2, 7.0)):
            home, voti, sensori, bot_html = self.leggi_canali()
            self.assertEqual(voti.count('class="grades-row"'), quanti + 1)
            self.assertEqual(home.count('class="grades-row"'), quanti + 1)
            self.assertEqual(bot_html.count('Storia: <b>8</b>'), quanti)
            self.assertEqual(sensori['media_voti'], media)
            self.assertEqual(len(sensori['dettagli']['voti']), quanti + 1)
            stats = self.client.get('/api/stats', query_string={'studente': self.nome}).get_json()
            self.assertEqual((stats['totale_voti'], stats['gruppi_voti_uguali']), (quanti + 1, quanti - 1))
            with patch('funzioni.get_studenti', return_value=STUDENTI):
                ricerca = self.client.get('/ricerca', query_string={'studente': self.nome, 'q': 'Storia'}).text
            self.assertEqual(ricerca.count('class="search-result"'), quanti + 1)
            if quanti == 1:
                with closing(models.get_db()) as conn:
                    gruppo, = gruppi_voti(conn, self.nome)
                    ripristina_copia(conn, self.nome, seconda, gruppo['versione'])
