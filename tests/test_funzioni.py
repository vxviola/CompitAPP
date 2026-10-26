from datetime import date
import json
from unittest.mock import Mock, patch
import unittest

from test_bacheca import DatabaseFixture, STUDENTI, ALLEGATO
from app import app
import ha_client
import models


class FunzioniTest(DatabaseFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        models.init_db()
        self.client = app.test_client()
        for target in ('app.get_studenti', 'funzioni.get_studenti'):
            p=patch(target, return_value=STUDENTI);p.start();self.addCleanup(p.stop)
        self.nome = STUDENTI[0]['nome']
        conn=models.get_db()
        self.task=conn.execute('INSERT INTO compiti(studente,data,materia,testo) VALUES (?,?,?,?)', (self.nome,'2026-10-27','Italiano','Leggere Città invisibili')).lastrowid
        self.altro=conn.execute('INSERT INTO compiti(studente,data,materia,testo) VALUES (?,?,?,?)', ('Luca','2026-10-27','Matematica','Riservato secondo')).lastrowid
        self.msg=conn.execute('INSERT INTO bacheca(studente,data,titolo,testo,allegati) VALUES (?,?,?,?,?)', (self.nome,'2026-10-26','Autorizzazione museo','Da consegnare',json.dumps([ALLEGATO]))).lastrowid
        conn.commit();conn.close()

    def post(self, path, data, nome=None):
        return self.client.post(path, query_string={'studente':nome or self.nome}, json=data)

    def row(self, table, rid):
        conn=models.get_db()
        try:return dict(conn.execute('SELECT * FROM '+table+' WHERE id=?',(rid,)).fetchone())
        finally:conn.close()

    def test_compiti_persistenti_e_separati_per_figlio(self):
        for prefix in ('','/addon','/app/addon','/api/hassio_ingress/token'):
            self.assertEqual(self.post(prefix+'/api/compiti/'+str(self.task),{'completato':True}).status_code,200)
        self.assertEqual(self.row('compiti',self.task)['completato'],1)
        self.assertEqual(self.row('compiti',self.altro)['completato'],0)
        self.assertEqual(self.post('/api/compiti/'+str(self.task),{'completato':False},'Luca').status_code,404)
        self.assertEqual(self.post('/api/compiti/'+str(self.task),{'completato':'false'}).status_code,400)

    def test_reset_attende_sync_e_svuota_cursori_conservando_preferenze(self):
        import sync_state
        conn=models.get_db()
        conn.executemany('INSERT INTO meta(chiave,valore) VALUES (?,?)',[
            ('sync_eventi:v1:compiti:'+self.nome,'{}'),('ha_notify:'+self.nome,'{}')])
        conn.execute('INSERT INTO zaino_materiali(studente,testo) VALUES (?,?)',(self.nome,'Diario'))
        conn.commit();conn.close()
        self.assertTrue(sync_state.inizia_manutenzione())
        try:
            self.assertEqual(self.client.post('/api/reset-db').status_code,409)
            self.assertEqual(self.row('compiti',self.task)['testo'],'Leggere Città invisibili')
        finally:sync_state.termina_manutenzione()
        self.assertEqual(self.client.post('/api/reset-db').status_code,200)
        conn=models.get_db()
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM meta WHERE chiave LIKE 'sync_eventi:%'").fetchone()[0],0)
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM zaino_materiali').fetchone()[0],1)
        self.assertIsNotNone(conn.execute('SELECT 1 FROM meta WHERE chiave=?',('ha_notify:'+self.nome,)).fetchone())
        conn.close()
        self.assertTrue(sync_state.inizia_manutenzione());sync_state.termina_manutenzione()

    def test_documenti_letti_preferiti_e_promemoria_sono_locali(self):
        path='/api/bacheca/'+str(self.msg)
        self.assertEqual(self.post(path,{'letta':True,'preferito':True,'promemoria_locale':'2026-10-29'}).status_code,200)
        r=self.row('bacheca',self.msg)
        self.assertEqual((r['letta'],r['preferito'],r['promemoria_locale']),(1,1,'2026-10-29'))
        self.assertEqual(self.post(path,{'letta':False},'Luca').status_code,404)
        self.assertEqual(self.post(path,{'promemoria_locale':'2026-99-33'}).status_code,400)
        self.assertEqual(self.post(path+'/allegati/0/letto',{'letto':True}).status_code,200)
        self.assertEqual(self.post(path+'/allegati/9/letto',{'letto':True}).status_code,404)
        self.assertEqual(self.post(path+'/allegati/0/letto',{'letto':True},'Luca').status_code,404)
        html=self.client.get('/bacheca',query_string={'studente':self.nome}).text
        self.assertIn('data-unread="0"',html)
        self.assertIn('data-starred="1"',html)

    def test_materiali_zaino_riutilizzabili_spunte_per_giorno_e_figlio(self):
        result=self.post('/api/zaino',{'testo':'Diario','materia':''})
        self.assertEqual(result.status_code,200)
        rid=result.json['id']
        self.assertEqual(self.post('/api/zaino/'+str(rid),{'data':'2026-10-27','fatto':True}).status_code,200)
        self.assertEqual(self.post('/api/zaino/'+str(rid),{'data':'2026-10-27','fatto':False},'Luca').status_code,404)
        oggi=self.client.get('/zaino',query_string={'studente':self.nome,'data':'2026-10-27'}).text
        domani=self.client.get('/zaino',query_string={'studente':self.nome,'data':'2026-10-28'}).text
        self.assertIn('1 / 1',oggi)
        self.assertIn('0 / 1',domani)
        self.assertEqual(self.client.delete('/api/zaino/'+str(rid),query_string={'studente':'Luca'}).status_code,404)
        self.assertEqual(self.client.delete('/api/zaino/'+str(rid),query_string={'studente':self.nome}).status_code,200)

    def test_materiali_per_materia_seguono_orario(self):
        conn=models.get_db();conn.execute('INSERT INTO orario(studente,giorno,ora,materia) VALUES (?,?,?,?)',(self.nome,1,1,'Italiano'));conn.commit();conn.close()
        self.post('/api/zaino',{'testo':'Quaderno rosso','materia':'Italiano'})
        html=self.client.get('/zaino',query_string={'studente':self.nome,'data':'2026-10-27'}).text
        self.assertIn('0 / 1',html)
        html=self.client.get('/zaino',query_string={'studente':self.nome,'data':'2026-10-28'}).text
        self.assertIn('0 / 0',html)

    def test_pagine_e_link_mantengono_prefisso_ingress_e_figlio(self):
        for prefix in ('','/addon','/app/addon','/api/hassio_ingress/token'):
            for page in ('/ricerca','/zaino'):
                r=self.client.get(prefix+page,query_string={'studente':self.nome})
                self.assertEqual(r.status_code,200)
                self.assertIn(prefix+'/static/funzioni.js?v=240',r.text)
                self.assertIn('Anna &amp; Leo',r.text)
        r=self.client.get('/zaino',headers={'X-Ingress-Path':'/api/hassio_ingress/reale'},query_string={'studente':self.nome})
        self.assertIn('/api/hassio_ingress/reale/zaino',r.text)

    def test_ricerca_ignora_accenti_e_non_mostra_altri_figli(self):
        html=self.client.get('/ricerca',query_string={'studente':self.nome,'q':'citta'}).text
        self.assertIn('Leggere Città invisibili',html)
        self.assertNotIn('Riservato secondo',html)
        html=self.client.get('/ricerca',query_string={'studente':self.nome,'q':'Circolare'}).text
        self.assertIn('Autorizzazione museo',html)
        html=self.client.get('/ricerca',query_string={'studente':self.nome,'q':'%'}).text
        self.assertIn('Nessun risultato trovato',html)

    def test_ricerca_e_materiali_non_eseguono_html(self):
        q='<script>alert(1)</script>'
        html=self.client.get('/ricerca',query_string={'studente':self.nome,'q':q}).text
        self.assertNotIn(q,html)
        self.assertIn('&lt;script&gt;',html)
        self.post('/api/zaino',{'testo':'<img src=x onerror=alert(1)>','materia':''})
        html=self.client.get('/zaino',query_string={'studente':self.nome}).text
        self.assertNotIn('<img src=x',html)

    def test_ha_richiede_destinatario_esplicito_e_impostazioni_per_figlio(self):
        servizi=[{'id':'notify.mobile_app_demo','nome':'Telefono demo'}]
        with patch('ha_client.servizi',return_value=servizi):
            bad=self.post('/api/ha/notifiche',{'attive':True,'servizio':'switch.turn_on','eventi':['compiti']})
            self.assertEqual(bad.status_code,400)
            r=self.post('/api/ha/notifiche',{'attive':True,'servizio':'notify.mobile_app_demo','eventi':['compiti']})
            self.assertEqual(r.status_code,200)
        self.assertTrue(ha_client.configurazione(self.nome)['attive'])
        self.assertFalse(ha_client.configurazione('Luca')['attive'])
        self.assertEqual(self.post('/api/ha/notifiche',{'attive':True,'servizio':{},'eventi':[]}).status_code,400)

    def test_notifica_ha_solo_categorie_abilitate_e_destinatario_salvato(self):
        with patch('ha_client.servizi',return_value=[{'id':'notify.mobile_app_demo'}]):
            ha_client.salva(self.nome,{'attive':True,'servizio':'notify.mobile_app_demo','eventi':['bacheca']})
        with patch('ha_client._headers',return_value={'Authorization':'Bearer DEMO'}),patch('ha_client._apertura',return_value='/app/demo?uniscuola=test'),patch('ha_client.requests.post') as post:
            self.assertFalse(ha_client.invia(self.nome,'voti','Test','Non inviare'))
            post.assert_not_called()
            self.assertTrue(ha_client.invia(self.nome,'bacheca','Test','Comunicazione'))
            self.assertTrue(post.call_args.args[0].endswith('/notify/mobile_app_demo'))
            self.assertEqual(post.call_args.kwargs['json']['data']['url'],'/app/demo?uniscuola=test')

    def test_promemoria_documenti_non_si_ripetono_e_si_riprovano_se_falliti(self):
        self.post('/api/bacheca/'+str(self.msg),{'promemoria_locale':date.today().isoformat()})
        with patch('ha_client.configurazione',return_value={'attive':True,'eventi':['documenti']}),patch('ha_client.invia',side_effect=[False,True]) as send:
            ha_client.promemoria_documenti([STUDENTI[0]])
            ha_client.promemoria_documenti([STUDENTI[0]])
            ha_client.promemoria_documenti([STUDENTI[0]])
            self.assertEqual(send.call_count,2)
