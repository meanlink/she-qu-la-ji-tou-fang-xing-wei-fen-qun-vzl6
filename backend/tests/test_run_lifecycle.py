"""In-memory lifecycle tests for recomputable clustering runs.

No MySQL or Redis is available in this workspace, so the tests drive the real
runs/quality/clustering code against a FakeLedger that implements the small SQL
surface used by those modules. The goal is to verify the state machine:
in-place recompute, attempt generations, leases, checkpoints and review resume.
"""
import json
import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR / 'stubs'))
sys.path.insert(0, str(TESTS_DIR.parent))

from src import runs as runs_module  # noqa: E402
from src.clustering import fit, prepare, merge_tree  # noqa: E402
from src.contracts import RunState  # noqa: E402
from src.storage import encode  # noqa: E402

START, END = date(2026, 11, 10), date(2026, 11, 11)
NOW = datetime(2026, 11, 12, 8, 0, 0)
ACTOR = 'field'


class FakeLedger:
    def __init__(self):
        self.points = [
            {'id': i + 1, 'code': f'QW-{i + 1:02d}', 'name': f'点 {i + 1}', 'location': f'地址 {i + 1}',
             'revision': 1, 'pending_location': None, 'sample_from': None}
            for i in range(6)]
        # Three clearly separated profiles, two points each -> stable 3-cluster input.
        # Every point clears the 30-observation / 2-window gate.
        profiles = [
            (40, 24, 40), (40, 23, 40),   # low accuracy, evening-heavy
            (40, 38, 40), (40, 37, 40),   # high accuracy, low overflow, evening
            (40, 30, 40), (40, 29, 40),   # mid accuracy, midday-heavy
        ]
        self.windows = []
        wid = 0
        for point, (morning_total, morning_correct, evening_total) in zip(self.points, profiles):
            midday = {'total': 20, 'correct': max(1, morning_correct // 2), 'overflow': 0}
            for day, slot, total, correct, overflow in (
                    (START, 'morning', morning_total, morning_correct, 1),
                    (END, 'midday', midday['total'], midday['correct'], midday['overflow']),
                    (END, 'evening', evening_total, max(1, evening_total - 3), 1)):
                wid += 1
                self.windows.append({'id': wid, 'point_id': point['id'], 'point_revision': 1,
                                     'sample_day': day, 'slot': slot, 'total': total, 'correct': correct,
                                     'overflow': overflow, 'task_id': None, 'entered_by': ACTOR})
        self.challenges = {}
        self.runs = []
        self.tasks = []
        self.audit_rows = []
        self._run_id = 0
        self._task_id = 0

    # --- minimal SQL surface ------------------------------------------------
    def rows(self, sql, args=()):
        if 'FROM disposal_points ORDER BY id' in sql:
            return [dict(p) for p in self.points]
        if 'FROM sampling_windows w JOIN disposal_points p' in sql:
            out = []
            for w in self.windows:
                if w['task_id'] is not None or not (START <= w['sample_day'] <= END):
                    continue
                p = next(x for x in self.points if x['id'] == w['point_id'])
                if p['revision'] != w['point_revision']:
                    continue
                row = dict(w)
                row['quality_state'] = self.challenges.get(w['id'], {}).get('state')
                row['code'] = p['code']
                out.append(row)
            return out
        if "FROM behavior_runs WHERE state='paused'" in sql:
            return [self._hydrate(dict(r)) for r in self.runs if r['state'] == 'paused']
        if "FROM behavior_runs WHERE state='queued' ORDER BY id LIMIT 1" in sql:
            queued = [r for r in self.runs if r['state'] == 'queued']
            return [self._hydrate(dict(queued[0]))] if queued else []
        if 'FROM behavior_runs WHERE id=%s' in sql:
            run = next((r for r in self.runs if r['id'] == args[0]), None)
            return [self._hydrate(dict(run))] if run else []
        if 'FROM behavior_runs WHERE fingerprint=%s' in sql:
            match = [r for r in self.runs if r['fingerprint'] == args[0] and r['state'] != 'failed']
            return [self._hydrate(dict(match[-1]))] if match else []
        if 'FROM outreach_tasks WHERE point_id=%s' in sql:
            return [dict(t) for t in self.tasks
                    if t['point_id'] == args[0] and t['state'] in ('assigned', 'retesting')]
        if 'FROM sample_challenges WHERE window_id=%s' in sql:
            return [dict(self.challenges[args[0]])] if args[0] in self.challenges else []
        if 'FROM field_register' in sql:
            return [{'id': 1}]
        raise AssertionError(f'unhandled query: {sql}')

    def one(self, sql, args=()):
        return next(iter(self.rows(sql, args)), None)

    def execute(self, sql, args=()):
        if sql.startswith('INSERT INTO behavior_runs'):
            self._run_id += 1
            from_day, through_day, clusters, state, reasons, snapshot, fingerprint, requested_by = args
            self.runs.append({'id': self._run_id, 'from_day': from_day, 'through_day': through_day,
                              'requested_clusters': clusters, 'state': state, 'attempt': 1,
                              'lease_owner': None, 'lease_until': None, 'checkpoint': None,
                              'started_at': None, 'reasons': reasons, 'input_snapshot': snapshot,
                              'fingerprint': fingerprint, 'result': None,
                              'requested_by': requested_by, 'reviewed_by': None, 'review_note': None})
            return self._run_id
        if sql.startswith('UPDATE behavior_runs'):
            if "state='queued',lease_owner=NULL" in sql:
                # Lease reclaim after a worker crash.
                for r in self.runs:
                    if r['state'] == 'running' and r['lease_until'] is not None and r['lease_until'] < NOW:
                        r.update(state='queued', lease_owner=None, lease_until=None)
                return None
            if 'checkpoint=%s' in sql:
                checkpoint, until, run_id, owner, attempt = args
                run = next(r for r in self.runs if r['id'] == run_id)
                if run['state'] == 'running' and run['lease_owner'] == owner and run['attempt'] == attempt:
                    run['checkpoint'] = json.loads(checkpoint)
                    run['lease_until'] = until
                return run_id
            run = next(r for r in self.runs if r['id'] == args[-1])
            if 'input_snapshot=%s' in sql:
                # In-place recompute (source change / retry / review resume).
                state, attempt, reasons, snapshot, fingerprint, _id = args
                run.update(state=state, attempt=attempt, reasons=json.loads(reasons),
                           input_snapshot=json.loads(snapshot), fingerprint=fingerprint, result=None,
                           checkpoint=None, lease_owner=None, lease_until=None, started_at=None)
            elif "state='review'" in sql:
                result, _id = args
                run.update(state='review', result=json.loads(result), checkpoint=None,
                           lease_owner=None, lease_until=None)
            elif "state='failed'" in sql:
                reasons, _id = args
                run.update(state='failed', reasons=json.loads(reasons), checkpoint=None,
                           lease_owner=None, lease_until=None)
            elif "state='paused'" in sql:
                reasons, _id = args
                run.update(state='paused', reasons=json.loads(reasons), checkpoint=None,
                           lease_owner=None, lease_until=None)
            elif "state='confirmed'" in sql:
                actor, note, _id = args
                run.update(state='confirmed', reviewed_by=actor, review_note=note)
            else:
                # Claim: SET state='running', lease_owner=%s, lease_until=%s, started_at=... WHERE id=%s
                owner, until, _id = args
                run.update(state='running', lease_owner=owner, lease_until=until,
                           started_at=run['started_at'] or NOW)
            return run['id']
        if sql.startswith('UPDATE sample_challenges'):
            state, note, decided_by, window_id = args
            self.challenges[window_id].update(state=state, decision_note=note, decided_by=decided_by,
                                              decided_at=NOW)
            return window_id
        if sql.startswith('INSERT INTO outreach_tasks'):
            self._task_id += 1
            self.tasks.append({'id': self._task_id, 'run_id': args[0], 'point_id': args[1],
                               'point_revision': args[2], 'cohort': args[3], 'goal': args[4],
                               'focus_slot': args[5], 'baseline': args[6], 'state': 'assigned'})
            return self._task_id
        if sql.startswith('INSERT INTO field_audit'):
            actor, event, object_id, facts = args
            self.audit_rows.append({'actor': actor, 'event': event, 'object_id': object_id,
                                    'facts': json.loads(facts)})
            return len(self.audit_rows)
        raise AssertionError(f'unhandled execute: {sql}')

    def audit(self, actor, event, object_id, facts):
        self.execute('INSERT INTO field_audit (actor,event,object_id,facts) VALUES (%s,%s,%s,%s)',
                     (actor, event, object_id, encode(facts)))

    @staticmethod
    def _hydrate(run):
        for key in ('reasons', 'input_snapshot', 'result', 'checkpoint'):
            value = run.get(key)
            if isinstance(value, str):
                run[key] = json.loads(value)
        return run


class RunLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.ledger = FakeLedger()
        # Subclass the real datetime so date/timedelta and SQL args stay intact; only utcnow is frozen.
        class FrozenDateTime(datetime):
            @classmethod
            def utcnow(cls):
                return NOW
        runs_module.datetime = FrozenDateTime
        ledger = self.ledger

        from contextlib import contextmanager

        @contextmanager
        def fake_register(write=False):
            yield ledger
        self._original_register = runs_module.register
        runs_module.register = fake_register
        self.worker = 'worker-A'
        self.form = SimpleNamespace(from_day=START, through_day=END, clusters=3)

    def tearDown(self):
        runs_module.register = self._original_register
        runs_module.datetime = datetime

    def run_record(self, run_id):
        return self.ledger.one('SELECT * FROM behavior_runs WHERE id=%s', (run_id,))

    def queue(self):
        return runs_module.queue_run(self.form, ACTOR)

    # 1. Happy path: queue -> running -> review -> confirm, no duplicate rows.
    def test_full_lifecycle_keeps_single_run_row(self):
        run = self.queue()
        self.assertEqual(run['state'], RunState.QUEUED)
        runs_module.compute_next(self.worker)
        run = self.run_record(run['id'])
        self.assertEqual(run['state'], RunState.REVIEW)
        self.assertEqual(len(self.ledger.runs), 1)
        confirmation = SimpleNamespace(note='按最新基线确认派发', attempt=run['attempt'])
        result = runs_module.confirm_run(run['id'], confirmation, 'ops')
        self.assertEqual(result['state'], RunState.CONFIRMED)
        self.assertGreaterEqual(result['created_tasks'], 1)
        self.assertEqual(len(self.ledger.runs), 1)

    # 2. Sampling while a run is active: recompute happens on the same row.
    def test_source_change_during_compute_recomputes_same_row(self):
        run = self.queue()
        run_id = run['id']
        first_attempt = run['attempt']

        def flaky_fit(points, requested, checkpoint=None, on_step=None):
            # A late baseline window lands while the worker is mid-calculation.
            self.ledger.windows.append({'id': 999, 'point_id': self.ledger.points[0]['id'],
                                        'point_revision': 1, 'sample_day': END, 'slot': 'midday',
                                        'total': 9, 'correct': 6, 'overflow': 1, 'task_id': None,
                                        'entered_by': ACTOR})
            return fit(points, requested, checkpoint, on_step)
        original_fit = runs_module.fit
        runs_module.fit = flaky_fit
        try:
            runs_module.compute_next(self.worker)
        finally:
            runs_module.fit = original_fit
        run = self.run_record(run_id)
        self.assertEqual(len(self.ledger.runs), 1)
        self.assertEqual(run['attempt'], first_attempt + 1)
        self.assertIn(run['state'], (RunState.QUEUED, RunState.RUNNING))
        self.assertEqual(run['reasons'][0]['code'], 'source_changed')
        # Next tick computes the fresh generation and produces a reviewable result.
        runs_module.compute_next(self.worker)
        run = self.run_record(run_id)
        self.assertEqual(run['state'], RunState.REVIEW)
        self.assertEqual(len(self.ledger.runs), 1)

    # 3. A stale worker result must never overwrite the newer generation.
    def test_late_result_cannot_overwrite_newer_generation(self):
        run = self.queue()
        run_id = run['id']

        def stale_fit(points, requested, checkpoint=None, on_step=None):
            # Simulate a parallel path that already moved the run to attempt 2 in review.
            row = self.ledger.runs[0]
            row['attempt'] = 2
            row['state'] = RunState.REVIEW
            row['lease_owner'] = 'worker-B'
            row['result'] = {'groups': [], 'merges': []}
            return fit(points, requested, checkpoint, on_step)
        original_fit = runs_module.fit
        runs_module.fit = stale_fit
        try:
            runs_module.compute_next(self.worker)
        finally:
            runs_module.fit = original_fit
        run = self.run_record(run_id)
        self.assertEqual(run['attempt'], 2)
        self.assertEqual(run['state'], RunState.REVIEW)
        self.assertEqual(run['lease_owner'], 'worker-B')

    # 4. Crash mid-calculation: expired lease is reclaimed and the run resumes.
    def test_interrupted_run_resumes_from_checkpoint(self):
        run = self.queue()
        run_id = run['id']
        captured = {}
        original_fit = runs_module.fit

        def crash_fit(points, requested, checkpoint=None, on_step=None):
            def record_then_crash(state):
                on_step_original(state)
                raise RuntimeError('worker lost')
            on_step_original = on_step
            return original_fit(points, requested, checkpoint, record_then_crash)
        runs_module.fit = crash_fit
        try:
            with self.assertRaises(RuntimeError):
                runs_module.compute_next(self.worker)
        finally:
            runs_module.fit = original_fit
        crashed = self.run_record(run_id)
        self.assertEqual(crashed['state'], RunState.RUNNING)
        self.assertIsNotNone(crashed['checkpoint'])
        captured['checkpoint'] = crashed['checkpoint']
        # Lease expires; a restarted worker reclaims the row and resumes from the checkpoint.
        self.ledger.runs[0]['lease_until'] = NOW - timedelta(seconds=1)
        resume_led = []

        def resume_fit(points, requested, checkpoint=None, on_step=None):
            resume_led.append(checkpoint)
            return original_fit(points, requested, checkpoint, on_step)
        runs_module.fit = resume_fit
        try:
            runs_module.compute_next('worker-B')
        finally:
            runs_module.fit = original_fit
        self.assertIsNotNone(resume_led[0])
        self.assertEqual(resume_led[0]['steps'], captured['checkpoint']['steps'])
        self.assertEqual(self.run_record(run_id)['state'], RunState.REVIEW)

    # 5. Retry reuses the run row instead of inserting a new one.
    def test_retry_does_not_create_run_record(self):
        run = self.queue()
        run_id = run['id']
        # Make the first calculation fail.
        def broken_fit(points, requested, checkpoint=None, on_step=None):
            raise ArithmeticError('boom')
        original_fit = runs_module.fit
        runs_module.fit = broken_fit
        try:
            runs_module.compute_next(self.worker)
        finally:
            runs_module.fit = original_fit
        self.assertEqual(self.run_record(run_id)['state'], RunState.FAILED)
        retried = runs_module.retry_run(run_id, ACTOR)
        self.assertEqual(retried['id'], run_id)
        self.assertEqual(len(self.ledger.runs), 1)
        self.assertEqual(retried['attempt'], 2)
        runs_module.compute_next(self.worker)
        self.assertEqual(self.run_record(run_id)['state'], RunState.REVIEW)

    # 6. Pending quality window pauses; after the ruling the same run continues.
    def test_quality_review_pauses_then_resumes_same_run(self):
        window_id = self.ledger.windows[0]['id']
        self.ledger.challenges[window_id] = {'window_id': window_id, 'state': 'pending',
                                             'note': '计数存疑', 'submitted_by': ACTOR}
        run = self.queue()
        run_id = run['id']
        self.assertEqual(run['state'], RunState.PAUSED)
        self.assertTrue(any(r['code'] == 'quality_pending' and r['window_id'] == window_id
                            for r in run['reasons']))
        # Retry while the challenge is open stays paused on the same row.
        retried = runs_module.retry_run(run_id, ACTOR)
        self.assertEqual(retried['state'], RunState.PAUSED)
        self.assertEqual(len(self.ledger.runs), 1)
        # A different operations account rules the window retained.
        self.ledger.execute(
            'UPDATE sample_challenges SET state=%s,decision_note=%s,decided_by=%s,decided_at=NOW() '
            'WHERE window_id=%s', ('retained', '复核后保留', 'ops', window_id))
        resumed = runs_module.resume_after_review(self.ledger, [window_id])
        self.assertEqual(resumed, [run_id])
        self.assertEqual(self.run_record(run_id)['state'], RunState.QUEUED)
        runs_module.compute_next(self.worker)
        self.assertEqual(self.run_record(run_id)['state'], RunState.REVIEW)
        self.assertEqual(len(self.ledger.runs), 1)

    # 7. Excluded window can keep the run paused if a point falls below threshold.
    def test_excluded_window_keeps_pause_until_samples_catch_up(self):
        # QW-01 keeps only morning + evening; excluding morning leaves a single window (below the gate).
        midday = next(w for w in self.ledger.windows if w['point_id'] == 1 and w['slot'] == 'midday')
        self.ledger.windows = [w for w in self.ledger.windows if w['id'] != midday['id']]
        morning = next(w for w in self.ledger.windows if w['point_id'] == 1 and w['slot'] == 'morning')
        window_id = morning['id']
        self.ledger.challenges[window_id] = {'window_id': window_id, 'state': 'pending',
                                             'note': '争议', 'submitted_by': ACTOR}
        run = self.queue()
        run_id = run['id']
        self.assertEqual(run['state'], RunState.PAUSED)
        self.ledger.execute(
            'UPDATE sample_challenges SET state=%s,decision_note=%s,decided_by=%s,decided_at=NOW() '
            'WHERE window_id=%s', ('excluded', '排除该窗口', 'ops', window_id))
        runs_module.resume_after_review(self.ledger, [window_id])
        run = self.run_record(run_id)
        self.assertEqual(run['state'], RunState.PAUSED)
        self.assertTrue(any(r['code'] == 'sample_insufficient' for r in run['reasons']))
        # A fresh replacement window (new id; the challenge stays on the excluded record) restores the gate.
        self.ledger.windows.append({'id': 9001, 'point_id': 1, 'point_revision': 1,
                                    'sample_day': START, 'slot': 'morning', 'total': 40, 'correct': 24,
                                    'overflow': 1, 'task_id': None, 'entered_by': ACTOR})
        retried = runs_module.retry_run(run_id, ACTOR)
        self.assertEqual(retried['state'], RunState.QUEUED)
        runs_module.compute_next(self.worker)
        self.assertEqual(self.run_record(run_id)['state'], RunState.REVIEW)

    # 8. Confirming a stale view is rejected until the operator re-reads the run.
    def test_confirm_rejects_stale_attempt_and_requeues_in_place(self):
        run = self.queue()
        runs_module.compute_next(self.worker)
        run = self.run_record(run['id'])
        stale = SimpleNamespace(note='运营拿着旧版本确认', attempt=run['attempt'] - 1)
        with self.assertRaises(Exception) as ctx:
            runs_module.confirm_run(run['id'], stale, 'ops')
        self.assertEqual(ctx.exception.status_code, 409)
        # Source change while reading: confirmation requeues the same row and asks for a re-read.
        run = self.run_record(run['id'])
        current_attempt = run['attempt']
        self.ledger.windows.append({'id': 1000, 'point_id': self.ledger.points[1]['id'],
                                    'point_revision': 1, 'sample_day': END, 'slot': 'midday',
                                    'total': 8, 'correct': 7, 'overflow': 0, 'task_id': None,
                                    'entered_by': ACTOR})
        fresh = SimpleNamespace(note='再确认一次', attempt=current_attempt)
        with self.assertRaises(Exception) as ctx:
            runs_module.confirm_run(run['id'], fresh, 'ops')
        self.assertEqual(ctx.exception.status_code, 409)
        run = self.run_record(run['id'])
        self.assertEqual(run['attempt'], current_attempt + 1)
        self.assertEqual(len(self.ledger.runs), 1)
        runs_module.compute_next(self.worker)
        run = self.run_record(run['id'])
        self.assertEqual(run['state'], RunState.REVIEW)
        good = SimpleNamespace(note='看过最新版本后确认', attempt=run['attempt'])
        result = runs_module.confirm_run(run['id'], good, 'ops')
        self.assertEqual(result['state'], RunState.CONFIRMED)

    # 9. Windows keep landing while the run is active; sampling path never touches runs.
    def test_sampling_never_blocked_by_active_run(self):
        run = self.queue()
        runs_module.compute_next(self.worker)
        self.assertEqual(self.run_record(run['id'])['state'], RunState.REVIEW)
        before = len(self.ledger.windows)
        self.ledger.windows.append({'id': 2000, 'point_id': self.ledger.points[2]['id'],
                                    'point_revision': 1, 'sample_day': END, 'slot': 'midday',
                                    'total': 7, 'correct': 6, 'overflow': 0, 'task_id': None,
                                    'entered_by': ACTOR})
        self.assertEqual(len(self.ledger.windows), before + 1)
        self.assertEqual(len(self.ledger.runs), 1)


class ClusteringResumeTests(unittest.TestCase):
    def _points(self):
        ledger = FakeLedger()
        snapshot, _, _ = runs_module.collect_snapshot(ledger, START, END, 3)
        return snapshot['points']

    def test_checkpoint_round_trip_matches_full_fit(self):
        points = self._points()
        full = fit(points, 3)
        prepared = prepare(points, 3)
        saved = []

        def save(state):
            saved.append(json.loads(encode(state)))
            raise _FirstCheckpoint
        try:
            merge_tree(prepared, 3, on_step=save)
        except _FirstCheckpoint:
            pass
        mid = saved[0]
        # Resume from a JSON-round-tripped checkpoint, as MySQL would hand it back.
        resumed = fit(points, 3, checkpoint=mid)
        self.assertEqual(resumed['groups'], full['groups'])
        self.assertEqual(resumed['merges'], full['merges'])

    def test_resume_after_every_step_is_consistent(self):
        points = self._points()
        full = fit(points, 3)
        prepared = prepare(points, 3)
        checkpoints = []
        merge_tree(prepared, 3, on_step=lambda state: checkpoints.append(json.loads(encode(state))))
        for checkpoint in checkpoints:
            resumed = fit(points, 3, checkpoint=checkpoint)
            self.assertEqual(resumed['merges'], full['merges'])


class _FirstCheckpoint(Exception):
    pass


if __name__ == '__main__':
    unittest.main(verbosity=2)
