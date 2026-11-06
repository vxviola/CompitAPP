"""Integration with installed project dependencies; external services mocked."""
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import Mock, patch
from test_bacheca import DatabaseFixture, STUDENTI
import argo_client
import models
import scheduler
import sync_state
from app import app
from apscheduler.schedulers.background import BackgroundScheduler

class RecoveryIntegration(DatabaseFixture, unittest.TestCase):
    def setUp(self):
        super().setUp(); models.init_db()
        self.student=dict(STUDENTI[0],password='synthetic')

    def test_real_client_401_uses_new_session_once(self):
        old=Mock(); fresh=Mock()
        rejected=Mock(status_code=401)
        success=Mock(status_code=200)
        success.json.return_value={'data':{'dati':[{'voti':[]}]}}
        with patch.dict(argo_client._sessions,{self.student['nome']:old},clear=True), \
             patch.object(argo_client,'ArgoPassword',return_value=fresh) as login, \
             patch.object(argo_client,'_scegli_profilo') as profile, \
             patch.object(argo_client.requests,'post',side_effect=[rejected,success]) as post:
            self.assertEqual(argo_client.dashboard_sync(self.student,datetime(2026,9,1)),{'voti':[]})
            login.assert_called_once();profile.assert_called_once_with(fresh,self.student)
            self.assertEqual(post.call_count,2)

    def test_actual_apscheduler_pause_hides_next_run(self):
        sched=BackgroundScheduler(timezone='UTC')
        sched.add_job(lambda:None,'interval',hours=24,id='sync_tutto')
        sched.start()
        try:
            with patch.object(scheduler,'_scheduler',sched):
                self.assertIsNotNone(scheduler.pianificazione_sync()[0])
                sched.pause()
                self.assertIsNone(scheduler.pianificazione_sync()[0])
                sched.resume()
                self.assertIsNotNone(scheduler.pianificazione_sync()[0])
        finally:sched.shutdown(wait=False)

    def test_flask_home_stale_status_and_bootstrap_timestamp(self):
        import json
        stamp=(datetime.now(timezone.utc)-timedelta(hours=3)).isoformat()
        conn=models.get_db()
        conn.execute('INSERT OR REPLACE INTO meta(chiave,valore) VALUES (?,?)',
                     ('sync_ui:'+STUDENTI[0]['nome'],json.dumps({'esito':'ok','ultimo_successo':stamp})))
        conn.commit();conn.close()
        with patch('app.get_studenti',return_value=STUDENTI):
            client=app.test_client()
            html=client.get('/').text
            self.assertIn('sync-diagnostics attesa',html)
            self.assertIn('Dati non aggiornati di recente',html)
            self.assertIn('data-last-success="'+stamp+'"',html)
            result=client.get('/api/sync-status').json
            self.assertTrue(result['dati_obsoleti'])
            self.assertIsNone(result['prossimo_tentativo'])

if __name__=='__main__':unittest.main()
