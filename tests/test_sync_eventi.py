from datetime import datetime, timedelta
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch, Mock
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'compitapp'))

import argo_client
import models
import sync_argo
from test_bacheca import DatabaseFixture, STUDENTI


class EventiTest(DatabaseFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        models.init_db()
        self.st = STUDENTI[0]
        self.ora = datetime(2026, 10, 26, 20, 0)
        self.clock = patch('sync_argo.adesso', side_effect=lambda: self.ora)
        self.clock.start(); self.addCleanup(self.clock.stop)

    def sync(self, categoria, sezione):
        with patch('argo_client.dashboard_sync', return_value=sezione) as fetch:
            ok = sync_argo.sincronizza([self.st], (categoria,))
        return ok, fetch.call_args.args[1]

    def righe(self, tabella):
        conn = models.get_db()
        try:
            return [dict(r) for r in conn.execute('SELECT * FROM ' + tabella)]
        finally:
            conn.close()

    def stato(self, categoria):
        conn = models.get_db()
        try:
            r = conn.execute('SELECT valore FROM meta WHERE chiave=?', (sync_argo._chiave(categoria, self.st['nome']),)).fetchone()
            return json.loads(r[0]) if r else None
        finally:
            conn.close()

    def test_voto_corretto_e_cancellato_senza_duplicati(self):
        voto = {'pk': 'v1', 'datGiorno': '2026-10-15', 'desMateria': 'Storia', 'valore': 7,
                'datEvento': '2026-10-20T12:00:00', 'operazione': 'I'}
        self.assertTrue(self.sync('voti', {'voti': [voto]})[0])
        self.sync('voti', {'voti': [dict(voto, valore=8, operazione='U', datEvento='2026-10-21T12:00:00')]})
        self.assertEqual([r['voto'] for r in self.righe('voti')], ['8'])
        self.sync('voti', {'voti': [{'pk': 'v1', 'operazione': 'D', 'datEvento': '2026-10-22T12:00:00'}]})
        self.assertEqual(self.righe('voti'), [])
        self.sync('voti', {'voti': [voto]})
        self.assertEqual(self.righe('voti'), [])
        self.sync('voti', {'voti': [dict(voto, datEvento='2026-10-22T12:00:00')]})
        self.assertEqual(self.righe('voti'), [])
        self.sync('voti', {'voti': [dict(voto, datEvento='2026-10-23T12:00:00')]})
        self.assertEqual(len(self.righe('voti')), 1)

    def test_due_voti_stessa_materia_e_data_restano_distinti(self):
        voto = {'datGiorno': '2026-10-15', 'desMateria': 'Storia', 'valore': 8}
        self.sync('voti', {'voti': [dict(voto, pk='1'), dict(voto, pk='2')]})
        self.assertEqual(len(self.righe('voti')), 2)

    def test_ciclo_completo_usa_una_risposta_e_isola_la_categoria_guasta(self):
        sezione = {'registro':[{'pk':'r1','datGiorno':'2026-10-26','ora':1,'materia':'Storia',
                    'attivita':'I Romani','compiti':[{'dataConsegna':'2026-10-28','compito':'Leggere'}]}],
                   'voti':[], 'appello':[], 'noteDisciplinari':[], 'bacheca':[], 'promemoria':[]}
        with patch('argo_client.dashboard_sync',return_value=sezione) as fetch:
            self.assertTrue(sync_argo.sincronizza([self.st]))
            self.assertEqual(fetch.call_count,1)
        prima=self.stato('voti')
        self.ora += timedelta(days=1)
        with patch('argo_client.dashboard_sync',return_value=dict(sezione,voti={})):
            self.assertFalse(sync_argo.sincronizza([self.st]))
        self.assertEqual(self.stato('voti'),prima)
        self.assertNotEqual(self.stato('compiti')['ultimo'],prima['ultimo'])
        self.assertEqual(len(self.righe('compiti')),1)
        self.assertEqual(len(self.righe('argomenti')),1)

    def test_note_promemoria_e_argomenti_corretti_e_ritirati_per_figlio(self):
        casi=[('note','noteDisciplinari','note_disciplinari',{'datNota':'2026-10-26','desNota':'Prima'},'desNota','testo'),
              ('promemoria','promemoria','promemoria',{'datGiorno':'2026-10-26','desAnnotazioni':'Prima'},'desAnnotazioni','testo'),
              ('argomenti','argomentiLezione','argomenti',{'datGiorno':'2026-10-26','materia':'Storia','desArgomento':'Prima'},'desArgomento','argomento')]
        for categoria,chiave,tabella,record,campo,locale in casi:
            with self.subTest(categoria=categoria):
                record=dict(record,pk='identico-tra-figli')
                with patch('argo_client.dashboard_sync',return_value={chiave:[record]}):
                    sync_argo.sincronizza(STUDENTI,(categoria,))
                self.sync(categoria,{chiave:[dict(record,**{campo:'Corretto'})]})
                self.assertEqual(next(r[locale] for r in self.righe(tabella) if r['studente']==self.st['nome']),'Corretto')
                self.sync(categoria,{chiave:[{'pk':record['pk'],'operazione':'D'}]})
                self.assertEqual([r['studente'] for r in self.righe(tabella)],[STUDENTI[1]['nome']])

    def test_giustificazione_e_correzione_data_assenza(self):
        assenza = {'pk': 'a1', 'data': '2026-10-10', 'codEvento': 'A', 'giustificata': 'N'}
        self.sync('assenze', {'appello': [assenza]})
        self.sync('assenze', {'appello': [dict(assenza, giustificata='S', data='2026-10-11')]})
        r = self.righe('assenze')
        self.assertEqual(len(r), 1)
        self.assertEqual((r[0]['giustificata'], r[0]['data']), (1, '2026-10-11'))

    def test_bacheca_corretta_preserva_letture_e_non_accetta_allegati_malformati(self):
        msg={'pk':'b1','data':'2026-10-26','titolo':'Museo','listaAllegati':[{'pk':'file1','nomeFile':'Museo.pdf'}]}
        self.sync('bacheca',{'bacheca':[msg]})
        rid=self.righe('bacheca')[0]['id']
        conn=models.get_db()
        conn.execute('UPDATE bacheca SET letta=1,preferito=1 WHERE id=?',(rid,))
        conn.execute('INSERT INTO allegati_letti(studente,messaggio_id,uid,letto) VALUES (?,?,?,1)',(self.st['nome'],rid,'file1'))
        conn.commit();conn.close()
        self.sync('bacheca',{'bacheca':[dict(msg,titolo='Museo aggiornato')]})
        row=self.righe('bacheca')[0]
        self.assertEqual((row['id'],row['letta'],row['preferito']),(rid,1,1))
        prima=self.stato('bacheca')
        self.ora += timedelta(days=1)
        self.assertFalse(self.sync('bacheca',{'bacheca':[dict(msg,listaAllegati={})]})[0])
        self.assertEqual(self.stato('bacheca'),prima)
        self.assertEqual(self.righe('bacheca')[0]['allegati'],row['allegati'])
        conn=models.get_db();self.assertEqual(conn.execute('SELECT letto FROM allegati_letti').fetchone()[0],1);conn.close()

    def test_compiti_del_registro_sostituiti_solo_nel_gruppo_corretto(self):
        registro = {'pk': 'r1', 'materia': 'Italiano', 'compiti': [{'dataConsegna': '2026-10-28', 'compito': 'Leggere'}]}
        altro = dict(registro, pk='r2')
        self.sync('compiti', {'registro': [registro, altro]})
        conn = models.get_db(); conn.execute('UPDATE compiti SET completato=1 WHERE argo_gruppo=?', ('r1',)); conn.commit(); conn.close()
        self.sync('compiti', {'registro': [dict(registro, compiti=[{'dataConsegna': '2026-10-29', 'compito': 'Leggere capitolo 2'}])]})
        rows = self.righe('compiti')
        self.assertEqual(len(rows), 2)
        self.assertEqual(next(r for r in rows if r['argo_gruppo']=='r1')['data'], '2026-10-29')
        self.sync('compiti', {'registro': [{'pk':'r1', 'operazione':'D'}]})
        self.assertEqual([r['argo_gruppo'] for r in self.righe('compiti')], ['r2'])

    def test_lista_compiti_vuota_ritira_assegnazioni_ma_delta_vuoto_non_cancella(self):
        registro = {'pk':'r1', 'materia':'Storia', 'compiti':[{'dataConsegna':'2026-10-28','compito':'Testo'}]}
        self.sync('compiti', {'registro':[registro]})
        self.sync('compiti', {'registro':[]})
        self.assertEqual(len(self.righe('compiti')), 1)
        self.sync('compiti', {'registro':[dict(registro, compiti=[])]})
        self.assertEqual(self.righe('compiti'), [])

    def test_riordino_compiti_non_sposta_spunte_o_id_locali(self):
        a={'dataConsegna':'2026-10-28','compito':'Leggere'}
        b={'dataConsegna':'2026-10-28','compito':'Scrivere'}
        registro={'pk':'r1','materia':'Italiano','compiti':[a,b]}
        self.sync('compiti',{'registro':[registro]})
        originale={r['testo']:r['id'] for r in self.righe('compiti')}
        conn=models.get_db();conn.execute("UPDATE compiti SET completato=1 WHERE testo='Scrivere'");conn.commit();conn.close()
        self.sync('compiti',{'registro':[dict(registro,compiti=[b,a])]})
        self.assertEqual({r['testo']:r['id'] for r in self.righe('compiti')},originale)
        self.assertEqual(next(r['completato'] for r in self.righe('compiti') if r['testo']=='Scrivere'),1)
        self.sync('compiti',{'registro':[dict(registro,compiti=[{'dataConsegna':'2026-10-28','compito':'Nuovo'},b,a])]})
        self.assertEqual(len(self.righe('compiti')),3)
        self.assertEqual(next(r['completato'] for r in self.righe('compiti') if r['testo']=='Nuovo'),0)

    def test_migrazione_legacy_crea_backup_e_conserva_i_dati(self):
        conn=models.get_db();conn.close()
        legacy=str(Path(self.tmp.name)/'legacy.db')
        conn=sqlite3.connect(legacy)
        conn.execute('CREATE TABLE compiti(id INTEGER PRIMARY KEY AUTOINCREMENT,studente TEXT,data TEXT,materia TEXT,testo TEXT,notificato INTEGER DEFAULT 0,creato_il TEXT)')
        conn.execute("INSERT INTO compiti(studente,data,materia,testo) VALUES ('Demo','2026-10-20','Storia','Da conservare')")
        conn.commit();conn.close()
        with patch.object(models,'DB_PATH',legacy):
            models.init_db();models.init_db()
            conn=models.get_db();self.assertEqual(conn.execute('SELECT testo FROM compiti').fetchone()[0],'Da conservare');conn.close()
        copia=sqlite3.connect(legacy+'.prima-eventi.sqlite')
        self.assertEqual(copia.execute('SELECT testo FROM compiti').fetchone()[0],'Da conservare');copia.close()

    def test_evento_malformato_non_avanza_cursore_e_non_scrive_righe_parziali(self):
        voto = {'pk':'v1','datGiorno':'2026-10-15','desMateria':'Storia','valore':8}
        self.sync('voti', {'voti':[voto]})
        prima = self.stato('voti')
        self.ora += timedelta(days=3)
        ok, _ = self.sync('voti', {'voti':[dict(voto, pk='v2'),dict(voto,pk='v3',datGiorno='non-data')]})
        self.assertFalse(ok)
        self.assertEqual(self.stato('voti'), prima)
        self.assertEqual([r['argo_uid'] for r in self.righe('voti')], ['v1'])

    def test_offline_oltre_sette_giorni_riprende_dal_cursore_con_sovrapposizione(self):
        self.sync('voti', {'voti':[]})
        self.ora += timedelta(days=30)
        ok, dal = self.sync('voti', {'voti':[]})
        self.assertTrue(ok)
        self.assertEqual(dal, datetime(2026,10,19,20,0))
        self.assertEqual(self.stato('voti')['ultimo'], self.ora.isoformat())

    def test_primo_passaggio_non_si_fida_dei_vecchi_marcatori(self):
        conn=models.get_db();conn.execute("INSERT INTO meta(chiave,valore) VALUES (?, '1')", ('storico:voti:'+self.st['nome'],));conn.commit();conn.close()
        _, dal = self.sync('voti', {'voti':[]})
        self.assertEqual(dal, datetime(2026,8,25))

    def test_categoria_assente_e_errore_http_lasciano_storico_da_completare(self):
        self.assertFalse(self.sync('voti', {'registro':[]})[0])
        self.assertIsNone(self.stato('voti'))
        with patch('argo_client.dashboard_sync', side_effect=argo_client.ArgoSyncError('rete')):
            self.assertFalse(sync_argo.sincronizza([self.st], ('voti',)))
        self.assertIsNone(self.stato('voti'))

    def test_adozione_legacy_conserva_id_e_notificato(self):
        conn=models.get_db();cur=conn.execute('INSERT INTO voti(studente,data,materia,voto,descrizione,notificato) VALUES (?,?,?,?,?,?)', (self.st['nome'],'2026-10-15','Storia','7','Prova',1));old=cur.lastrowid;conn.commit();conn.close()
        self.sync('voti', {'voti':[{'pk':'v1','datGiorno':'2026-10-15','desMateria':'Storia','valore':8,'desCommento':'Prova'}]})
        rows=self.righe('voti')
        self.assertEqual(len(rows),1)
        self.assertEqual((rows[0]['id'],rows[0]['voto'],rows[0]['notificato']),(old,'8',1))

    def test_legacy_ambiguo_non_viene_cancellato_o_fuso(self):
        conn=models.get_db()
        for voto in ('6','7'):
            conn.execute('INSERT INTO voti(studente,data,materia,voto) VALUES (?,?,?,?)',(self.st['nome'],'2026-10-15','Storia',voto))
        conn.commit();conn.close()
        self.sync('voti', {'voti':[{'pk':'v1','datGiorno':'2026-10-15','desMateria':'Storia','valore':8}]})
        self.assertEqual(len(self.righe('voti')),3)

    def test_importazione_iniziale_silenziosa_e_rilettura_senza_doppie_notifiche(self):
        voto={'pk':'v1','datGiorno':'2026-10-15','desMateria':'Storia','valore':8}
        with patch('notifier.notifica_nuovo_voto') as notify:
            self.sync('voti',{'voti':[voto]})
            self.sync('voti',{'voti':[voto]})
            self.sync('voti',{'voti':[dict(voto,pk='v2')]})
            self.sync('voti',{'voti':[dict(voto,pk='v2',valore=9)]})
            self.assertEqual(notify.call_count,1)

    def test_registro_corretto_rimuove_la_vecchia_ora_e_cancellazione_svuota(self):
        r={'pk':'r1','datGiorno':'2026-10-15','ora':1,'materia':'Storia','docente':'Demo'}
        self.sync('registro',{'registro':[r]})
        self.sync('registro',{'registro':[dict(r,ora=2)]})
        self.assertEqual([r['ora'] for r in self.righe('lezioni_registro')],[2])
        self.sync('registro',{'registro':[{'pk':'r1','operazione':'D'}]})
        self.assertEqual(self.righe('lezioni_registro'),[])

    def test_medie_salvate_dalla_stessa_risposta(self):
        self.sync('voti',{'voti':[],'mediaGenerale':8.5,'mediaMaterie':{}})
        conn=models.get_db();self.assertEqual(models.media_argo(conn,self.st['nome'])['generale'],8.5);conn.close()
        self.sync('voti',{'voti':[{'pk':'inesistente','operazione':'D'}]})
        conn=models.get_db();self.assertIsNone(models.media_argo(conn,self.st['nome']));conn.close()

    def test_compiti_di_tipo_errato_non_ritirano_attivita_esistenti(self):
        r={'pk':'r1','materia':'Italiano','compiti':[{'dataConsegna':'2026-10-28','compito':'Leggere'}]}
        self.sync('compiti',{'registro':[r]})
        prima=self.stato('compiti')
        for errato in ({},'',False):
            self.assertFalse(self.sync('compiti',{'registro':[dict(r,compiti=errato)]})[0])
            self.assertEqual(len(self.righe('compiti')),1)
            self.assertEqual(self.stato('compiti'),prima)

    def test_errore_scrittura_cursore_annulla_anche_i_dati_dello_stesso_batch(self):
        get_db_originale = models.get_db
        class Connessione:
            def __init__(self): self.conn=get_db_originale()
            def execute(self, sql, args=()):
                if sql.startswith('INSERT OR REPLACE INTO meta(chiave,valore)'):
                    raise sqlite3.OperationalError('Disco simulato pieno')
                return self.conn.execute(sql,args)
            def __getattr__(self,name):return getattr(self.conn,name)
        with patch('sync_argo.get_db',side_effect=[get_db_originale(),get_db_originale(),Connessione()]),patch('argo_client.dashboard_sync',return_value={'voti':[{'pk':'v1','datGiorno':'2026-10-15','desMateria':'Storia','valore':8}]}):
            self.assertFalse(sync_argo.sincronizza([self.st],('voti',)))
        self.assertEqual(self.righe('voti'),[])
        self.assertIsNone(self.stato('voti'))

    def test_cambio_profilo_durante_login_rilegge_lo_storico(self):
        self.sync('voti',{'voti':[]})
        chiamate=[]
        def risposta(st,dal):
            chiamate.append(dal)
            if len(chiamate)==1:
                conn=models.get_db();models.svuota_studente(conn,self.st['nome']);conn.commit();conn.close()
            return {'voti':[]}
        with patch('argo_client.dashboard_sync',side_effect=risposta):
            self.assertTrue(sync_argo.sincronizza([self.st],('voti',)))
        self.assertEqual(len(chiamate),2)
        self.assertEqual(chiamate[-1],datetime(2026,8,25))


class TrasportoTest(unittest.TestCase):
    def test_richiesta_dal_punto_preciso_e_mai_ripiego_giornaliero(self):
        risposta=Mock();risposta.json.return_value={'success':True,'data':{'dati':[{'voti':[]}]}}
        with patch('argo_client.get_session',return_value=Mock()),patch('argo_client.requests.post',return_value=risposta) as post:
            self.assertEqual(argo_client.dashboard_sync(STUDENTI[0],datetime(2026,8,25)),{'voti':[]})
            self.assertEqual(post.call_args.kwargs['json']['dataultimoaggiornamento'],'2026-08-25 00:00:00')
            risposta.json.return_value={'success':False,'data':{'dati':[{}]}}
            with self.assertRaises(argo_client.ArgoSyncError):argo_client.dashboard_sync(STUDENTI[0],datetime(2026,8,25))
            self.assertEqual(post.call_count,2)

    def test_risposta_parziale_o_senza_profili_non_e_verificata(self):
        with patch('argo_client.get_session',return_value=Mock()),patch('argo_client.requests.post') as post:
            for payload in ({'data':{'dati':[]}}, {'hasMore':True,'data':{'dati':[{}]}},
                            {'data':{'dati':[{'parziale':True}]}}, {'data':{'dati':[None]}}):
                post.return_value.json.return_value=payload
                with self.assertRaises(argo_client.ArgoSyncError):argo_client.dashboard_sync(STUDENTI[0],datetime(2026,8,25))
