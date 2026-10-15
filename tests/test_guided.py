import importlib
import json
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from uuid import uuid4

_tmp = tempfile.TemporaryDirectory()
os.environ['DATABASE_PATH'] = _tmp.name + '/test.db'
os.environ['COOKIE_SECURE'] = 'false'
from app import app, db
from guided import active_questions, analyse, deliver

class IntakeTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()
        self.client.get('/intake/individual')
        with self.client.session_transaction() as s: self.csrf=s['intake_csrf']

    def answers(self, kind):
        a={q['key']: (q['choices'][-1] if q['choices'] else 'Sample') for q in active_questions(kind,{})}
        a.update(full_name='Sample Client', email='sample@example.com', filing_year='2025',consent='I agree')
        if kind=='individual': a['residency']='Resident all year'
        for q in active_questions(kind,a):
            a.setdefault(q['key'],'Sample')
        return a

    def send(self, kind, a, key=None):
        return self.client.post('/api/intake/'+kind+'/submit', json=dict(csrf=self.csrf,answers=a),headers={'Idempotency-Key': key or str(uuid4())})

    def test_both_flows_save_and_duplicate_retry(self):
        for kind in ('individual','business'):
            a=self.answers(kind); key=str(uuid4())
            r=self.send(kind,a,key);self.assertEqual(r.status_code,200)
            self.assertTrue(r.json['analysis']['documents'])
            self.assertEqual(self.send(kind,a,key).json['id'],key)
            with db() as con: self.assertEqual(con.execute('SELECT count(*) FROM guided_submissions WHERE id=?',(key,)).fetchone()[0],1)

    def test_hidden_answers_do_not_affect_analysis(self):
        a=self.answers('individual');a.update(dependents='No',dependent_facts='Stale data')
        r=self.send('individual',a)
        with db() as con: stored=json.loads(con.execute('SELECT answers_json FROM guided_submissions WHERE id=?',(r.json['id'],)).fetchone()[0])
        self.assertNotIn('dependent_facts',stored)

    def test_validation_csrf_consent(self):
        a=self.answers('business');a['consent']='I do not agree'
        self.assertEqual(self.send('business',a).status_code,400)
        a['consent']='I agree';a['entity']='invalid'
        self.assertEqual(self.send('business',a).status_code,400)
        self.assertEqual(self.client.post('/api/intake/business/submit',json={'answers':a}).status_code,403)

    def test_protected_workspace(self):
        self.assertEqual(self.client.get('/intake-team').status_code,302)
        with self.client.session_transaction() as s:s['logged_in']=True
        self.assertEqual(self.client.get('/intake-team').status_code,200)

    def test_adaptive_and_documents(self):
        a={'self_employed':'Yes','dependents':'No','residency':'Resident all year','filing_year':'2025'}
        keys=[q['key'] for q in active_questions('individual',a)]
        self.assertIn('gig_details',keys);self.assertNotIn('dependent_facts',keys)
        self.assertTrue(any('mileage' in x['title'] for x in analyse('individual',a)['documents']))

    def test_notification_retry_and_no_answers_in_email(self):
        r=self.send('individual',self.answers('individual'));key=r.json['id']
        config=dict(SMTP_HOST='smtp.example.com',SMTP_USER='sender',SMTP_PASSWORD='test',MAIL_FROM='sender@example.com',INTAKE_NOTIFY_TO='team@example.com',PUBLIC_BASE_URL='https://example.com')
        with patch.dict(os.environ,config),app.app_context():
            with patch('guided.smtplib.SMTP',side_effect=OSError()):self.assertFalse(deliver(key))
            with patch('guided.smtplib.SMTP') as smtp:
                self.assertTrue(deliver(key));message=smtp.return_value.__enter__.return_value.send_message.call_args.args[0]
                self.assertNotIn('sample@example.com',message.get_content())
                self.assertIn(key,message.get_content())
                self.assertFalse(deliver(key))

    def test_explanation_fallback(self):
        with patch.dict(os.environ,{'OLLAMA_URL':''}):
            r=self.client.post('/api/intake/explain',json={'csrf':self.csrf,'kind':'individual','key':'wages'})
            self.assertEqual(r.json['mode'],'guided')

if __name__=='__main__':unittest.main()
