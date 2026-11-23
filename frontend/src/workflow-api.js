export function workflowApi(call) {
  const read = (path, params, keys) => {
    const query = new URLSearchParams();
    for (const key of keys) if (params.has(key)) query.set(key, params.get(key));
    return call(`${path}?${query}`);
  };
  return {
    conditions: params => read('/observation-conditions', params, ['window']),
    appointments: params => read('/retest-appointments', params, ['task']),
    handoffs: params => read('/cohort-handoffs', params, ['task', 'handoff']),
    async workflowAction(form, fields) {
      const {action, id, task} = form.dataset;
      const routes = {
        'report-condition': `/observation-conditions/${id}`,
        'decide-condition': `/observation-conditions/${id}/decision`,
        'save-appointment': `/retest-appointments/${id}`,
        'issue-handoff': `/cohort-handoffs/from-task/${id}`,
        'handoff-outcome': `/cohort-handoffs/${id}/members/${task}`,
        'close-handoff': `/cohort-handoffs/${id}/close`,
      };
      if (action === 'issue-handoff') fields.condition_window_id = Number(fields.condition_window_id) || null;
      const result = await call(routes[action], fields);
      return {message: '工作记录已更新', location: action === 'issue-handoff' ? `#handoffs?handoff=${result.id}` : undefined};
    },
  };
}
