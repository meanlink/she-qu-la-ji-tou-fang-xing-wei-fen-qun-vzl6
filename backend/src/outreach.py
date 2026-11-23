from fractions import Fraction

from fastapi import HTTPException

from src.clustering import aggregate
from src.contracts import TaskState
from src.fieldwork import current_point, get_point, get_task
from src.storage import encode, register

MIN_RETEST = 20


def deliver(task_id, form, actor):
    with register(write=True) as ledger:
        task = get_task(ledger, task_id)
        if task['state'] != TaskState.ASSIGNED or form.delivered_day <= task['through_day']:
            raise HTTPException(409, '仅待执行任务可登记宣教，宣教日须晚于完整基线')
        current_point(get_point(ledger, task['point_id']), task['point_revision'])
        ledger.execute("UPDATE outreach_tasks SET state='retesting',delivered_day=%s,delivery_note=%s WHERE id=%s",
                       (form.delivered_day, form.note, task_id))
        ledger.audit(actor, 'outreach_delivered', task_id, form.model_dump(mode='json'))
        return get_task(ledger, task_id)


def review_retest(task_id, form, actor):
    with register(write=True) as ledger:
        task = get_task(ledger, task_id)
        if task['state'] != TaskState.RETESTING:
            raise HTTPException(409, '仅复测中的任务可以评估')
        current_point(get_point(ledger, task['point_id']), task['point_revision'])
        rows = ledger.rows('SELECT id,total,correct,overflow FROM sampling_windows WHERE task_id=%s ORDER BY id', (task_id,))
        retest = aggregate(rows)
        if retest['total'] < MIN_RETEST or len(rows) < 2:
            raise HTTPException(409, '复测至少需要两个不同日期、合计 20 次匿名观察')
        field = 'correct' if task['goal'] == 'accuracy' else 'overflow'
        baseline = task['baseline']
        before = Fraction(baseline[field], baseline['total'])
        after = Fraction(retest[field], retest['total'])
        gain = after - before if task['goal'] == 'accuracy' else before - after
        threshold = Fraction(5 if task['goal'] == 'accuracy' else 3, 100)
        state = TaskState.IMPROVED if gain >= threshold else TaskState.FOLLOWUP
        result = {'baseline_rate': float(before), 'retest_rate': float(after), 'gain_pp': float(100 * gain),
                  'target_pp': float(100 * threshold), 'counts': retest, 'window_ids': [r['id'] for r in rows]}
        ledger.execute('UPDATE outreach_tasks SET state=%s,result=%s,review_note=%s WHERE id=%s',
                       (state, encode(result), form.note, task_id))
        ledger.audit(actor, f'outreach_{state}', task_id, {'result': result, 'note': form.note})
        return get_task(ledger, task_id)
