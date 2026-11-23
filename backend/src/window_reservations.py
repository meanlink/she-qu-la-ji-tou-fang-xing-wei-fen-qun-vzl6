from fastapi import HTTPException


def reserve_window(ledger, form, revision):
    if form.task_id is not None:
        assignment = ledger.one('SELECT first_day,second_day FROM retest_appointments WHERE task_id=%s', (form.task_id,))
        if assignment and form.sample_day not in {assignment['first_day'], assignment['second_day']}:
            raise HTTPException(409, '复测日期须匹配已约定的两个班次')
    reservation = ledger.one('''SELECT t.id FROM outreach_tasks t JOIN retest_appointments a ON a.task_id=t.id
        WHERE t.point_id=%s AND t.point_revision=%s AND t.focus_slot=%s AND t.state='retesting'
        AND %s IN (a.first_day,a.second_day) LIMIT 1''', (form.point_id, revision, form.slot, form.sample_day))
    if reservation and reservation['id'] != form.task_id:
        raise HTTPException(409, '此窗口已为指定宣教任务预留，请从复测排班进入')
