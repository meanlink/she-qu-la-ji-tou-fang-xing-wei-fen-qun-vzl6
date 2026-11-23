from datetime import timedelta

from fastapi import HTTPException

from src.contracts import TaskState, local_day
from src.storage import register
from src.window_reservations import reserve_window


def required(ledger, query, object_id, label):
    record = ledger.one(query, (object_id,))
    if record is None:
        raise HTTPException(404, f'{label}不存在')
    return record


def get_point(ledger, point_id):
    return required(ledger, 'SELECT * FROM disposal_points WHERE id=%s', point_id, '点位')


def get_task(ledger, task_id):
    return required(ledger, '''SELECT t.*, p.code, p.name AS point_name, r.through_day
        FROM outreach_tasks t JOIN disposal_points p ON p.id=t.point_id
        JOIN behavior_runs r ON r.id=t.run_id WHERE t.id=%s''', task_id, '宣教任务')


def add_point(form, actor):
    with register(write=True) as ledger:
        if ledger.one('SELECT id FROM disposal_points WHERE code=%s', (form.code,)):
            raise HTTPException(409, '点位编码已存在')
        data = form.model_dump()
        point_id = ledger.execute('INSERT INTO disposal_points (code,name,sector,location) VALUES (%s,%s,%s,%s)',
                                  (form.code, form.name, form.sector, form.location))
        ledger.audit(actor, 'point_registered', point_id, data)
        return get_point(ledger, point_id)


def propose_move(point_id, form, actor):
    with register(write=True) as ledger:
        point = get_point(ledger, point_id)
        if point['pending_location'] or point['location'] == form.location:
            raise HTTPException(409, '已有待核迁移，或新旧地址相同')
        ledger.execute('UPDATE disposal_points SET pending_location=%s,migration_note=%s WHERE id=%s',
                       (form.location, form.note, point_id))
        ledger.audit(actor, 'relocation_proposed', point_id, form.model_dump())
        return get_point(ledger, point_id)


def resolve_move(point_id, form, actor, approve):
    with register(write=True) as ledger:
        point = get_point(ledger, point_id)
        if not point['pending_location']:
            raise HTTPException(409, '当前点位没有待核迁移')
        facts = {'old_location': point['location'], 'proposed_location': point['pending_location'], 'note': form.note}
        if approve:
            sample_from = local_day() + timedelta(days=1)
            ledger.execute('''UPDATE disposal_points SET location=pending_location,revision=revision+1,
                sample_from=%s WHERE id=%s''', (sample_from, point_id))
            unfinished = ledger.rows("SELECT id FROM outreach_tasks WHERE point_id=%s AND state IN ('assigned','retesting')",
                                    (point_id,))
            for task in unfinished:
                ledger.execute("UPDATE outreach_tasks SET state='obsolete' WHERE id=%s", (task['id'],))
                ledger.audit(actor, 'outreach_obsoleted', task['id'], {'point_id': point_id, 'reason': 'relocated'})
            facts['sample_from'] = sample_from.isoformat()
        ledger.execute('UPDATE disposal_points SET pending_location=NULL,migration_note=NULL WHERE id=%s', (point_id,))
        ledger.audit(actor, 'relocation_confirmed' if approve else 'relocation_cleared', point_id, facts)
        return get_point(ledger, point_id)


def current_point(point, revision):
    if point['pending_location'] or point['revision'] != revision:
        raise HTTPException(409, '点位迁移待核或地址版本已改变')


def add_window(form, actor):
    with register(write=True) as ledger:
        point = get_point(ledger, form.point_id)
        current_point(point, point['revision'])
        if point['sample_from'] and form.sample_day < point['sample_from']:
            raise HTTPException(409, '新址采样须从迁移确认次日开始')
        if form.task_id is not None:
            task = get_task(ledger, form.task_id)
            if (task['state'] != TaskState.RETESTING or task['point_id'] != form.point_id
                    or task['point_revision'] != point['revision'] or task['focus_slot'] != form.slot
                    or form.sample_day <= task['delivered_day']):
                raise HTTPException(409, '复测须在宣教后、在任务对应的点位和时段采集')
        reserve_window(ledger, form, point['revision'])
        key = (form.point_id, point['revision'], form.sample_day, form.slot)
        if ledger.one('''SELECT id FROM sampling_windows WHERE point_id=%s AND point_revision=%s
                      AND sample_day=%s AND slot=%s''', key):
            raise HTTPException(409, '同一地址版本、日期和时段只能入账一次')
        window_id = ledger.execute('''INSERT INTO sampling_windows
            (point_id,point_revision,sample_day,slot,total,correct,overflow,task_id,entered_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)''', (*key, form.total, form.correct, form.overflow, form.task_id, actor))
        ledger.audit(actor, 'retest_window_recorded' if form.task_id else 'baseline_window_recorded', window_id,
                     form.model_dump(mode='json'))
        return {'id': window_id, 'point_revision': point['revision'], **form.model_dump()}
