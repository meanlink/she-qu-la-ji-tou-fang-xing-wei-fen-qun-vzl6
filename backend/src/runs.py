from collections import defaultdict
from hashlib import sha256

from fastapi import HTTPException

from src.clustering import fit
from src.contracts import RunState
from src.fieldwork import required
from src.storage import encode, register

MIN_ANONYMOUS = 30
MIN_WINDOWS = 2
MAX_POINTS = 80


def get_run(ledger, run_id):
    return required(ledger, 'SELECT * FROM behavior_runs WHERE id=%s', run_id, '分群运行')


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


def verify_source(ledger, run, actor):
    _, checksum, reasons = collect_snapshot(ledger, run['from_day'], run['through_day'], run['requested_clusters'])
    if checksum == run['fingerprint'] and not reasons:
        return True
    reasons.insert(0, {'code': 'source_changed'})
    ledger.execute("UPDATE behavior_runs SET state='paused',reasons=%s WHERE id=%s", (encode(reasons), run['id']))
    ledger.audit(actor, 'run_paused', run['id'], {'reasons': reasons})
    return False


def compute_next():
    with register(write=True) as ledger:
        run = ledger.one("SELECT * FROM behavior_runs WHERE state='queued' ORDER BY id LIMIT 1")
        if run is None or not verify_source(ledger, run, 'worker'):
            return
        try:
            result = fit(run['input_snapshot']['points'], run['requested_clusters'])
        except (ArithmeticError, ValueError, KeyError) as error:
            reasons = [{'code': 'calculation_failed'}]
            ledger.execute("UPDATE behavior_runs SET state='failed',reasons=%s WHERE id=%s", (encode(reasons), run['id']))
            ledger.audit('worker', 'run_failed', run['id'], {'error_type': type(error).__name__})
            return
        if result is None:
            reasons = [{'code': 'identical_profiles'}]
            ledger.execute("UPDATE behavior_runs SET state='paused',reasons=%s WHERE id=%s", (encode(reasons), run['id']))
            ledger.audit('worker', 'run_paused', run['id'], {'reasons': reasons})
            return
        ledger.execute("UPDATE behavior_runs SET state='review',result=%s WHERE id=%s", (encode(result), run['id']))
        ledger.audit('worker', 'run_computed', run['id'], {'groups': len(result['groups'])})


def confirm_run(run_id, form, actor):
    with register(write=True) as ledger:
        run = get_run(ledger, run_id)
        if run['state'] != RunState.REVIEW:
            raise HTTPException(409, '只有待运营确认的分群可发布')
        if not verify_source(ledger, run, actor):
            return {'id': run_id, 'state': RunState.PAUSED, 'created_tasks': 0}
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
