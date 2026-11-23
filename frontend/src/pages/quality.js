import {state} from '../state.js';
import {badge, formError, labelSlot, note, paneHead, pct, rowSet, text} from '../ui.js';

const table = (headers, rows) => `<div class="table-wrap"><table><thead><tr>${headers.map(label => `<th>${label}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table></div>`;
const log = items => items.filter(Boolean).map(item => `<small>${text(item)}</small>`).join('<br>');
const form = (action, row, label, prompt, extra = '') => `<form data-action="${action}" data-id="${Number(row.id)}" class="quality-form">${extra}${note(label, prompt)}${formError}<button>${label}</button></form>`;

export function qualityPage() {
  const status = {pending: '待复核', excluded: '已排除', retained: '保留采样'};
  const rows = rowSet(state.quality, row => {
    let action = '';
    if (!row.state && state.staff.role !== 'viewer') action = form('challenge-window', row, '提交复核', '记录计数异常的现场依据');
    if (row.state === 'pending' && state.staff.role === 'admin' && row.submitted_by !== state.staff.username) {
      action = form('decide-window', row, '签署复核', '说明排除或保留的依据', '<label>复核结果<select name="decision"><option value="excluded">排除窗口</option><option value="retained">保留窗口</option></select></label>');
    }
    return `<tr><td><strong>${text(row.name)}</strong><br>${text(row.sample_day)} · ${labelSlot(row.slot)}</td><td>${row.total} 次 / 正确 ${row.correct}</td>
      <td>${badge(status[row.state] || '正常采样')}<br>${log([row.note, row.decision_note])}</td><td>${action}</td></tr>`;
  }, 4, '暂无当前地址的基线采样。');
  return `<section class="pane">${paneHead('基线采样质量复核', '待复核窗口暂停对应期间的分群。确认排除后，重跑时重新检查样本门槛。')}${table(['采样点位', '匿名计数', '复核进度', '业务操作'], rows)}</section>`;
}

export function overflowPage() {
  const status = {requested: '待调度', scheduled: '待清运确认', resolved: '已确认清运'};
  const rows = rowSet(state.overflowDispatch, row => {
    let action = '';
    if (!row.state && state.staff.role !== 'viewer') action = form('request-overflow', row, '申请清运', '说明满溢位置及现场影响');
    if (row.state === 'requested' && state.staff.role === 'admin') action = form('schedule-overflow', row, '安排清运', '登记执行班组和交接要求');
    if (row.state === 'scheduled' && state.staff.role !== 'viewer') action = form('resolve-overflow', row, '确认清运结果', '记录清运完成时间和桶点现状');
    return `<tr><td><strong>${text(row.name)}</strong><br>${text(row.sample_day)} · ${labelSlot(row.slot)}</td><td>${row.overflow} / ${row.total} · ${pct(row.overflow / row.total)}</td>
      <td>${badge(status[row.state] || '达到清运线')}<br>${log([row.note, row.schedule_note, row.outcome])}</td><td>${action}</td></tr>`;
  }, 4, '暂无达到临时清运门槛的窗口。');
  return `<section class="pane">${paneHead('满溢清运调度台账', '在册地址的有效窗口至少记录 3 次满溢且达到 15%，方可申请清运。')}${table(['采样点位', '满溢记录', '工单进度', '业务操作'], rows)}</section>`;
}
