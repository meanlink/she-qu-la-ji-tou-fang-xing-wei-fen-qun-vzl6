from typing import Literal

from fastapi import APIRouter, Depends, HTTPException

from src.contracts import Note, Role
from src.fieldwork import required
from src.security import allow, signed_in
from src.storage import register

router = APIRouter()
field_staff = allow(Role.ANALYST, Role.ADMIN)
operations = allow(Role.ADMIN)


class Decision(Note):
    decision: Literal['excluded', 'retained']


def initialize():
    with register() as ledger:
        ledger.execute('''CREATE TABLE IF NOT EXISTS sample_challenges (
          window_id INT PRIMARY KEY,
          state ENUM('pending','excluded','retained') NOT NULL DEFAULT 'pending',
          note VARCHAR(240) NOT NULL, submitted_by VARCHAR(40) NOT NULL,
          submitted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          decision_note VARCHAR(240), decided_by VARCHAR(40), decided_at TIMESTAMP NULL,
          FOREIGN KEY (window_id) REFERENCES sampling_windows(id),
          FOREIGN KEY (submitted_by) REFERENCES staff(username), FOREIGN KEY (decided_by) REFERENCES staff(username)
        ) CHARACTER SET utf8mb4''')
        ledger.execute('''CREATE TABLE IF NOT EXISTS overflow_dispatches (
          window_id INT PRIMARY KEY,
          state ENUM('requested','scheduled','resolved') NOT NULL DEFAULT 'requested',
          note VARCHAR(240) NOT NULL, requested_by VARCHAR(40) NOT NULL,
          requested_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          schedule_note VARCHAR(240), scheduled_by VARCHAR(40),
          outcome VARCHAR(240), resolved_by VARCHAR(40), resolved_at TIMESTAMP NULL,
          FOREIGN KEY (window_id) REFERENCES sampling_windows(id),
          FOREIGN KEY (requested_by) REFERENCES staff(username), FOREIGN KEY (scheduled_by) REFERENCES staff(username),
          FOREIGN KEY (resolved_by) REFERENCES staff(username)
        ) CHARACTER SET utf8mb4''')


WINDOW_SELECT = '''SELECT w.id,w.point_id,w.point_revision,w.sample_day,w.slot,w.total,w.correct,w.overflow,w.task_id,
                   p.code,p.name,p.revision,p.pending_location FROM sampling_windows w
                   JOIN disposal_points p ON p.id=w.point_id'''


@router.get('/quality')
def quality(_staff=Depends(signed_in)):
    with register() as ledger:
        windows = ledger.rows('''SELECT w.id,w.sample_day,w.slot,w.total,w.correct,w.overflow,p.code,p.name,
             q.state,q.note,q.submitted_by,q.decision_note,q.decided_by FROM sampling_windows w
             JOIN disposal_points p ON p.id=w.point_id LEFT JOIN sample_challenges q ON q.window_id=w.id
             WHERE (w.task_id IS NULL AND w.point_revision=p.revision) OR q.window_id IS NOT NULL
             ORDER BY (q.state='pending') DESC,w.sample_day DESC,w.id DESC LIMIT 180''')
        return windows


@router.post('/quality/{identifier}', status_code=201)
def challenge(identifier: int, data: Note, staff=Depends(field_staff)):
    with register(write=True) as ledger:
        window = required(ledger, WINDOW_SELECT + ' WHERE w.id=%s', identifier, '采样窗口')
        if window['task_id'] is not None or window['point_revision'] != window['revision']:
            raise HTTPException(409, '仅当前地址的基线样本可提交质量复核')
        if ledger.one('SELECT window_id FROM sample_challenges WHERE window_id=%s', (identifier,)):
            raise HTTPException(409, '此采样窗口已有复核记录')
        ledger.execute('INSERT INTO sample_challenges(window_id,note,submitted_by) VALUES (%s,%s,%s)',
                       (identifier, data.note, staff['username']))
        ledger.audit(staff['username'], 'sampling_challenged', identifier, {'note': data.note})
        return {'state': 'pending'}


@router.post('/quality/{identifier}/decision')
def decide(identifier: int, data: Decision, staff=Depends(operations)):
    with register(write=True) as ledger:
        ticket = required(ledger, 'SELECT * FROM sample_challenges WHERE window_id=%s', identifier, '质量复核单')
        if ticket['state'] != 'pending' or ticket['submitted_by'] == staff['username']:
            raise HTTPException(409, '需由另一名运营账号复核待处理窗口')
        ledger.execute('''UPDATE sample_challenges SET state=%s,decision_note=%s,decided_by=%s,decided_at=NOW()
                          WHERE window_id=%s''', (data.decision, data.note, staff['username'], identifier))
        ledger.audit(staff['username'], 'sampling_decided', identifier, {'state': data.decision, 'note': data.note})
        return {'state': data.decision}


def qualifies_for_dispatch(window):
    return (window['overflow'] >= 3 and window['overflow'] * 100 >= window['total'] * 15
            and window['point_revision'] == window['revision'] and not window['pending_location'])


@router.get('/overflow-dispatch')
def dispatch_board(_staff=Depends(signed_in)):
    with register() as ledger:
        return ledger.rows('''SELECT w.id,w.sample_day,w.slot,w.total,w.overflow,p.code,p.name,
             d.state,d.note,d.schedule_note,d.outcome FROM sampling_windows w JOIN disposal_points p ON p.id=w.point_id
             LEFT JOIN overflow_dispatches d ON d.window_id=w.id
             LEFT JOIN sample_challenges q ON q.window_id=w.id
             WHERE d.window_id IS NOT NULL OR (w.point_revision=p.revision AND p.pending_location IS NULL
                AND w.overflow>=3 AND w.overflow*100>=w.total*15 AND COALESCE(q.state,'retained')='retained')
             ORDER BY (d.state IN ('requested','scheduled')) DESC,w.sample_day DESC,w.id DESC LIMIT 160''')


@router.post('/overflow-dispatch/{identifier}', status_code=201)
def request_dispatch(identifier: int, data: Note, staff=Depends(field_staff)):
    with register(write=True) as ledger:
        window = required(ledger, WINDOW_SELECT + ' WHERE w.id=%s', identifier, '采样窗口')
        quality = ledger.one('SELECT state FROM sample_challenges WHERE window_id=%s', (identifier,))
        if not qualifies_for_dispatch(window) or (quality and quality['state'] != 'retained'):
            raise HTTPException(409, '需使用有效地址、未排除且满溢至少 3 次且达到 15% 的采样')
        if ledger.one('SELECT window_id FROM overflow_dispatches WHERE window_id=%s', (identifier,)):
            raise HTTPException(409, '此窗口已有清运工单')
        ledger.execute('INSERT INTO overflow_dispatches(window_id,note,requested_by) VALUES (%s,%s,%s)',
                       (identifier, data.note, staff['username']))
        ledger.audit(staff['username'], 'overflow_requested', identifier, {'note': data.note})
        return {'state': 'requested'}


@router.post('/overflow-dispatch/{identifier}/schedule')
def schedule(identifier: int, data: Note, staff=Depends(operations)):
    with register(write=True) as ledger:
        ticket = required(ledger, 'SELECT state FROM overflow_dispatches WHERE window_id=%s', identifier, '清运工单')
        if ticket['state'] != 'requested':
            raise HTTPException(409, '只可安排待调度工单')
        ledger.execute('''UPDATE overflow_dispatches SET state='scheduled',schedule_note=%s,scheduled_by=%s
                          WHERE window_id=%s''', (data.note, staff['username'], identifier))
        ledger.audit(staff['username'], 'overflow_scheduled', identifier, {'note': data.note})
        return {'state': 'scheduled'}


@router.post('/overflow-dispatch/{identifier}/resolve')
def resolve(identifier: int, data: Note, staff=Depends(field_staff)):
    with register(write=True) as ledger:
        ticket = required(ledger, 'SELECT state FROM overflow_dispatches WHERE window_id=%s', identifier, '清运工单')
        if ticket['state'] != 'scheduled':
            raise HTTPException(409, '安排清运后才可提交现场结果')
        ledger.execute('''UPDATE overflow_dispatches SET state='resolved',outcome=%s,resolved_by=%s,resolved_at=NOW()
                          WHERE window_id=%s''', (data.note, staff['username'], identifier))
        ledger.audit(staff['username'], 'overflow_resolved', identifier, {'note': data.note})
        return {'state': 'resolved'}
