import {canEdit, state} from '../state.js';
import {badge, code, empty, formError, input, labelSlot, note, paneHead, text, today} from '../ui.js';

function appointmentSlot(task, order, label) {
  const day = task[`${order}_day`];
  const windowId = task[`${order}_window_id`];
  const current = task.state === 'retesting' && task.revision === task.point_revision && !task.pending_location;
  let action = '<small>待到班</small>';
  if (windowId) action = `<a href="#conditions?window=${windowId}">查看窗口 #${windowId} →</a>`;
  else if (current && canEdit() && day <= today()) action = `<a href="#windows?task=${task.id}&day=${day}">录入该班次 →</a>`;
  return `<li><div><strong>${label}</strong><small>${code(day)} · ${labelSlot(task.focus_slot)}</small></div>${action}</li>`;
}

function detail(task) {
  if (!task) return empty('宣教登记后可以安排复测班次。');
  const active = task.state === 'retesting' && task.revision === task.point_revision && !task.pending_location;
  const canPlan = active && canEdit() && (task.window_count === 0 || (task.first_day && task.window_count === 1));
  const dates = ['first', 'second'].map((key, index) => {
    const day = task[`${key}_day`] ?? '';
    const fixed = task[`${key}_window_id`] ? 'readonly' : '';
    return input(`${key}_day`, index === 0 ? '首班日期' : '次班日期', `type="date" value="${day}" ${fixed}`);
  }).join('');
  return `${paneHead(`${task.code} · ${task.name}`, `任务 #${task.id} · ${labelSlot(task.focus_slot)} · V${task.point_revision}`)}
    <p class="workflow-source"><a href="#tasks?task=${task.id}">查看宣教任务 →</a> · 宣教日 ${code(task.delivered_day ?? '待登记')}</p>
    <div class="workflow-metrics"><div><small>已入账</small><strong>${task.window_count} / 2</strong></div><div><small>匿名投放观察</small><strong>${task.sample_total}</strong></div></div>
    ${task.first_day ? `<ol class="workflow-slots">${appointmentSlot(task, 'first', '首班')}${appointmentSlot(task, 'second', '次班')}</ol>
      <div class="workflow-record"><p>${text(task.note)}</p><small>排班人 ${text(task.planned_by)}</small></div>` : '<p class="aside-note">尚无约定班次。</p>'}
    ${canPlan ? `<form data-action="save-appointment" data-id="${task.id}"><div class="input-pair">${dates}</div>
      ${note('排班交接', '如巡查员与现场会合点，或改约原因')}${formError}<button>保存复测班次</button></form>` : ''}
    ${active && task.window_count >= 2 ? `<a class="quiet-link" href="#tasks?task=${task.id}">返回任务评估复测 →</a>` : ''}`;
}

export function appointmentsPage() {
  const tasks = state.appointments;
  const selected = tasks[0];
  return `<div class="split workflow-split"><section class="pane">${paneHead('同址复测队列', '在宣教后的 21 天内，预留同一时段的两个日期。')}
    <ul class="task-list workflow-list">${tasks.map(t => `<li><a href="#appointments?task=${t.id}" class="${selected.id === t.id ? 'chosen' : ''}">
      <span><strong>${text(t.name)}</strong><small>${code(t.code)} · ${labelSlot(t.focus_slot)} · 任务 #${t.id}</small></span>${t.first_day ? `<span class="workflow-tag">${t.window_count} / 2 已入账</span>` : badge(t.state)}</a></li>`).join('')}</ul>
    ${tasks.length ? '' : empty('暂无可排班的宣教任务。')}</section><aside class="pane entry">${detail(selected)}</aside></div>`;
}
