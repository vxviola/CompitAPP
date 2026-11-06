"""Exercise actual source with stdlib-only isolated collaborators (no network).

This does not replace integration tests with Flask/APScheduler/argofamiglia.
Run independently: python -X utf8 tests/test_sync_recovery_offline.py
"""
import ast
from collections import Counter
from datetime import datetime, date, timedelta, timezone
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1] / 'compitapp'

def module(name, values, only=None):
    tree = ast.parse((ROOT / (name + '.py')).read_text(encoding='utf-8'))
    tree.body = [n for n in tree.body if not isinstance(n, (ast.Import, ast.ImportFrom))
                 and (only is None or getattr(n, 'name', None) in only)]
    obj = types.ModuleType(name)
    obj.__dict__.update(values)
    exec(compile(tree, str(ROOT / (name + '.py')), 'exec'), obj.__dict__)
    return obj

class RequestError(Exception): pass
class FakeSession:
    def __init__(self, *args):
        self._ArgoFamiglia__headers = {'generation': 'fresh'}

def response(status=200, section=None):
    r = Mock(status_code=status)
    r.raise_for_status.side_effect = RequestError() if status >= 400 else None
    r.json.return_value = {'data': {'dati': [section or {'voti': []}]}}
    return r

class Recovery(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.models = module('models', dict(sqlite3=__import__('sqlite3'), os=__import__('os')))
        self.models.DB_PATH = str(Path(self.tmp.name) / 'test.db')
        self.models.init_db()
        self.requests = types.SimpleNamespace(RequestException=RequestError, post=Mock())
        self.state = module('sync_state', dict(json=json,threading=threading,datetime=datetime,get_db=self.models.get_db))
        self.scheduler = module('scheduler', dict(TZ=timezone.utc,datetime=datetime,POLLING_MINUTI=30,_scheduler=None,STATE_RUNNING=1,
            sync_state=self.state), only={'pianificazione_sync','_esegui_sync','sync_tutto'})
        self.argo = module('argo_client', dict(os=__import__('os'),json=json,time=time,threading=threading,secrets=__import__('secrets'),
            requests=self.requests,ArgoFamiglia=FakeSession,ArgoPassword=FakeSession,
            ArgoLoginError=type('ArgoLoginError',(Exception,),{}),ENDPOINT='offline://'))
        self.argo._scegli_profilo = Mock()
        self.ha = types.SimpleNamespace(avviso_sincronizzazione=Mock(),pubblica_diagnostica=Mock())
        constants = types.SimpleNamespace(DASHBOARD_OPTIONS={})
        self.mods = patch.dict(sys.modules, {'models':self.models, 'sync_state':self.state,'scheduler':self.scheduler,
            'argo_client':self.argo,'ha_client':self.ha,'argofamiglia.CONSTANTS':constants})
        self.mods.start(); self.addCleanup(self.mods.stop)
        self.sync = module('sync_argo', dict(json=json,sha256=sha256,Counter=Counter,date=date,datetime=datetime,
            timedelta=timedelta,urlencode=urlencode,pytz=types.SimpleNamespace(timezone=lambda _:timezone.utc),
            argo_client=self.argo,sync_state=self.state,get_db=self.models.get_db))
        self.sync._notifica = Mock()
        self.st = dict(nome='SYNTHETIC_A',codice_scuola='FAKE',username='FAKE',password='FAKE',alunno=2)
        self.old = FakeSession()
        self.argo._sessions[self.st['nome']] = self.old
        self.scheduler.get_studenti = lambda:[self.st]
        self.scheduler._ciclo_sync = lambda:None

    def fetch(self): return self.argo.dashboard_sync(self.st,datetime(2026,9,1))

    def test_401_recovers_once_same_cursor_and_profile(self):
        self.requests.post.side_effect=[response(401),response()]
        self.assertEqual(self.fetch(),{'voti':[]})
        self.assertEqual(self.requests.post.call_count,2)
        self.assertIsNot(self.argo._sessions[self.st['nome']],self.old)
        self.argo._scegli_profilo.assert_called_once()
        self.assertEqual(self.argo._scegli_profilo.call_args.args[1],self.st)
        self.assertEqual(self.requests.post.call_args_list[0].kwargs['json'],self.requests.post.call_args_list[1].kwargs['json'])

    def test_spid_401_does_not_add_reset_or_immediate_retry(self):
        self.st['accesso'] = 'spid'
        self.argo._sessioni_creata[self.st['nome']] = time.time()
        self.requests.post.return_value = response(401)
        with self.assertRaises(self.argo.ArgoSyncError) as exc:
            self.fetch()
        self.assertEqual(exc.exception.categoria, 'accesso')
        self.assertEqual(self.requests.post.call_count, 1)
        self.assertIs(self.argo._sessions[self.st['nome']], self.old)
        self.argo._scegli_profilo.assert_not_called()

    def test_two_401_are_bounded_and_next_cycle_can_recover(self):
        self.requests.post.side_effect=[response(401),response(401),response()]
        with self.assertRaises(self.argo.ArgoSyncError) as exc:self.fetch()
        self.assertEqual(exc.exception.categoria,'accesso')
        self.assertEqual(self.requests.post.call_count,2)
        self.assertNotIn(self.st['nome'],self.argo._sessions)
        self.fetch()
        self.assertEqual(self.requests.post.call_count,3)

    def test_non_auth_errors_do_not_relogin_and_recover_next_call(self):
        for code,kind in [(403,'permessi'),(429,'limite'),(500,'servizio'),(503,'servizio')]:
            with self.subTest(code=code):
                self.requests.post.side_effect=[response(code),response()]
                with self.assertRaises(self.argo.ArgoSyncError) as exc:self.fetch()
                self.assertEqual(exc.exception.categoria,kind)
                self.assertIs(self.argo._sessions[self.st['nome']],self.old)
                self.fetch()
        self.argo._scegli_profilo.assert_not_called()

    def test_network_failure_is_safe_and_does_not_reset(self):
        self.requests.post.side_effect=RequestError('private URL/token')
        with self.assertRaises(self.argo.ArgoSyncError) as exc:self.fetch()
        self.assertEqual(exc.exception.categoria,'rete')
        self.assertNotIn('private',str(exc.exception))
        self.assertIs(self.argo._sessions[self.st['nome']],self.old)

    def test_malformed_response_no_reset(self):
        r=response();r.json.side_effect=ValueError('private payload')
        self.requests.post.return_value=r
        with self.assertRaises(self.argo.ArgoSyncError) as exc:self.fetch()
        self.assertEqual(exc.exception.categoria,'risposta')
        self.argo._scegli_profilo.assert_not_called()

    def test_concurrent_new_session_is_not_invalidated(self):
        fresh=FakeSession()
        def first(*args,**kwargs):
            self.argo._sessions[self.st['nome']]=fresh
            self.requests.post.side_effect=None
            self.requests.post.return_value=response()
            return response(401)
        self.requests.post.side_effect=first
        self.fetch()
        self.assertIs(self.argo._sessions[self.st['nome']],fresh)
        self.argo._scegli_profilo.assert_not_called()

    def test_other_profile_session_is_preserved(self):
        other=FakeSession();self.argo._sessions['SYNTHETIC_B']=other
        self.requests.post.side_effect=[response(401),response()]
        self.fetch()
        self.assertIs(self.argo._sessions['SYNTHETIC_B'],other)

    def test_database_cursor_and_rows_preserved_then_no_duplicates(self):
        section={'voti':[dict(pk='fake-event',datGiorno='2026-10-01',desMateria='SYNTHETIC',valore=8)]}
        self.requests.post.return_value=response(section=section)
        self.assertTrue(self.sync.sincronizza([self.st],('voti',)))
        def snapshot():
            c=self.models.get_db()
            try:return [tuple(r) for r in c.execute('SELECT * FROM voti')], [tuple(r) for r in c.execute("SELECT * FROM meta WHERE chiave LIKE 'sync_eventi:%'")]
            finally:c.close()
        before=snapshot()
        self.requests.post.return_value=response(503)
        self.assertFalse(self.sync.sincronizza([self.st],('voti',)))
        self.assertEqual(snapshot(),before)
        self.requests.post.side_effect=[response(401),response(section=section)]
        self.assertTrue(self.sync.sincronizza([self.st],('voti',)))
        self.assertEqual(snapshot()[0],before[0])

    def test_lock_released_after_failure_and_state_preserves_success(self):
        self.scheduler.sync_tutto()
        success=self.state.leggi(self.st['nome'])['ultimo_successo']
        def fail():raise RuntimeError('private')
        self.scheduler._ciclo_sync=fail
        self.assertFalse(self.scheduler.sync_tutto())
        s=self.state.leggi(self.st['nome'])
        self.assertEqual(s['esito'],'errore');self.assertEqual(s['ultimo_successo'],success)
        self.assertFalse(self.state._lock.locked())
        self.scheduler._ciclo_sync=lambda:None
        self.assertTrue(self.scheduler.sync_tutto())
        self.assertEqual(self.state.leggi(self.st['nome'])['esito'],'ok')

    def test_stale_without_new_data_and_privacy_allowlist(self):
        old=(datetime.now(timezone.utc)-timedelta(hours=3)).isoformat()
        s=self.state.diagnostica(dict(esito='ok',ultimo_successo=old,nome='SECRET',token='SECRET',motivo='SECRET'))
        self.assertTrue(s['dati_obsoleti']);self.assertEqual(s['livello'],'attesa')
        self.assertNotIn('SECRET',json.dumps(s))
        self.assertIsNone(s['prossimo_tentativo'])

    def test_next_only_when_real_job_future(self):
        job=types.SimpleNamespace(next_run_time=datetime.now(timezone.utc)+timedelta(minutes=30))
        self.scheduler._scheduler=types.SimpleNamespace(state=1,get_job=lambda _:job)
        self.assertIsNotNone(self.state.diagnostica({})['prossimo_tentativo'])
        job.next_run_time=datetime.now(timezone.utc)-timedelta(seconds=1)
        self.assertIsNone(self.state.diagnostica({})['prossimo_tentativo'])
        self.scheduler._scheduler.state=2
        self.assertIsNone(self.state.diagnostica({})['prossimo_tentativo'])

    def test_error_stays_visible_during_attempt_and_profiles_isolated(self):
        self.state.inizia();self.state.errore(self.st['nome'],'rete');self.state.termina([self.st['nome'],'SYNTHETIC_B'])
        self.state.inizia()
        try:
            self.assertEqual(self.state.leggi(self.st['nome'])['livello'],'errore')
            self.assertEqual(self.state.leggi('SYNTHETIC_B')['esito'],'ok')
        finally:self.state.termina([self.st['nome'],'SYNTHETIC_B'])
        self.assertEqual(self.state.leggi(self.st['nome'])['livello'],'ok')

    def test_password_login_transient_categories_are_safe(self):
        auth=module('argo_auth',{},only={'ArgoLoginError','_fail'})
        for status,reason,category in [(503,'stato_http_inatteso','servizio'),(429,'stato_http_inatteso','limite'),
                                       (403,'stato_http_inatteso','permessi'),(200,'timeout','rete'),(401,'stato_http_inatteso','accesso')]:
            with self.subTest(category=category):
                with self.assertRaises(auth.ArgoLoginError) as exc:
                    auth._fail('token',reason,types.SimpleNamespace(status_code=status,headers={}))
                self.assertEqual(exc.exception.categoria,category)
                self.argo.ArgoLoginError=auth.ArgoLoginError
                self.argo.ArgoPassword=Mock(side_effect=exc.exception)
                self.argo._reset_session(self.st['nome'])
                with self.assertRaises(self.argo.ArgoSyncError) as failure:self.fetch()
                self.assertEqual(failure.exception.categoria,category)

    def test_publication_is_ordered_across_threads(self):
        self.scheduler.sync_tutto()
        entered=threading.Event();release=threading.Event();seen=[]
        def deliver(name,state):
            seen.append(state['esito'])
            if len(seen)==1:
                entered.set()
                if not release.wait(2):raise AssertionError('test timeout')
        self.ha.pubblica_diagnostica=deliver
        first=threading.Thread(target=self.state.pubblica,args=([self.st['nome']],))
        first.start();self.assertTrue(entered.wait(2))
        self.state.inizia();self.state.errore(self.st['nome'],'rete')
        second=threading.Thread(target=self.state.pubblica,args=([self.st['nome']],))
        second.start();release.set();first.join(2);second.join(2)
        self.assertFalse(first.is_alive());self.assertFalse(second.is_alive())
        self.assertEqual(seen,['ok','errore'])
        self.state.termina([self.st['nome']])

    def test_missing_student_list_still_releases_lock(self):
        def fail():raise RuntimeError('synthetic list failure')
        self.scheduler.get_studenti=fail
        self.assertFalse(self.scheduler.sync_tutto())
        self.assertFalse(self.state._lock.locked())

if __name__ == '__main__':unittest.main(verbosity=2)
