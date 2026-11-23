from fastapi import HTTPException

from src.fieldwork import current_point, get_point, required
from src.quality import WINDOW_SELECT
from src.storage import register


def list_conditions(window_id):
    with register() as ledger:
        return ledger.rows('''SELECT w.id,w.point_id,w.sample_day,w.slot,w.task_id,w.point_revision,
            w.total,w.correct,w.overflow,p.code,p.name,p.revision,p.pending_location,
            q.state AS quality_state,c.condition_type,c.state,c.note,c.reported_by,c.decision_note,c.decided_by
            FROM sampling_windows w JOIN disposal_points p ON p.id=w.point_id
            LEFT JOIN observation_conditions c ON c.window_id=w.id
            LEFT JOIN sample_challenges q ON q.window_id=w.id
            WHERE c.window_id IS NOT NULL OR w.point_revision=p.revision OR w.id=%s
            ORDER BY (w.id <=> %s) DESC,(c.state <=> 'pending') DESC,w.sample_day DESC,w.id DESC LIMIT 180''',
            (window_id, window_id))


def report_condition(window_id, form, actor):
    with register(write=True) as ledger:
        window = required(ledger, WINDOW_SELECT + ' WHERE w.id=%s', window_id, '采样窗口')
        current_point(get_point(ledger, window['point_id']), window['point_revision'])
        if ledger.one("SELECT window_id FROM sample_challenges WHERE window_id=%s AND state='excluded'", (window_id,)):
            raise HTTPException(409, '已排除的观察窗口无法登记现场条件')
        if ledger.one('SELECT window_id FROM observation_conditions WHERE window_id=%s', (window_id,)):
            raise HTTPException(409, '该观察窗口已有现场条件记录')
        ledger.execute('''INSERT INTO observation_conditions (window_id,condition_type,note,reported_by)
            VALUES (%s,%s,%s,%s)''', (window_id, form.condition_type, form.note, actor))
        ledger.audit(actor, 'observation_condition_reported', window_id, form.model_dump())
        return {'window_id': window_id, 'state': 'pending'}


def decide_condition(window_id, form, actor):
    with register(write=True) as ledger:
        entry = required(ledger, 'SELECT * FROM observation_conditions WHERE window_id=%s', window_id, '现场条件记录')
        if entry['state'] != 'pending' or entry['reported_by'] == actor:
            raise HTTPException(409, '待核现场条件须由另一名运营人员签核')
        ledger.execute('''UPDATE observation_conditions SET state=%s,decision_note=%s,decided_by=%s,decided_at=NOW()
            WHERE window_id=%s''', (form.decision, form.note, actor, window_id))
        ledger.audit(actor, 'observation_condition_decided', window_id, form.model_dump())
        return {'window_id': window_id, 'state': form.decision}
