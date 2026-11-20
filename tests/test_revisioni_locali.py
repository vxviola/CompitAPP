from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Barrier
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'compitapp'))
import models
from revisione_voti import RevisioneObsoleta, escludi_copia, gruppi_voti, ripristina_copia


class RevisioniLocaliTest(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(models, 'DB_PATH', str(Path(directory) / 'registro.sqlite')))
        models.init_db()
        self.conn = models.get_db()
        self.addCleanup(self.conn.close)
        self.a = self.voto(uid='id-esterno-1')
        self.b = self.voto(descrizione='')

    def voto(self, nome='Ada', uid=None, descrizione=None):
        with self.conn:
            return self.conn.execute('''INSERT INTO voti(studente,data,materia,voto,descrizione,argo_uid)
                VALUES (?, '2026-10-22', 'Storia', '8', ?, ?)''', (nome, descrizione, uid)).lastrowid

    def gruppo(self, nome='Ada'):
        gruppi = gruppi_voti(self.conn, nome)
        self.assertEqual(len(gruppi), 1)
        return gruppi[0]

    def visibili(self, nome='Ada'):
        return [r[0] for r in self.conn.execute(
            'SELECT id FROM voti_visibili WHERE studente=? ORDER BY id', (nome,))]

    def escludi(self):
        escludi_copia(self.conn, 'Ada', self.b, self.a, self.gruppo()['versione'])

    def test_una_copia_ripristinabile_dopo_rilettura_e_riavvio(self):
        self.escludi()
        models.init_db()
        with self.conn:
            self.conn.execute("UPDATE voti SET voto='8', descrizione='', notificato=1 WHERE id=?", (self.b,))
        g = self.gruppo()
        self.assertEqual(self.visibili(), [self.a])
        self.assertEqual([(r['id'], r['esclusa'], r['conserva_id'], r['collegato']) for r in g['righe']],
                         [(self.a, False, None, True), (self.b, True, self.a, False)])
        self.assertNotIn('id-esterno-1', str(g))
        self.assertEqual(models.riepilogo_medie(self.conn, 'Ada')['conteggi'], {'Storia': 1})
        ripristina_copia(self.conn, 'Ada', self.b, g['versione'])
        self.assertEqual(self.visibili(), [self.a, self.b])
        self.assertEqual(models.riepilogo_medie(self.conn, 'Ada')['conteggi'], {'Storia': 2})

    def test_tre_copie_cambiano_riferimento_senza_catene_o_gruppi_vuoti(self):
        c = self.voto()
        self.escludi()
        escludi_copia(self.conn, 'Ada', self.a, c, self.gruppo()['versione'])
        self.assertEqual(self.visibili(), [c])
        self.assertEqual([r['conserva_id'] for r in self.gruppo()['righe']], [c, c, None])
        for op in [(c, c), (c, self.a), (self.a, c)]:
            with self.assertRaises(RevisioneObsoleta):
                escludi_copia(self.conn, 'Ada', *op, self.gruppo()['versione'])
        with self.conn:
            self.conn.execute('DELETE FROM voti WHERE id=?', (c,))
        self.assertEqual(self.visibili(), [self.a, self.b])

    def test_aggiornamento_argo_rende_visibile_il_voto_e_invalida_la_decisione(self):
        self.escludi()
        with self.conn:
            self.conn.execute("UPDATE voti SET voto='9' WHERE id=?", (self.a,))
        self.assertEqual(self.visibili(), [self.a, self.b])
        self.assertEqual(gruppi_voti(self.conn, 'Ada'), [])
        with self.conn:
            self.conn.execute("UPDATE voti SET voto='8' WHERE id=?", (self.a,))
        self.assertEqual(self.visibili(), [self.a, self.b])
        self.escludi()
        with self.conn:
            self.conn.execute("UPDATE voti SET argo_uid='id-esterno-2' WHERE id=?", (self.b,))
        self.assertEqual(self.visibili(), [self.a, self.b])

    def test_rifiuta_anteprima_superata_e_identita_cambiate_o_estranee(self):
        altro = self.voto(descrizione='Orale')
        altro_studente = self.voto('Bea')
        self.voto('Bea')
        versione = self.gruppo()['versione']
        for nome, copia, conserva in [('Ada', self.a, altro), ('Ada', altro_studente, self.b),
                                     ('Bea', self.b, self.a), ('Ada', True, self.b)]:
            with self.assertRaises(RevisioneObsoleta):
                escludi_copia(self.conn, nome, copia, conserva, versione)
        with self.conn:
            self.conn.execute("UPDATE voti SET argo_uid='diverso' WHERE id=?", (self.a,))
        with self.assertRaises(RevisioneObsoleta):
            escludi_copia(self.conn, 'Ada', self.b, self.a, versione)
        versione = self.gruppo()['versione']
        self.voto()
        with self.assertRaises(RevisioneObsoleta):
            escludi_copia(self.conn, 'Ada', self.b, self.a, versione)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM voti_esclusi').fetchone()[0], 0)

    def test_due_conferme_in_parallelo_non_possono_escludere_entrambe_le_righe(self):
        versione = self.gruppo()['versione']
        pronte = Barrier(2)

        def conferma(copia, conserva):
            with closing(models.get_db()) as conn:
                pronte.wait(timeout=5)
                try:
                    escludi_copia(conn, 'Ada', copia, conserva, versione)
                    return 'salvata'
                except RevisioneObsoleta:
                    return 'superata'

        with ThreadPoolExecutor(max_workers=2) as pool:
            risultati = [pool.submit(conferma, self.a, self.b), pool.submit(conferma, self.b, self.a)]
            self.assertCountEqual([f.result() for f in risultati], ['salvata', 'superata'])
        self.assertEqual(len(self.visibili()), 1)

    def test_cambio_profilo_annulla_solo_correzioni_del_profilo_azzerato(self):
        x, y = self.voto('Bea'), self.voto('Bea')
        self.escludi()
        escludi_copia(self.conn, 'Bea', y, x, self.gruppo('Bea')['versione'])
        with self.conn:
            models.svuota_studente(self.conn, 'Ada')
        self.assertEqual(self.visibili(), [])
        self.assertEqual(self.visibili('Bea'), [x])
        self.assertEqual([r[0] for r in self.conn.execute('SELECT studente FROM voti_esclusi')], ['Bea'])
