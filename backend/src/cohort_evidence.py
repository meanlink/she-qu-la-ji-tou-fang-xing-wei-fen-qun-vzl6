from src.fieldwork import required


TASK_SELECT = '''SELECT t.*,p.code,p.name,p.revision,p.pending_location
    FROM outreach_tasks t JOIN disposal_points p ON p.id=t.point_id'''


def evidence_for(ledger, task):
    run = required(ledger, 'SELECT input_snapshot FROM behavior_runs WHERE id=%s', task['run_id'], '分群运行')
    point = next(point for point in run['input_snapshot']['points'] if point['id'] == task['point_id'])
    baseline = [row['id'] for row in point['windows'] if row['slot'] == task['focus_slot']]
    retest = task['result']['window_ids']
    sources = {window_id: 'baseline' for window_id in baseline} | {window_id: 'retest' for window_id in retest}
    ids = tuple(sources)
    conditions = ledger.rows(f'''SELECT c.window_id,c.condition_type,c.note,w.sample_day,w.slot
        FROM observation_conditions c JOIN sampling_windows w ON w.id=c.window_id
        LEFT JOIN sample_challenges q ON q.window_id=c.window_id
        WHERE c.state='verified' AND (q.state IS NULL OR q.state='retained')
        AND c.window_id IN ({','.join(['%s'] * len(ids))}) ORDER BY w.sample_day,w.id''', ids) if ids else []
    for condition in conditions:
        condition['source'] = sources[condition['window_id']]
    return {'baseline_window_ids': baseline, 'retest_window_ids': retest, 'verified_conditions': conditions}
