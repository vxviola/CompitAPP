import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'compitapp'))

import allegati
import argo_client
import models
import scheduler
from app import app

STUDENTI = [{'nome': 'Anna & Leo', 'codice_scuola': 'TEST', 'username': 'test'},
            {'nome': 'Luca', 'codice_scuola': 'TEST', 'username': 'test'}]
ALLEGATO = {'uid': 'file-1', 'nome': 'Circolare è.pdf', 'descrizione': 'Programma', 'tipo': 'bacheca'}


class DatabaseFixture:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = patch.object(models, 'DB_PATH', str(Path(self.tmp.name) / 'test.db'))
        p.start()
        self.addCleanup(p.stop)

    def inserisci(self, nome=STUDENTI[0]['nome'], uid='msg-1', allegato=ALLEGATO):
        conn = models.get_db()
        try:
            cursor = conn.execute('INSERT INTO bacheca (studente,uid,titolo,data,allegati) VALUES (?,?,?,?,?)',
                                  (nome, uid, 'Circolare', '2026-10-26', json.dumps([allegato])))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()


class DatabaseTest(DatabaseFixture, unittest.TestCase):
    def test_migrazione_conserva_dati_e_accetta_avviso_per_due_figli(self):
        conn = models.get_db()
        conn.execute('''CREATE TABLE bacheca (id INTEGER PRIMARY KEY AUTOINCREMENT,
            studente TEXT NOT NULL DEFAULT 'default', data TEXT, titolo TEXT,
            testo TEXT, mittente TEXT, uid TEXT UNIQUE, notificato INTEGER DEFAULT 0,
            creato_il TEXT DEFAULT (datetime('now','localtime')))''')
        conn.execute("INSERT INTO bacheca (id,studente,uid,titolo,notificato) VALUES (7,'Anna & Leo','msg-1','Esistente',1)")
        conn.commit()
        conn.close()
        models.init_db()
        models.init_db()
        conn = models.get_db()
        r = conn.execute('SELECT * FROM bacheca WHERE id=7').fetchone()
        self.assertEqual((r['titolo'], r['notificato'], r['allegati']), ('Esistente', 1, '[]'))
        conn.close()
        self.inserisci('Luca')
        with self.assertRaises(sqlite3.IntegrityError):
            self.inserisci('Luca')

    def test_sync_aggiorna_allegati_senza_duplicati_o_notifiche(self):
        models.init_db()
        self.inserisci(allegato=dict(ALLEGATO, uid='vecchio'))
        msg = {'uid': 'msg-1', 'titolo': 'Circolare', 'data': '2026-10-26', 'allegati': [ALLEGATO]}
        with patch.object(scheduler, 'get_studenti', return_value=STUDENTI), \
                patch.object(scheduler, 'fetch_dashboard', return_value={'data': {'dati': []}}), \
                patch.object(scheduler, 'fetch_bacheca', return_value=[msg]), \
                patch.object(scheduler, 'notifica_bacheca') as notifica:
            scheduler.sync_bacheca()
            scheduler.sync_bacheca()
            notifica.assert_not_called()
        conn = models.get_db()
        righe = conn.execute('SELECT * FROM bacheca').fetchall()
        self.assertEqual(len(righe), 2)
        self.assertTrue(all(json.loads(r['allegati']) == [ALLEGATO] for r in righe))
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM meta WHERE chiave LIKE 'storico:bacheca_allegati:%'").fetchone()[0], 2)
        conn.close()

    def test_sync_rimuove_avvisi_ritirati(self):
        models.init_db()
        self.inserisci()
        self.inserisci('Luca')
        with patch.object(scheduler, 'get_studenti', return_value=STUDENTI[:1]), \
                patch.object(scheduler, '_prepara', return_value=(7, False)), \
                patch.object(scheduler, 'fetch_bacheca', return_value=[{'uid': 'msg-1', 'eliminato': True}]):
            scheduler.sync_bacheca()
        conn = models.get_db()
        self.assertEqual([r['studente'] for r in conn.execute('SELECT * FROM bacheca')], ['Luca'])
        conn.close()


class ParsingTest(unittest.TestCase):
    def test_lista_allegati_normalizzata_senza_url_temporanei(self):
        msg = argo_client._msg_bacheca({'pk': 'msg', 'messaggio': 'Test', 'listaAllegati': [
            {'pk': 'file-1', 'nomeFile': 'Circolare è.pdf', 'descrizioneFile': 'Programma',
             'url': 'https://segreto'}, None, {}]})
        self.assertEqual(msg['allegati'], [ALLEGATO])
        self.assertEqual(argo_client._msg_bacheca({'listaAllegati': None})['allegati'], [])

    def test_file_bacheca_personale(self):
        msg = argo_client._msg_bacheca({'pk': 'personale', 'nomeFile': 'Pagella.pdf'}, 'alunno')
        self.assertEqual(msg['allegati'][0]['uid'], 'personale')
        self.assertEqual(msg['allegati'][0]['tipo'], 'alunno')

    def test_json_corrotto_non_rompe_la_pagina(self):
        for valore in ('non json', '{}', 'null', '[null, {}]'):
            self.assertEqual(allegati.leggi_allegati(valore), [])


class ArgoTest(unittest.TestCase):
    def test_richiesta_link_con_sessione_dello_studente(self):
        session = Mock(_ArgoFamiglia__headers={'x-auth-token': 'privato'})
        with patch.object(argo_client, 'get_session', return_value=session) as get_session, \
                patch.object(argo_client.requests, 'post') as post:
            post.return_value.json.return_value = {'success': True, 'url': 'https://www.portaleargo.it/file'}
            self.assertEqual(argo_client.link_allegato_bacheca(STUDENTI[1], ALLEGATO), 'https://www.portaleargo.it/file')
            get_session.assert_called_once_with(STUDENTI[1])
            self.assertTrue(post.call_args.args[0].endswith('/downloadallegatobacheca'))
            self.assertEqual(post.call_args.kwargs['json'], {'uid': 'file-1'})

    def test_bacheca_personale_usa_pk_scheda_del_profilo(self):
        with patch.object(argo_client, 'get_session', return_value=Mock()), \
                patch.object(argo_client.requests, 'get') as get, \
                patch.object(argo_client.requests, 'post') as post:
            get.return_value.json.return_value = {'data': {'scheda': {'pk': 'scheda-secondo-figlio'}}}
            post.return_value.json.return_value = {'url': 'https://www.portaleargo.it/file'}
            argo_client.link_allegato_bacheca(STUDENTI[1], dict(ALLEGATO, tipo='alunno'))
            self.assertEqual(post.call_args.kwargs['json'], {'uid': 'file-1', 'pkScheda': 'scheda-secondo-figlio'})
            self.assertTrue(post.call_args.args[0].endswith('/downloadallegatobachecaalunno'))

    def test_rinnova_sessione_se_link_rifiutato(self):
        with patch.object(argo_client, 'get_session', return_value=Mock()), \
                patch.object(argo_client, '_reset_session') as reset, \
                patch.object(argo_client.requests, 'post') as post:
            post.return_value.json.side_effect = [{'success': False}, {'url': 'https://www.portaleargo.it/file'}]
            argo_client.link_allegato_bacheca(STUDENTI[0], ALLEGATO)
            reset.assert_called_once_with('Anna & Leo')
            self.assertEqual(post.call_count, 2)


class DownloadTest(unittest.TestCase):
    def risposta(self, blocchi=(b'%PDF-test',), headers=None, redirect=False):
        r = Mock(headers=headers or {}, is_redirect=redirect)
        r.__enter__ = Mock(return_value=r)
        r.__exit__ = Mock(return_value=False)
        r.iter_content.return_value = iter(blocchi)
        return r

    def test_download_non_invia_credenziali(self):
        with patch.object(allegati.requests, 'get', return_value=self.risposta()) as get:
            with allegati.scarica_file('https://bacheca.s3.eu-west-1.amazonaws.com/documento') as f:
                self.assertEqual(f.read(), b'%PDF-test')
            self.assertNotIn('headers', get.call_args.kwargs)
            self.assertFalse(get.call_args.kwargs['allow_redirects'])

    def test_blocca_url_locali_o_non_https(self):
        with patch.object(allegati.requests, 'get') as get:
            for url in ('http://www.portaleargo.it/file', 'https://127.0.0.1/file',
                        'https://portaleargo.it.evil.example/file', 'https://user:pwd@www.portaleargo.it/file'):
                with self.subTest(url=url), self.assertRaises(ValueError):
                    allegati.scarica_file(url)
            get.assert_not_called()

    def test_redirect_controllato_prima_di_seguirlo(self):
        r = self.risposta(headers={'Location': 'https://127.0.0.1/privato'}, redirect=True)
        with patch.object(allegati.requests, 'get', return_value=r) as get:
            with self.assertRaises(ValueError):
                allegati.scarica_file('https://www.portaleargo.it/file')
            get.assert_called_once()

    def test_dimensione_limitata_anche_senza_content_length(self):
        with patch.object(allegati, 'MAX_BYTES', 4), \
                patch.object(allegati.requests, 'get', return_value=self.risposta((b'123', b'45'))):
            with self.assertRaises(ValueError):
                allegati.scarica_file('https://www.portaleargo.it/file')

    def test_nome_file_sicuro_preserva_accenti(self):
        self.assertEqual(allegati.nome_download('../cartella\\Circolare è.pdf\r\n'), 'Circolare è.pdf')


class RouteTest(DatabaseFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        models.init_db()
        self.id = self.inserisci()
        self.client = app.test_client()
        p = patch('app.get_studenti', return_value=STUDENTI)
        p.start()
        self.addCleanup(p.stop)

    def test_html_e_link_ingress(self):
        for prefix in ('', '/addon', '/app/addon', '/api/hassio_ingress/token'):
            with self.subTest(prefix=prefix), app.test_request_context(prefix + '/bacheca'):
                # /app/<slug> viene normalmente rimosso dal reverse proxy HA.
                from app import bacheca
                html = bacheca()
                self.assertIn('Scarica Circolare è.pdf', html)
                import re
                href = re.search(r'href="(\./bacheca/[^\"]+)"', html).group(1)
                self.assertTrue(urljoin('http://localhost' + prefix + '/bacheca', href).startswith(
                    'http://localhost' + prefix + '/bacheca/'))
                self.assertIn('studente=Anna%20%26%20Leo', href)

    def test_download_tutti_prefissi(self):
        for prefix in ('', '/addon', '/app/addon', '/api/hassio_ingress/token'):
            with self.subTest(prefix=prefix), \
                    patch('app.link_allegato_bacheca', return_value='https://www.portaleargo.it/file') as link, \
                    patch('app.scarica_file', return_value=io.BytesIO(b'%PDF-test')):
                r = self.client.get(prefix + f'/bacheca/{self.id}/allegati/0', query_string={'studente': 'Anna & Leo'})
                self.assertEqual(r.status_code, 200)
                self.assertEqual(r.data, b'%PDF-test')
                self.assertIn('attachment;', r.headers['Content-Disposition'])
                self.assertEqual(r.headers['Cache-Control'], 'private, no-store')
                link.assert_called_once_with(STUDENTI[0], ALLEGATO)
                r.close()

    def test_altro_studente_indice_o_id_non_validi(self):
        with patch('app.link_allegato_bacheca') as link:
            for msg_id, indice, nome in ((self.id, 0, 'Luca'), (self.id, 5, 'Anna & Leo'),
                                          (999, 0, 'Anna & Leo'), (self.id, 0, ''),
                                          (self.id, 0, 'Sconosciuto')):
                r = self.client.get(f'/bacheca/{msg_id}/allegati/{indice}', query_string={'studente': nome})
                self.assertEqual(r.status_code, 404)
            link.assert_not_called()

    def test_errore_argo_senza_url_o_token_nella_risposta(self):
        with patch('app.link_allegato_bacheca', side_effect=RuntimeError('TOKEN-SEGRETO')):
            r = self.client.get(f'/bacheca/{self.id}/allegati/0', query_string={'studente': 'Anna & Leo'})
            self.assertEqual(r.status_code, 502)
            self.assertIn('Download non riuscito', r.text)
            self.assertNotIn('TOKEN-SEGRETO', r.text)


if __name__ == '__main__':
    unittest.main()
