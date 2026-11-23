from datetime import timedelta

from fastapi import HTTPException

from src.contracts import TaskState
from src.fieldwork import current_point, get_point, get_task
from src.storage import register

APPOINTMENT_DAYS = 21


def appointment_board(task_id):
    with register() as ledger:
        return ledger.rows('''SELECT t.id,t.state,t.point_id,t.point_revision,t.focus_slot,t.delivered_day,t.goal,
            p.code,p.name,p.revision,p.pending_location,a.first_day,a.second_day,a.note,a.planned_by,
            COUNT(w.id) AS window_count,COALESCE(SUM(w.total),0) AS sample_total,
            MAX(CASE WHEN w.sample_day=a.first_day THEN w.id END) AS first_window_id,
            MAX(CASE WHEN w.sample_day=a.second_day THEN w.id END) AS second_window_id
            FROM outreach_tasks t JOIN disposal_points p ON p.id=t.point_id
            LEFT JOIN retest_appointments a ON a.task_id=t.id LEFT JOIN sampling_windows w ON w.task_id=t.id
            WHERE t.state='retesting' OR a.task_id IS NOT NULL OR t.id=%s
            GROUP BY t.id,p.id,a.task_id ORDER BY (t.id <=> %s) DESC,t.id DESC LIMIT 160''', (task_id, task_id))


def save_appointment(task_id, form, actor):
    with register(write=True) as ledger:
        task = get_task(ledger, task_id)
        if task['state'] != TaskState.RETESTING:
            raise HTTPException(409, '宣教登记后才能安排复测班次')
        current_point(get_point(ledger, task['point_id']), task['point_revision'])
        if (form.first_day <= task['delivered_day'] or
                form.second_day > task['delivered_day'] + timedelta(days=APPOINTMENT_DAYS)):
            raise HTTPException(409, '两次复测须安排在宣教后的 21 天内')
        captured = {row['sample_day'] for row in ledger.rows(
            'SELECT sample_day FROM sampling_windows WHERE task_id=%s', (task_id,))}
        existing = ledger.one('SELECT first_day,second_day FROM retest_appointments WHERE task_id=%s', (task_id,))
        submitted = (form.first_day, form.second_day)
        if captured and (not existing or len(captured) >= 2 or any(
                existing[key] in captured and existing[key] != day
                for key, day in zip(('first_day', 'second_day'), submitted))):
            raise HTTPException(409, '已入账日期必须保留，只能改约未完成的班次')
        if ledger.one('''SELECT id FROM sampling_windows WHERE point_id=%s AND point_revision=%s
            AND slot=%s AND sample_day IN (%s,%s) AND NOT (task_id <=> %s) LIMIT 1''',
            (task['point_id'], task['point_revision'], task['focus_slot'], form.first_day, form.second_day, task_id)):
            raise HTTPException(409, '同点位、同日期及时段已有观察记录，请改约')
        if ledger.one('''SELECT t.id FROM outreach_tasks t JOIN retest_appointments a ON a.task_id=t.id
            WHERE t.id<>%s AND t.point_id=%s AND t.point_revision=%s AND t.focus_slot=%s AND t.state='retesting'
            AND (a.first_day IN (%s,%s) OR a.second_day IN (%s,%s)) LIMIT 1''',
            (task_id, task['point_id'], task['point_revision'], task['focus_slot'],
             form.first_day, form.second_day, form.first_day, form.second_day)):
            raise HTTPException(409, '同一时段已为另一项宣教任务预留')
        ledger.execute('''INSERT INTO retest_appointments (task_id,first_day,second_day,note,planned_by)
            VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE first_day=%s,second_day=%s,note=%s,planned_by=%s''',
            (task_id, form.first_day, form.second_day, form.note, actor,
             form.first_day, form.second_day, form.note, actor))
        ledger.audit(actor, 'retest_appointed', task_id, form.model_dump(mode='json'))
        return {'task_id': task_id, **form.model_dump()}
