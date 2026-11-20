from contextlib import closing
from html.parser import HTMLParser
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from test_bacheca import DatabaseFixture, STUDENTI
from app import app
import models
import revisione_voti_web


class CampiPagina(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.campi = {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'input' and a.get('name') in ('versione', 'token'):
            self.campi[a['name']] = a['value']


class RevisioneWebTest(DatabaseFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        models.init_db()
        self.client = app.test_client()
        self.nome = STUDENTI[0]['nome']
        self.query = urlencode({'studente': self.nome})
        self.url = '/voti/duplicati?' + self.query
        cache = patch.dict(revisione_voti_web._riscontri, clear=True)
        cache.start()
        self.addCleanup(cache.stop)
        for target in ('app.get_studenti', 'revisione_voti_web.get_studenti'):
            p = patch(target, return_value=STUDENTI)
            p.start()
            self.addCleanup(p.stop)
        with closing(models.get_db()) as conn, conn:
            self.righe = [conn.execute('''INSERT INTO voti(studente,data,materia,voto,descrizione,argo_uid)
                    VALUES (?,'2026-11-10','Storia','8','Compito scritto',?)''', (self.nome, uid)).lastrowid
                          for uid in ('ID-ARGO-PRIVATO', None)]
            conn.execute("""INSERT INTO voti(studente,data,materia,voto) VALUES
                ('Luca','2026-11-10','Materia riservata','7'),('Luca','2026-11-10','Materia riservata','7')""")

    def test_ingress_collegamenti_e_confronto_solo_su_richiesta(self):
        with patch('revisione_voti_web.confronta_gruppi_voti') as mock:
            mock.side_effect = lambda studente, gruppi: {
                g['versione']: dict(esito='riscontro', trovati=1, messaggio='Una valutazione riscontrata',
                                    righe={self.righe[0]: 'Corrispondenza con Argo'}) for g in gruppi}
            for prefix in ('', '/addon', '/app/addon', '/api/hassio_ingress/token'):
                with self.subTest(prefix=prefix):
                    for route in ('voti', 'configurazione'):
                        html = self.client.get(prefix + '/' + route + '?' + self.query).text
                        self.assertIn('href="' + prefix + self.url + '"', html)
                    html = self.client.get(prefix + self.url).text
                    self.assertIn('action="' + prefix + self.url + '#gruppo-', html)
                    self.assertIn('href="' + prefix + '/voti/duplicati?studente=Luca"', html)
                    self.assertNotIn('ID-ARGO-PRIVATO', html)
                    self.assertNotIn('Materia riservata', html)
            mock.assert_not_called()
            form = CampiPagina(html).campi
            r = self.client.post(prefix + self.url, data=dict(form, azione='confronta'))
            self.assertEqual(r.status_code, 200)
            self.assertIn('Corrispondenza con Argo', r.text)
            self.assertIn('Una valutazione riscontrata', r.text)
            self.assertEqual(mock.call_args.args[0], STUDENTI[0])
            self.assertEqual(self.conteggi(), (2, 2))

    def conteggi(self):
        with closing(models.get_db()) as conn:
            return tuple(conn.execute('SELECT COUNT(*) FROM ' + tab + ' WHERE studente=?',
                                      (self.nome,)).fetchone()[0] for tab in ('voti', 'voti_visibili'))

    def test_conferma_esclusione_ripristino_e_ripetizione(self):
        url = '/api/hassio_ingress/token' + self.url
        form = CampiPagina(self.client.get(url).text).campi
        scelta = dict(form, azione='escludi', copia_id=self.righe[1], conserva_id=self.righe[0])
        self.assertEqual(self.client.post(url, data=scelta).status_code, 400)
        scelta['conferma'] = 'si'
        with patch('revisione_voti_web.confronta_gruppi_voti') as mock:
            r = self.client.post(url, data=scelta)
            self.assertEqual(r.status_code, 303)
            self.assertEqual(r.location, url + '&esito=esclusa')
            html = self.client.get(r.location).text
            self.assertIn('Copia esclusa dai voti', html)
            self.assertIn('Ripristina voce', html)
            self.assertEqual(self.conteggi(), (2, 1))
            self.assertEqual(self.client.post(url, data=scelta).status_code, 409)
            undo = dict(CampiPagina(html).campi, azione='ripristina', copia_id=self.righe[1])
            self.assertEqual(self.client.post(url, data=undo).status_code, 303)
            self.assertEqual(self.conteggi(), (2, 2))
            mock.assert_not_called()

    def test_cambio_gruppo_durante_il_confronto_non_mostra_riscontro_superato(self):
        form = CampiPagina(self.client.get(self.url).text).campi
        def confronto(studente, gruppi):
            with closing(models.get_db()) as conn, conn:
                conn.execute('UPDATE voti SET voto=? WHERE id=?', ('7', self.righe[0]))
            return {gruppi[0]['versione']: {'messaggio': 'RISULTATO_SUPERATO'}}
        with patch('revisione_voti_web.confronta_gruppi_voti', side_effect=confronto):
            r = self.client.post(self.url, data=dict(form, azione='confronta'))
        self.assertEqual(r.status_code, 409)
        self.assertNotIn('RISULTATO_SUPERATO', r.text)
        self.assertIn('Il gruppo è cambiato', r.text)

    def test_confronto_collettivo_conserva_gli_altri_riscontri_dopo_una_scelta(self):
        with closing(models.get_db()) as conn, conn:
            conn.executemany("INSERT INTO voti(studente,data,materia,voto) VALUES (?, '2026-11-09', ?, '7')",
                             [(self.nome, 'Italiano'), (self.nome, 'Italiano'), (self.nome, 'Francese')])
        token = CampiPagina(self.client.get(self.url).text).campi['token']
        def confronto(studente, gruppi):
            self.assertEqual({g['materia'] for g in gruppi}, {'Storia', 'Italiano'})
            return {g['versione']: dict(esito='riscontro', trovati=1,
                    messaggio='Esito per ' + g['materia'], righe={}) for g in gruppi}
        with patch('revisione_voti_web.confronta_gruppi_voti', side_effect=confronto) as batch:
            html = self.client.post(self.url, data={'token': token, 'azione': 'confronta_tutti'}).text
            self.assertIn('Esito per Storia', html)
            self.assertIn('Esito per Italiano', html)
            self.assertNotIn('Francese', html)
            gruppo = next(g for g in batch.call_args.args[1] if g['materia'] == 'Storia')
            self.client.post(self.url, data=dict(token=token, azione='escludi', versione=gruppo['versione'],
                             copia_id=self.righe[1], conserva_id=self.righe[0], conferma='si'))
            html = self.client.get(self.url).text
            self.assertNotIn('Esito per Storia', html)
            self.assertIn('Esito per Italiano', html)
            self.assertLess(html.index('Italiano · 7'), html.index('Storia · 8'))
            self.assertIn('<strong>1</strong> gruppo con più voci visibili', html)
            self.assertIn('<strong>1</strong> copia esclusa', html)
            batch.assert_called_once()

    def test_riscontro_di_identita_distinte_protegge_le_voci_anche_dal_post_precedente(self):
        form = CampiPagina(self.client.get(self.url).text).campi
        esiti = {form['versione']: dict(esito='distinti', messaggio='Due prove distinte', righe={})}
        with patch('revisione_voti_web.confronta_gruppi_voti', return_value=esiti):
            html = self.client.post(self.url, data=dict(form, azione='confronta')).text
        self.assertIn('Due prove distinte', html)
        self.assertNotIn('Conferma esclusione', html)
        scelta = dict(form, azione='escludi', conferma='si', copia_id=self.righe[1], conserva_id=self.righe[0])
        self.assertEqual(self.client.post(self.url, data=scelta).status_code, 409)
        self.assertEqual(self.conteggi(), (2, 2))

    def test_profilo_e_modulo_richiesti(self):
        for suffisso in ('', '?studente=Inesistente', '?' + self.query + '&studente=Luca'):
            self.assertEqual(self.client.get('/voti/duplicati' + suffisso).status_code, 404)
        form = CampiPagina(self.client.get(self.url).text).campi
        azione = dict(form, azione='escludi', copia_id=self.righe[1], conserva_id=self.righe[0], conferma='si')
        self.assertEqual(self.client.post('/voti/duplicati?studente=Luca', data=azione).status_code, 403)
        self.assertEqual(self.client.post(self.url, data=dict(azione, token='')).status_code, 403)
        self.assertEqual(self.client.post(self.url, data=dict(azione, copia_id=self.righe[1] + 1)).status_code, 409)
        self.assertEqual(self.conteggi(), (2, 2))
