import {canEdit, slots, state, taskById} from '../state.js';
import {code, formError, input, labelSlot, options, paneHead, pct, rowSet, stat, text, today} from '../ui.js';

export function windowsPage(params) {
  const active = state.points.filter(point => !point.pending_location);
  const task = taskById(params.get('task'));
  const appointmentDay = params.get('day');
  const sampleDay = task && /^\d{4}-\d{2}-\d{2}$/.test(appointmentDay ?? '') && appointmentDay <= today() ? appointmentDay : today();
  const filter = params.get('filter') ?? 'all';
  const windows = state.windows;
  const shown = windows.filter(window => filter === 'all' || (filter === 'retest' ? window.task_id : !window.task_id));
  const tally = windows.reduce((sum, window) => sum + window.total, 0);
  const valid = task ? task.state === 'retesting' && active.some(point => point.id === task.point_id) : active.length > 0;
  return `<div class="stats">${stat('采样窗口', windows.length, '最近 250 条内')}${stat('匿名观察', tally, '每次投放记为 1 次观察')}${stat('关联复测', windows.filter(w => w.task_id).length, '专用于对应宣教任务')}</div>
  <div class="split"><section class="pane">${paneHead('采样流水', '旧址样本保留在流水中，分群只读取当前地址版本。')}
    <div class="filters">${Object.entries({all: '全部窗口', baseline: '基线', retest: '复测'}).map(([key, label]) =>
      `<a href="#windows?filter=${key}" class="${filter === key ? 'chosen' : ''}">${label}</a>`).join('')}</div>
    <div class="table-wrap"><table><thead><tr><th>日期 / 时段</th><th>投放点</th><th>观察量</th><th>正确率</th><th>满溢</th><th>用途</th></tr></thead><tbody>
    ${rowSet(shown, w => `<tr><td>${code(w.sample_day)}<small>${labelSlot(w.slot)}</small></td><td>${text(w.point_name)}
    <small>${code(w.code)} · V${w.point_revision}${w.point_revision !== w.current_revision ? ' 旧址' : ''}</small></td>
    <td class="mono">${w.total}</td><td class="mono">${pct(w.correct / w.total, 0)}</td><td class="mono">${w.overflow}</td>
    <td>${w.task_id ? `<a href="#tasks?task=${w.task_id}">复测 #${w.task_id}</a>` : '基线'}<small><a href="#conditions?window=${w.id}">现场条件</a></small></td></tr>`, 6, '这个视图暂无采样窗口。')}
    </tbody></table></div></section>
  <aside class="pane entry">${paneHead(task ? '录入宣教复测' : '登记匿名窗口', task ? `${task.point_name} · ${labelSlot(task.focus_slot)} · 任务 #${task.id}` : '仅记录合计数，至少 5 次观察可入账。')}
    ${canEdit() && valid ? `<form id="add-window" data-action="window" data-task="${task?.id ?? ''}">
      <label>投放点<select name="point_id" required>${options(Object.fromEntries(active.filter(p => !task || p.id === task.point_id).map(p => [p.id, `${p.code} · ${p.name}`])), task?.point_id ?? params.get('point'))}</select></label>
      <div class="input-pair">${input('sample_day', '采样日期', `type="date" max="${today()}" value="${sampleDay}"`)}
      <label>时段<select name="slot" required>${options(task ? {[task.focus_slot]: slots[task.focus_slot]} : slots, task?.focus_slot)}</select></label></div>
      ${input('total', '投放观察数', 'type="number" min="5" max="1000"')}
      <div class="input-pair">${input('correct', '分类正确数', 'type="number" min="0" max="1000"')}${input('overflow', '满溢记录数', 'type="number" min="0" max="1000"')}</div>
      ${formError}<button>保存${task ? '复测' : '采样'}</button></form>` : '<p class="aside-note">当前岗位或点位状态暂不可录入。</p>'}
    <p class="aside-note">时段口径 · 早间 06–10 / 午间 11–14 / 晚间 17–21</p>
    ${task ? `<a href="#tasks?task=${task.id}" class="quiet-link">返回宣教任务 →</a>` : ''}
  </aside></div>`;
}
