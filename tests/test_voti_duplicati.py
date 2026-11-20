import unittest

from test_bacheca import DatabaseFixture
import models
from voti_duplicati import riconcilia_copia_anonima, riconcilia_identita_voto, separa_identita_voti


class RiconciliazioneVotiTest(DatabaseFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        models.init_db()
        self.conn = models.get_db()
        self.addCleanup(self.conn.close)
        self.nome = 'Demo'
        self.valori = {'data': '2026-10-05', 'materia': 'Storia', 'voto': '8', 'descrizione': 'Orale'}

    def voto(self, uid, notificato=0, voto='8', studente='Demo'):
        return self.conn.execute('''INSERT INTO voti(studente,argo_uid,data,materia,voto,descrizione,notificato)
            VALUES (?,?,?,?,?,?,?)''', (studente, uid, self.valori['data'], self.valori['materia'], voto,
                                         self.valori['descrizione'], notificato)).lastrowid

    def evento(self, uid, versione, eliminato=0):
        self.conn.execute('''INSERT INTO argo_eventi (studente,categoria,uid,versione,eliminato)
            VALUES (?,'voti',?,?,?)''', (self.nome, uid, versione, eliminato))

    def righe(self):
        return [tuple(r) for r in self.conn.execute('''SELECT id,studente,argo_uid,voto,notificato
            FROM voti ORDER BY id''')]

    def test_riunisce_alias_attestati_conservando_id_notifica_e_correzione_recente(self):
        storico = self.voto('precedente', notificato=1, voto='7')
        self.voto('ufficiale', voto='8')
        altro = self.voto('precedente', studente='Secondo')
        self.evento('precedente', '2026-10-05T11:00:00')
        self.evento('ufficiale', '2026-10-05T14:00:00')
        for _ in range(2):
            self.assertEqual(riconcilia_identita_voto(self.conn, self.nome, 'ufficiale', ['precedente']),
                             'ufficiale')
        self.assertEqual(self.righe(), [(storico, self.nome, 'ufficiale', '8', 1),
                                        (altro, 'Secondo', 'precedente', '8', 0)])
        self.assertEqual(riconcilia_identita_voto(self.conn, self.nome, 'precedente'), 'ufficiale')
        self.assertEqual(riconcilia_identita_voto(self.conn, 'Secondo', 'precedente'), 'precedente')
        self.assertEqual([tuple(r) for r in self.conn.execute('SELECT uid,versione,eliminato FROM argo_eventi')],
                         [('ufficiale', '2026-10-05T14:00:00', 0)])

    def test_ritiro_prevale_su_replay_della_stessa_versione(self):
        self.voto('web')
        self.evento('web', '2026-10-05T11:00:00')
        self.evento('mobile', '2026-10-05T11:00:00', eliminato=1)
        riconcilia_identita_voto(self.conn, self.nome, 'web', ['mobile'])
        self.assertEqual(self.righe(), [])
        evento = self.conn.execute('SELECT uid,versione,eliminato FROM argo_eventi').fetchone()
        self.assertEqual(tuple(evento), ('web', '2026-10-05T11:00:00', 1))

    def test_una_nuova_chiave_propaga_gli_alias_precedenti_e_un_solo_voto(self):
        storico = self.voto('mobile')
        riconcilia_identita_voto(self.conn, self.nome, 'web', ['mobile'])
        riconcilia_identita_voto(self.conn, self.nome, 'aggiornato', ['web'])
        self.assertEqual(self.righe(), [(storico, self.nome, 'aggiornato', '8', 0)])
        for uid in ('web', 'mobile', 'aggiornato'):
            self.assertEqual(riconcilia_identita_voto(self.conn, self.nome, uid), 'aggiornato')

    def test_due_pk_ufficiali_distinti_smentiscono_una_vecchia_equivalenza(self):
        storico = self.voto('A')
        riconcilia_identita_voto(self.conn, self.nome, 'A', ['B', 'C'])
        primari = {'A', 'B'}
        separa_identita_voti(self.conn, self.nome, primari)
        self.assertEqual(riconcilia_identita_voto(self.conn, self.nome, 'A', (), primari), 'A')
        self.assertEqual(riconcilia_identita_voto(self.conn, self.nome, 'B', ['C'], primari), 'B')
        secondo = self.voto('B')
        self.assertEqual(riconcilia_identita_voto(self.conn, self.nome, 'C'), 'B')
        self.assertEqual(self.righe(), [(storico, self.nome, 'A', '8', 0), (secondo, self.nome, 'B', '8', 0)])

    def test_un_alias_riproposto_non_unisce_due_pk_compresenti(self):
        primo = self.voto('A')
        secondo = self.voto('B')
        riconcilia_identita_voto(self.conn, self.nome, 'A', ['C'])
        primari = {'A', 'B'}
        separa_identita_voti(self.conn, self.nome, primari)
        self.assertEqual(riconcilia_identita_voto(self.conn, self.nome, 'B', ['C'], primari), 'B')
        self.assertEqual(self.righe(), [(primo, self.nome, 'A', '8', 0), (secondo, self.nome, 'B', '8', 0)])

    def test_due_voti_con_stessi_valori_e_uid_distinti_senza_prova_restano_entrambi(self):
        self.voto('v1')
        self.voto('v2')
        prima = self.righe()
        for uid in ('v1', 'v2'):
            self.assertEqual(riconcilia_identita_voto(self.conn, self.nome, uid), uid)
            self.assertFalse(riconcilia_copia_anonima(self.conn, self.nome, uid, self.valori))
        self.assertEqual(self.righe(), prima)

    def test_copia_anonima_confermata_conserva_id_e_stato_anche_al_secondo_passaggio(self):
        storico = self.voto(None, notificato=1)
        self.voto('web')
        altro = self.voto(None, studente='Secondo')
        self.assertTrue(riconcilia_copia_anonima(self.conn, self.nome, 'web', self.valori))
        self.assertFalse(riconcilia_copia_anonima(self.conn, self.nome, 'web', self.valori))
        self.assertEqual(self.righe(), [(storico, self.nome, 'web', '8', 1), (altro, 'Secondo', None, '8', 0)])

    def test_piu_voti_identici_nella_stessa_materia_rendono_ambigua_la_copia_anonima(self):
        self.voto('web')
        self.voto('altro')
        self.voto(None)
        prima = self.righe()
        self.assertFalse(riconcilia_copia_anonima(self.conn, self.nome, 'web', self.valori))
        self.assertEqual(self.righe(), prima)

    def test_rollback_riporta_sia_righe_che_identificativi_allo_stato_precedente(self):
        self.voto('web')
        self.voto('mobile', notificato=1)
        self.evento('mobile', '2026-10-05T12:00:00')
        self.conn.commit()
        prima = self.righe()
        riconcilia_identita_voto(self.conn, self.nome, 'web', ['mobile'])
        self.conn.rollback()
        self.assertEqual(self.righe(), prima)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM voti_alias').fetchone()[0], 0)
        self.assertEqual(self.conn.execute('SELECT uid FROM argo_eventi').fetchone()[0], 'mobile')
