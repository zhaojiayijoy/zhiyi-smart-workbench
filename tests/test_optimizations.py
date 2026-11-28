"""Targeted regressions using disposable data only; no model/network calls."""
import hashlib
import io
import json
import sqlite3
import threading
import time
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import test_regressions
from app import auth, backup, db, edu


class OptimizationTests(unittest.TestCase):
    setUp = test_regressions.WorkbenchTests.setUp
    tearDown = test_regressions.WorkbenchTests.tearDown
    lesson = test_regressions.WorkbenchTests.lesson
    review = test_regressions.WorkbenchTests.review
    get = test_regressions.WorkbenchTests.get

    def submit(self, tid, content=b'one', request_key=''):
        return self.client.post(f'/api/student/task/{tid}/submit', headers=self.student,
                                data={'request_key': request_key},
                                files={'file': ('work.txt', content, 'text/plain')})

    def test_out_of_order_review_completion_binds_exact_versions(self):
        tid = self.lesson()
        first_started, release_first = threading.Event(), threading.Event()

        def evaluate(pid, text, name, **kwargs):
            if text == 'one':
                first_started.set()
                if not release_first.wait(10):
                    raise AssertionError('Second submission never completed')
            return {'dimensions': [{'name': 'Accuracy', 'score': 8, 'max': 10}], 'total': 8}

        with patch.object(edu, 'extract_text', side_effect=lambda n, b: (b.decode(), {})), \
             patch.object(edu, 'evaluate_submission', side_effect=evaluate), \
             ThreadPoolExecutor(2) as pool:
            first = pool.submit(self.submit, tid)
            try:
                self.assertTrue(first_started.wait(10))
                second_response = self.submit(tid, b'two')
                self.assertEqual(second_response.status_code, 200, second_response.text)
            finally:
                release_first.set()
            first_response = first.result(timeout=10)
        self.assertEqual(first_response.status_code, 200, first_response.text)
        one, two = first_response.json()['data'], second_response.json()['data']
        sid = one['submission_id']
        self.assertEqual(db.get_submission_version(sid, 1)['review_task_id'], one['review_task_id'])
        self.assertEqual(db.get_submission_version(sid, 2)['review_task_id'], two['review_task_id'])
        self.assertEqual(db.get_submission(sid)['review_task_id'], two['review_task_id'])
        response = self.client.patch(f'/api/review/{one["review_task_id"]}', headers=self.teacher,
                                     json={'scores': {'Accuracy': 6}, 'comment': 'Old version graded'})
        self.assertEqual(response.status_code, 200, response.text)
        old = db.get_submission_version(sid, 1)
        self.assertEqual((old['status'], old['score']), ('reviewed', 6))
        current = db.get_submission(sid)
        self.assertEqual((current['status'], current['score']), ('submitted', None))
        self.assertEqual(db.get_task(one['review_task_id'])['meta']['submission_version'], 1)

    def test_retry_does_not_create_version_or_call_model_twice(self):
        tid = self.lesson()
        key = '0123456789abcdef0123456789abcdef'
        with patch.object(edu, 'extract_text', return_value=('Text', {})) as extract, \
             patch.object(edu, 'evaluate_submission', return_value={'total': 90}) as evaluate:
            first = self.submit(tid, request_key=key).json()['data']
            retry = self.submit(tid, request_key=key)
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertTrue(retry.json()['data']['replayed'])
        self.assertEqual(retry.json()['data']['review_task_id'], first['review_task_id'])
        self.assertEqual(len(db.list_submission_versions(first['submission_id'])), 1)
        self.assertEqual(extract.call_count, 1)
        self.assertEqual(evaluate.call_count, 1)

    def test_duplicate_request_is_atomic_and_scoped(self):
        def submit(key, tid=10, student_id=None):
            return db.upsert_submission(project_id=self.a, task_id=tid, student_id=student_id or self.uid,
                                        student_no=str(student_id or self.uid), student_name='Alice', request_key=key)
        with ThreadPoolExecutor(4) as pool:
            results = list(pool.map(submit, ['same-request-key-123'] * 4))
        self.assertEqual(sum(not r.get('replayed') for r in results), 1)
        self.assertEqual(len(db.list_submission_versions(results[0]['id'])), 1)
        self.assertFalse(submit('same-request-key-123', tid=11).get('replayed'))
        self.assertFalse(submit('same-request-key-123', student_id=999).get('replayed'))

    def test_pending_retry_returns_conflict_without_new_model_call(self):
        tid = self.lesson()
        key = 'pending-request-12345'
        db.upsert_submission(project_id=self.a, task_id=tid, student_id=self.uid,
                             student_no='100001', student_name='Alice', request_key=key)
        with patch.object(edu, 'evaluate_submission') as model:
            response = self.submit(tid, request_key=key)
        self.assertEqual(response.status_code, 409)
        model.assert_not_called()

    def test_old_records_survive_newer_other_student_records(self):
        own = self.review()
        qa = db.save_task(prompt='My question', kind='qa', project_id=self.a,
                          meta={'student_no': '100001', 'feedback': 'My answer'})
        with db._conn() as conn:
            rows = [(self.a, kind, 'Other student', json.dumps({'student_no': '999999', 'status': 'published'}), time.time())
                    for kind in ('review', 'qa') for _ in range(210)]
            conn.executemany('INSERT INTO tasks(project_id,kind,prompt,meta,created_at) VALUES(?,?,?,?,?)', rows)
        d = self.get(f'/api/student/overview?project_id={self.a}').json()['data']
        self.assertEqual([r['id'] for r in d['my_reviews']], [own])
        self.assertEqual([r['id'] for r in d['my_qa']], [qa])
        self.assertEqual(self.get(f'/api/student/wrong?project_id={self.a}').json()['data']['total'], 1)

    def test_pagination_filters_drafts_and_handles_bad_legacy_json(self):
        ids = [self.review() for _ in range(5)]
        self.review(status='submitted', teacher={'comment': 'PRIVATE_DRAFT'})
        with db._conn() as conn:
            conn.execute('INSERT INTO tasks(project_id,kind,prompt,meta,created_at) VALUES(?,?,?,?,?)',
                         (self.a, 'review', 'Bad meta', '{invalid', time.time()))
        pages = [self.get(f'/api/student/overview?project_id={self.a}&offset={n}&limit=2').json()['data']
                 for n in (0, 2, 4)]
        self.assertEqual([r['id'] for d in pages for r in d['my_reviews']], list(reversed(ids)))
        self.assertEqual([d['pagination']['reviews_has_more'] for d in pages], [True, True, False])
        self.assertNotIn('PRIVATE_DRAFT', json.dumps(pages))

    def test_student_initial_password_uses_student_number(self):
        self.assertEqual(auth.initial_password('123456'), '123456')
        self.assertEqual(auth.initial_password('123'), '123')
        self.assertEqual(auth.initial_password('2024001234'), '001234')
        pwd = auth.initial_password('300003')
        auth.ensure_student_user('300003', 'New student', 'A')
        user, token = auth.login('student', '300003', pwd)
        self.assertTrue(user['must_change'])
        self.assertIsNone(user['activation_expires_at'])
        headers = {'Authorization': 'Bearer ' + token}
        self.assertEqual(self.client.get('/api/student/overview', headers=headers).status_code, 403)
        response = self.client.post('/api/auth/password', headers=headers,
                                    json={'old_password': pwd, 'new_password': 'New-secure-password'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(auth.resolve_token(token))
        self.assertFalse(auth.resolve_token(response.json()['data']['token'])['must_change'])
        self.assertIsNone(db.get_user(user['id'])['activation_expires_at'])

    def test_teacher_and_student_password_policy_and_session_invalidation(self):
        for headers, old in ((self.student, 'Student-test'), (self.teacher, 'Test-only-password-2026')):
            for password in ('short', 'x' * 257, old):
                response = self.client.post('/api/auth/password', headers=headers,
                                           json={'old_password': old, 'new_password': password})
                self.assertEqual(response.status_code, 400, response.text)
    def test_roster_import_creates_student_with_student_number_password(self):
        args = {'data': {'project_id': str(self.a)}, 'headers': self.teacher,
                'files': {'file': ('roster.csv', '学号,姓名,班级\n300003,Carol,A\n'.encode('utf-8'), 'text/csv')}}
        first = self.client.post('/api/students/import', **args)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertTrue(auth.verify_password('000003', db.get_user_by_username('300003')['password_hash']))
        second = self.client.post('/api/students/import', **args)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertTrue(auth.verify_password('000003', db.get_user_by_username('300003')['password_hash']))

    def test_login_limit_returns_retry_after_and_persists(self):
        body = {'role': 'student', 'username': '100001', 'password': 'wrong'}
        for _ in range(8):
            self.assertEqual(self.client.post('/api/auth/login', json=body).status_code, 401)
        body['password'] = 'Student-test'
        response = self.client.post('/api/auth/login', json=body)
        self.assertEqual(response.status_code, 429)
        self.assertGreater(int(response.headers['retry-after']), 0)
        db.initialize()
        self.assertEqual(self.client.post('/api/auth/login', json=body).status_code, 429)
        with db._conn() as conn:
            conn.execute('UPDATE login_attempts SET started_at=?', (time.time() - 901,))
        self.assertEqual(self.client.post('/api/auth/login', json=body).status_code, 200)

    def test_login_account_limit_is_atomic_across_sources(self):
        with ThreadPoolExecutor(8) as pool:
            results = list(pool.map(lambda n: db.reserve_login_attempt('account:test', f'source:{n}', 1000), range(24)))
        self.assertEqual(results.count(0), 8)
        self.assertTrue(all(r > 0 for r in results if r))
        db.clear_login_attempts('account:test')
        self.assertEqual(db.reserve_login_attempt('account:test', 'source:other', 1000), 0)

    def test_source_limit_preserves_shared_network_capacity(self):
        for n in range(200):
            self.assertEqual(db.reserve_login_attempt(f'account:{n}', 'source:school', 1000), 0)
        self.assertGreater(db.reserve_login_attempt('account:201', 'source:school', 1000), 0)
        self.assertEqual(db.reserve_login_attempt('account:201', 'source:other', 1000), 0)
        self.assertEqual(db.reserve_login_attempt('account:201', 'source:school', 1901), 0)

    def test_regular_reads_do_not_run_schema_or_migrations(self):
        trace = []
        connect = sqlite3.connect
        def traced(*args, **kwargs):
            conn = connect(*args, **kwargs)
            conn.set_trace_callback(trace.append)
            return conn
        with patch.object(db.sqlite3, 'connect', side_effect=traced):
            db.get_session(self.student['Authorization'][7:])
            db.list_rehearsals(self.a)
        forbidden = ('CREATE', 'ALTER', 'INSERT', 'UPDATE', 'DELETE')
        self.assertFalse([sql for sql in trace if sql.lstrip().upper().startswith(forbidden)], trace)
        with db._conn() as conn:
            conn.execute('SELECT 1')
        with self.assertRaises(sqlite3.ProgrammingError):
            conn.execute('SELECT 1')
        with self.assertRaises(ValueError):
            with db._conn() as failed:
                failed.execute("INSERT INTO projects(name,created_at) VALUES('Rollback',0)")
                raise ValueError('test rollback')
        self.assertFalse(any(p['name'] == 'Rollback' for p in db.list_projects()))
        with self.assertRaises(sqlite3.ProgrammingError):
            failed.execute('SELECT 1')

    def test_legacy_migration_invalidates_only_predictable_initial_accounts(self):
        uid = db.create_user(role='student', username='old', student_no='987654321',
                             password_hash=auth.hash_password('old'), must_change=1)
        old = auth.new_session(uid, 'student')
        with db._conn() as conn:
            conn.execute('ALTER TABLE users DROP COLUMN activation_expires_at')
            conn.execute('PRAGMA user_version=0')
        with patch.object(db, '_initialize', wraps=db._initialize) as initialize:
            db.initialize()
            db.initialize()
            self.assertEqual(initialize.call_count, 1)
        self.assertIsNone(db.get_session(old))
        self.assertTrue(auth.verify_password('654321', db.get_user(uid)['password_hash']))
        self.assertIsNotNone(auth.resolve_token(self.student['Authorization'][7:]))
        self.assertIsNotNone(auth.resolve_token(self.teacher['Authorization'][7:]))

    def backup_roots(self):
        roots = {name: Path(self.tmp.name) / name for name in ('uploads', 'exports', 'projects', 'custom')}
        for root in roots.values():
            root.mkdir()
            (root / 'file.txt').write_text(root.name, encoding='utf-8')
        db.set_project_folder(self.a, str(roots['projects']))
        db.set_project_folder(self.b, str(roots['custom']))
        return roots

    def make_backup(self, roots, extra=True):
        return backup.create_backup(project_root=roots['projects'], upload_root=roots['uploads'],
                                    export_root=roots['exports'], extra_roots=(roots['custom'],) if extra else ())

    def test_backup_includes_all_roots_hashes_and_restorable_wal_snapshot(self):
        roots = self.backup_roots()
        with db._conn() as live:
            live.execute('PRAGMA journal_mode=WAL')
            live.execute('PRAGMA wal_autocheckpoint=0')
            db.create_project('Committed while WAL is open')
            data = self.make_backup(roots)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertTrue({'workbench.db', 'uploads/file.txt', 'exports/file.txt', 'projects/file.txt',
                             'external/1/file.txt', 'manifest.json'}.issubset(archive.namelist()))
            manifest = json.loads(archive.read('manifest.json'))
            for entry in manifest['files']:
                content = archive.read(entry['path'])
                self.assertEqual(hashlib.sha256(content).hexdigest(), entry['sha256'])
                self.assertEqual(len(content), entry['size'])
            restored = Path(self.tmp.name) / 'restored.db'
            restored.write_bytes(archive.read('workbench.db'))
        with sqlite3.connect(restored, factory=db._Connection) as conn:
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertIsNotNone(conn.execute("SELECT id FROM projects WHERE name='Committed while WAL is open'").fetchone())

    def test_backup_rejects_unapproved_missing_or_linked_course_files(self):
        roots = self.backup_roots()
        with self.assertRaisesRegex(ValueError, '未授权'):
            self.make_backup(roots, extra=False)
        with patch.object(backup, '_linked', return_value=True):
            with self.assertRaisesRegex(ValueError, '链接'):
                self.make_backup(roots)
        db.set_project_folder(self.b, str(roots['custom'] / 'missing'))
        with self.assertRaisesRegex(ValueError, '不存在'):
            self.make_backup(roots)


if __name__ == '__main__':
    unittest.main()
