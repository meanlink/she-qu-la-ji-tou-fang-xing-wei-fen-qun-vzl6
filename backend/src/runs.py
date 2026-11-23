import os
import socket
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from hashlib import sha256

from fastapi import HTTPException

from src.clustering import fit
from src.contracts import RunState
from src.fieldwork import required
from src.storage import encode, register

MIN_ANONYMOUS = 30
MIN_WINDOWS = 2
MAX_POINTS = 80
# A worker heartbeat tick is ~1s; a lease this long survives brief stalls without blocking resume.
LEASE_SECONDS = 30


def get_run(ledger, run_id):
    return required(ledger, 'SELECT * FROM behavior_runs WHERE id=%s', run_id, '分群运行')


def worker_identity():
    return f'{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}'


def collect_snapshot(ledger, start, end, clusters):
    points = ledger.rows('''SELECT id,code,name,location,revision,pending_location
        FROM disposal_points ORDER BY id''')
    windows = defaultdict(list)
    reviews = []
    for row in ledger.rows('''SELECT w.id,w.point_id,w.sample_day,w.slot,w.total,w.correct,w.overflow,q.state AS quality_state,p.code
        FROM sampling_windows w JOIN disposal_points p ON p.id=w.point_id AND p.revision=w.point_revision
        LEFT JOIN sample_challenges q ON q.window_id=w.id
        WHERE w.task_id IS NULL AND w.sample_day BETWEEN %s AND %s ORDER BY w.id''', (start, end)):
        quality_state = row.pop('quality_state')
        point_code = row.pop('code')
        if quality_state in {'pending', 'excluded'}:
            if quality_state == 'pending':
                reviews.append({'code': 'quality_pending', 'point': point_code, 'window_id': row['id']})
            continue
        row['sample_day'] = row['sample_day'].isoformat()
        windows[row.pop('point_id')].append(row)
    reasons = reviews.copy()
    if len(points) <= clusters:
        reasons.append({'code': 'too_few_points', 'required': clusters + 1, 'actual': len(points)})
    if len(points) > MAX_POINTS:
        reasons.append({'code': 'point_limit', 'limit': MAX_POINTS})
    for point in points:
        point['windows'] = windows[point['id']]
        total = sum(window['total'] for window in point['windows'])
        if point['pending_location']:
            reasons.append({'code': 'migration_pending', 'point': point['code']})
        if total < MIN_ANONYMOUS or len(point['windows']) < MIN_WINDOWS:
            reasons.append({'code': 'sample_insufficient', 'point': point['code'], 'samples': total,
                            'windows': len(point['windows']), 'required_samples': MIN_ANONYMOUS,
                            'required_windows': MIN_WINDOWS})
    snapshot = {'from_day': start.isoformat(), 'through_day': end.isoformat(),
                'clusters': clusters, 'points': points}
    if reviews:
        snapshot['quality_pending'] = reviews
    return snapshot, sha256(encode(snapshot).encode()).hexdigest(), reasons


def _requeue(ledger, run, snapshot, checksum, reasons, actor, attempt):
    """Re-evaluate a run against current source data and move it back onto the same run row."""
    state = RunState.PAUSED if reasons else RunState.QUEUED
    ledger.execute('''UPDATE behavior_runs SET state=%s,attempt=%s,reasons=%s,input_snapshot=%s,
        fingerprint=%s,result=NULL,checkpoint=NULL,lease_owner=NULL,lease_until=NULL,started_at=NULL WHERE id=%s''',
                   (state, attempt, encode(reasons), encode(snapshot), checksum, run['id']))
    ledger.audit(actor, f'run_{state}', run['id'],
                 {'attempt': attempt, 'fingerprint': checksum, 'reasons': reasons})
    return state


def queue_run(form, actor):
    with register(write=True) as ledger:
        snapshot, checksum, reasons = collect_snapshot(ledger, form.from_day, form.through_day, form.clusters)
        old = ledger.one('''SELECT id,reasons FROM behavior_runs WHERE fingerprint=%s AND state<>'failed'
            ORDER BY id DESC LIMIT 1''', (checksum,))
        # A stale snapshot can recur if an unconfirmed relocation is cleared.
        if old and all(reason['code'] != 'source_changed' for reason in old['reasons']):
            return get_run(ledger, old['id'])
        state = RunState.PAUSED if reasons else RunState.QUEUED
        run_id = ledger.execute('''INSERT INTO behavior_runs
            (from_day,through_day,requested_clusters,state,reasons,input_snapshot,fingerprint,requested_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)''', (form.from_day, form.through_day, form.clusters, state,
                                                  encode(reasons), encode(snapshot), checksum, actor))
        ledger.audit(actor, f'run_{state}', run_id, {'fingerprint': checksum, 'reasons': reasons})
        return get_run(ledger, run_id)


def retry_run(run_id, actor):
    """Retry keeps the original run row: re-check current source data and requeue in place."""
    with register(write=True) as ledger:
        run = get_run(ledger, run_id)
        if run['state'] not in (RunState.PAUSED, RunState.FAILED):
            raise HTTPException(409, '只有暂停或计算失败的分群可以重试')
        snapshot, checksum, reasons = collect_snapshot(
            ledger, run['from_day'], run['through_day'], run['requested_clusters'])
        _requeue(ledger, run, snapshot, checksum, reasons, actor, run['attempt'] + 1)
        return get_run(ledger, run_id)


def resume_after_review(ledger, window_ids):
    """Quality rulings may clear the last blocker: requeue affected paused runs on their own rows."""
    wanted = set(window_ids)
    resumed = []
    for run in ledger.rows("SELECT * FROM behavior_runs WHERE state='paused' ORDER BY id"):
        marks = {reason.get('window_id') for reason in run['reasons']
                 if reason.get('code') == 'quality_pending'}
        if not marks or not (marks & wanted):
            continue
        snapshot, checksum, reasons = collect_snapshot(
            ledger, run['from_day'], run['through_day'], run['requested_clusters'])
        if _requeue(ledger, run, snapshot, checksum, reasons, 'quality-review', run['attempt'] + 1) \
                == RunState.QUEUED:
            resumed.append(run['id'])
    return resumed


def compute_next(worker_id=None):
    worker_id = worker_id or worker_identity()
    with register(write=True) as ledger:
        # Recover runs whose worker died mid-calculation once their lease expires.
        ledger.execute('''UPDATE behavior_runs SET state='queued',lease_owner=NULL,lease_until=NULL
            WHERE state='running' AND lease_until IS NOT NULL AND lease_until < UTC_TIMESTAMP()''')
        run = ledger.one("SELECT * FROM behavior_runs WHERE state='queued' ORDER BY id LIMIT 1")
        if run is None:
            return None
        lease_until = datetime.utcnow() + timedelta(seconds=LEASE_SECONDS)
        # Conditional claim under the write lock: another worker cannot take the same run row.
        ledger.execute('''UPDATE behavior_runs SET state='running',lease_owner=%s,lease_until=%s,
            started_at=COALESCE(started_at, UTC_TIMESTAMP()) WHERE id=%s AND state='queued' ''',
                       (worker_id, lease_until, run['id']))
        run = get_run(ledger, run['id'])
        if run['state'] != RunState.RUNNING or run['lease_owner'] != worker_id:
            return None
        attempt = run['attempt']

    def persist(checkpoint):
        with register(write=True) as ledger:
            # Only the live generation may write checkpoints; stale workers become no-ops.
            ledger.execute('''UPDATE behavior_runs SET checkpoint=%s,lease_until=%s
                WHERE id=%s AND state='running' AND lease_owner=%s AND attempt=%s''',
                           (encode(checkpoint), datetime.utcnow() + timedelta(seconds=LEASE_SECONDS),
                            run['id'], worker_id, attempt))

    previous = run['checkpoint']
    try:
        result = fit(run['input_snapshot']['points'], run['requested_clusters'],
                     checkpoint=previous, on_step=persist)
    except (ArithmeticError, ValueError, KeyError) as error:
        with register(write=True) as ledger:
            current = get_run(ledger, run['id'])
            if current['attempt'] != attempt or current['lease_owner'] != worker_id:
                return None
            reasons = [{'code': 'calculation_failed'}]
            ledger.execute('''UPDATE behavior_runs SET state='failed',reasons=%s,checkpoint=NULL,
                lease_owner=NULL,lease_until=NULL WHERE id=%s''', (encode(reasons), run['id']))
            ledger.audit(worker_id, 'run_failed', run['id'],
                         {'attempt': attempt, 'error_type': type(error).__name__})
        return run['id']

    with register(write=True) as ledger:
        current = get_run(ledger, run['id'])
        if current['attempt'] != attempt or current['lease_owner'] != worker_id:
            # A newer generation superseded this calculation; the late result must never overwrite it.
            return None
        snapshot, checksum, reasons = collect_snapshot(
            ledger, current['from_day'], current['through_day'], current['requested_clusters'])
        if checksum != current['fingerprint'] or reasons:
            # Source data moved while computing: recompute on the same run row with a fresh generation.
            next_attempt = attempt + 1
            state = RunState.PAUSED if reasons else RunState.QUEUED
            if not reasons:
                reasons = [{'code': 'source_changed'}]
            ledger.execute('''UPDATE behavior_runs SET state=%s,attempt=%s,reasons=%s,input_snapshot=%s,
                fingerprint=%s,result=NULL,checkpoint=NULL,lease_owner=NULL,lease_until=NULL,started_at=NULL
                WHERE id=%s''', (state, next_attempt, encode(reasons), encode(snapshot), checksum, run['id']))
            ledger.audit(worker_id, f'run_{state}', run['id'],
                         {'attempt': next_attempt, 'reasons': reasons, 'superseded_attempt': attempt})
            return run['id']
        if result is None:
            reasons = [{'code': 'identical_profiles'}]
            ledger.execute('''UPDATE behavior_runs SET state='paused',reasons=%s,checkpoint=NULL,
                lease_owner=NULL,lease_until=NULL WHERE id=%s''', (encode(reasons), run['id']))
            ledger.audit(worker_id, 'run_paused', run['id'], {'attempt': attempt, 'reasons': reasons})
            return run['id']
        ledger.execute('''UPDATE behavior_runs SET state='review',result=%s,checkpoint=NULL,
            lease_owner=NULL,lease_until=NULL WHERE id=%s''', (encode(result), run['id']))
        ledger.audit(worker_id, 'run_computed', run['id'], {'attempt': attempt, 'groups': len(result['groups'])})
    return run['id']


def confirm_run(run_id, form, actor):
    with register(write=True) as ledger:
        run = get_run(ledger, run_id)
        if run['state'] != RunState.REVIEW:
            raise HTTPException(409, '只有待运营确认的分群可发布')
        if form.attempt != run['attempt']:
            raise HTTPException(409, '这版分群结果已过期，请重新查看最新结果后再确认')
        snapshot, checksum, reasons = collect_snapshot(
            ledger, run['from_day'], run['through_day'], run['requested_clusters'])
        if checksum != run['fingerprint'] or reasons:
            # Source changed while the operator was reading: requeue on the same row and ask for a re-read.
            next_attempt = run['attempt'] + 1
            state = RunState.PAUSED if reasons else RunState.QUEUED
            if not reasons:
                reasons = [{'code': 'source_changed'}]
            ledger.execute('''UPDATE behavior_runs SET state=%s,attempt=%s,reasons=%s,input_snapshot=%s,
                fingerprint=%s,result=NULL,checkpoint=NULL,lease_owner=NULL,lease_until=NULL,started_at=NULL
                WHERE id=%s''', (state, next_attempt, encode(reasons), encode(snapshot), checksum, run_id))
            ledger.audit(actor, f'run_{state}', run_id, {'attempt': next_attempt, 'reasons': reasons})
            raise HTTPException(409, '源数据已更新，分群正在按最新基线重算，请重新查看后再确认')
        candidates = [(group['number'], member) for group in run['result']['groups']
                      for member in group['members'] if member['action']]
        task_ids = []
        for cohort, member in candidates:
            if ledger.one("SELECT id FROM outreach_tasks WHERE point_id=%s AND state IN ('assigned','retesting')",
                          (member['point_id'],)):
                raise HTTPException(409, f"{member['code']} 尚有进行中的宣教任务")
            action = member['action']
            task_id = ledger.execute('''INSERT INTO outreach_tasks
                (run_id,point_id,point_revision,cohort,goal,focus_slot,baseline) VALUES (%s,%s,%s,%s,%s,%s,%s)''',
                (run_id, member['point_id'], member['revision'], cohort, action['goal'], action['focus_slot'], encode(action)))
            task_ids.append(task_id)
            ledger.audit(actor, 'outreach_assigned', task_id, {'run_id': run_id, 'point_id': member['point_id']})
        ledger.execute("UPDATE behavior_runs SET state='confirmed',reviewed_by=%s,review_note=%s WHERE id=%s",
                       (actor, form.note, run_id))
        ledger.audit(actor, 'run_confirmed', run_id, {'task_ids': task_ids, 'note': form.note})
        return {'id': run_id, 'state': RunState.CONFIRMED, 'created_tasks': len(task_ids)}
