from datetime import timedelta

from fastapi import HTTPException

from src.cohort_evidence import TASK_SELECT, evidence_for
from src.contracts import Role, local_day
from src.fieldwork import current_point, required
from src.storage import register

TACTICS = {'accuracy': {'replace_signs', 'guided_sorting'}, 'overflow': {'stagger_window', 'alternate_point'}}
CANDIDATES = ''' WHERE t.state='followup' AND t.point_revision=p.revision AND p.pending_location IS NULL
    AND NOT EXISTS (SELECT 1 FROM cohort_handoff_members m WHERE m.task_id=t.id)'''


def cohort_board(task_id, handoff_id):
    with register() as ledger:
        candidates = ledger.rows(TASK_SELECT + CANDIDATES + ''' ORDER BY (t.id <=> %s) DESC,
            t.run_id DESC,t.cohort,t.goal,t.id LIMIT 160''', (task_id,))
        handoffs = ledger.rows('''SELECT h.*,t.run_id,t.cohort,t.goal,c.condition_type,c.note AS condition_note
            FROM cohort_handoffs h JOIN outreach_tasks t ON t.id=h.anchor_task_id
            LEFT JOIN observation_conditions c ON c.window_id=h.condition_window_id
            ORDER BY (h.id <=> %s) DESC,(h.closed_at IS NULL) DESC,h.id DESC LIMIT 80''', (handoff_id,))
        for handoff in handoffs:
            handoff['members'] = ledger.rows('''SELECT m.*,t.focus_slot,t.result,t.point_revision,p.revision,
                p.pending_location,p.code,p.name FROM cohort_handoff_members m JOIN outreach_tasks t ON t.id=m.task_id
                JOIN disposal_points p ON p.id=t.point_id WHERE m.handoff_id=%s ORDER BY p.code''', (handoff['id'],))
        if candidates:
            candidates[0]['evidence'] = evidence_for(ledger, candidates[0])
        return {'candidates': candidates, 'handoffs': handoffs}


def issue_handoff(task_id, form, actor):
    today = local_day()
    if not today <= form.due_day <= today + timedelta(days=30):
        raise HTTPException(409, '整改期限须在今天起 30 天内')
    with register(write=True) as ledger:
        anchor = required(ledger, TASK_SELECT + ' WHERE t.id=%s', task_id, '宣教任务')
        members = ledger.rows(TASK_SELECT + CANDIDATES + ' AND t.run_id=%s AND t.cohort=%s AND t.goal=%s',
                              (anchor['run_id'], anchor['cohort'], anchor['goal']))
        if not any(member['id'] == task_id for member in members):
            raise HTTPException(409, '仅当前地址、尚未派发整改的未达标宣教任务可发起交接')
        if form.tactic not in TACTICS[anchor['goal']]:
            raise HTTPException(409, '整改动作须匹配群组目标')
        if form.condition_window_id is not None:
            conditions = evidence_for(ledger, anchor)['verified_conditions']
            if not any(condition['window_id'] == form.condition_window_id for condition in conditions):
                raise HTTPException(409, '整改引用须为该任务目标时段的已签核有效观察')
        handoff_id = ledger.execute('''INSERT INTO cohort_handoffs
            (anchor_task_id,tactic,due_day,note,condition_window_id,issued_by,issued_day) VALUES (%s,%s,%s,%s,%s,%s,%s)''',
            (task_id, form.tactic, form.due_day, form.note, form.condition_window_id, actor, today))
        task_ids = [member['id'] for member in members]
        for member_id in task_ids:
            ledger.execute('INSERT INTO cohort_handoff_members (handoff_id,task_id) VALUES (%s,%s)', (handoff_id, member_id))
        ledger.audit(actor, 'cohort_handoff_issued', handoff_id, {'tasks': task_ids, **form.model_dump(mode='json')})
        return {'id': handoff_id, 'task_ids': task_ids}


def record_outcome(handoff_id, task_id, form, staff):
    actor = staff['username']
    with register(write=True) as ledger:
        handoff = required(ledger, 'SELECT * FROM cohort_handoffs WHERE id=%s', handoff_id, '整改交接')
        member = ledger.one('''SELECT m.outcome,t.point_revision,p.revision,p.pending_location
            FROM cohort_handoff_members m JOIN outreach_tasks t ON t.id=m.task_id
            JOIN disposal_points p ON p.id=t.point_id WHERE m.handoff_id=%s AND m.task_id=%s''', (handoff_id, task_id))
        if member is None:
            raise HTTPException(404, '此任务不在交接范围内')
        if handoff['closed_at'] or member['outcome'] or form.event_day < handoff['issued_day']:
            raise HTTPException(409, '现场结果须发生于派发后，且每个点位只能登记一次')
        if form.outcome == 'relocated':
            if staff['role'] != Role.ADMIN:
                raise HTTPException(403, '仅运营可确认旧址整改停止')
            if member['revision'] == member['point_revision']:
                raise HTTPException(409, '确认迁移后方可停止旧址整改')
        else:
            current_point(member, member['point_revision'])
        ledger.execute('''UPDATE cohort_handoff_members SET outcome=%s,event_day=%s,note=%s,recorded_by=%s,recorded_at=NOW()
            WHERE handoff_id=%s AND task_id=%s''', (form.outcome, form.event_day, form.note, actor, handoff_id, task_id))
        ledger.audit(actor, 'cohort_handoff_outcome', handoff_id, {'task_id': task_id, **form.model_dump(mode='json')})
        return {'task_id': task_id, 'outcome': form.outcome}


def close_handoff(handoff_id, form, actor):
    with register(write=True) as ledger:
        handoff = required(ledger, 'SELECT * FROM cohort_handoffs WHERE id=%s', handoff_id, '整改交接')
        if handoff['closed_at'] or ledger.one('''SELECT task_id FROM cohort_handoff_members
                WHERE handoff_id=%s AND outcome IS NULL LIMIT 1''', (handoff_id,)):
            raise HTTPException(409, '待所有点位登记现场结果后才能结案')
        ledger.execute('UPDATE cohort_handoffs SET closed_at=NOW(),closed_by=%s,close_note=%s WHERE id=%s',
                       (actor, form.note, handoff_id))
        ledger.audit(actor, 'cohort_handoff_closed', handoff_id, {'note': form.note})
        return {'id': handoff_id, 'state': 'closed'}
