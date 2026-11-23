import {canApprove, canEdit, state, taskById} from '../state.js';
import {badge, code, empty, formError, goalAction, goalLabel, input, labelSlot, note, paneHead, pct, stat, text, today} from '../ui.js';

function taskDetail(task) {
  if (!task) return empty('运营确认分群后，达到宣教条件的点位会出现在任务队列。');
  const baseline = task.baseline[task.goal === 'accuracy' ? 'correct' : 'overflow'] / task.baseline.total;
  const asOf = task.delivered_day ?? today();
  return `<div class="run-head">${paneHead(task.point_name, `任务 #${task.id} · 分群 #${task.run_id} / G${task.cohort} · 地址 V${task.point_revision}`)}${badge(task.state)}</div>
    <div class="assignment"><h3>${goalLabel(task.goal)} · ${labelSlot(task.focus_slot)}</h3><p>${goalAction(task.goal)}。</p></div>
    <div class="comparison"><div><span>基线 · ${task.baseline.total} 次观察</span><strong>${pct(baseline)}</strong></div>
    <div><span>复测 · ${task.retest_total} 次观察</span><strong>${task.result ? pct(task.result.retest_rate) : '未评估'}</strong></div></div>
    ${task.result ? `<p class="verdict">改善 ${task.result.gain_pp.toFixed(1)} 个百分点 · 目标 ${task.result.target_pp.toFixed(0)} 个百分点。${text(task.review_note)}</p>` : ''}
    ${task.state === 'retesting' ? `<p><a class="quiet-link" href="#appointments?task=${task.id}">安排同址复测 →</a></p>` : ''}
    ${task.state === 'followup' ? `<p><a class="quiet-link" href="#handoffs?task=${task.id}">查看群组整改 →</a></p>` : ''}
    ${task.pending_location ? '<p class="move-note">点位迁移待核，暂缓现场宣教与复测。</p>' : ''}
    ${task.state === 'assigned' && canEdit() && !task.pending_location ? `<form id="deliver-task" data-action="deliver" data-id="${task.id}">
      ${input('delivered_day', '现场宣教日期', `type="date" value="${asOf}" max="${today()}"`)}
      ${note('宣教执行记录', '例如：在桶前更换标识并做两轮现场示范')}${formError}<button>登记宣教已执行</button></form>` : ''}
    ${task.delivered_day ? `<p class="aside-note">${text(task.delivered_day)} 已宣教。${text(task.delivery_note)}</p>` : ''}
    ${task.state === 'retesting' && !task.pending_location ? `<div class="followup"><strong>复测进度</strong>
      <span>${task.retest_windows} / 2 个日期 · ${task.retest_total} / 20 次观察</span>
      ${canEdit() ? `<a href="#windows?task=${task.id}" class="quiet-link">登记同址同时段复测 →</a>` : ''}</div>
      ${canApprove() ? `<form id="review-task" data-action="review-task" data-id="${task.id}">
        ${note('复测审核记录', '填写现场复测结果及后续安排')}${formError}<button>评估并归档复测</button></form>` : ''}` : ''}`;
}

export function tasksPage(params) {
  const tasks = state.tasks;
  const selected = taskById(params.get('task')) ?? tasks[0];
  return `<div class="stats">${stat('待宣教', tasks.filter(t => t.state === 'assigned').length, '等待现场执行')}
    ${stat('复测中', tasks.filter(t => t.state === 'retesting').length, '执行后同址同段复测')}
    ${stat('已评估', tasks.filter(t => ['improved', 'followup'].includes(t.state)).length, '包含已改善与需跟进')}</div>
    <div class="split task-layout"><section class="pane">${paneHead('任务队列', '按点位查看执行进度。')}
    <ul class="task-list">${tasks.map(task => `<li><a href="#tasks?task=${task.id}" class="${selected?.id === task.id ? 'chosen' : ''}">
      <span><strong>${text(task.point_name)}</strong><small>${code(task.code)} · ${labelSlot(task.focus_slot)}</small></span>${badge(task.state)}</a></li>`).join('')}</ul>
    ${!tasks.length ? empty('暂无任务。运营确认分群后将在这里显示。') : ''}</section><aside class="pane entry">${taskDetail(selected)}</aside></div>`;
}
