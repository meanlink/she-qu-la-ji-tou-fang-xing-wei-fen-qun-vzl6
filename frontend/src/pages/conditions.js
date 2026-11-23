import {canApprove, canEdit, state} from '../state.js';
import {code, empty, formError, labelSlot, note, options, paneHead, pct, stat, text} from '../ui.js';

export const conditionTypes = {rain: '降雨与遮蔽', access: '通道受阻', signage: '指示牌缺失或难辨', staffing: '值守变动'};
const statuses = {pending: '待签核', verified: '已签核', dismissed: '未采纳'};

function detail(window) {
  if (!window) return empty('暂无采样窗口。');
  return `${paneHead(`${window.code} · ${window.name}`, `${window.sample_day} · ${labelSlot(window.slot)} · 地址 V${window.point_revision}`)}
    <div class="workflow-metrics"><div><small>观察量</small><strong>${window.total}</strong></div><div><small>正确率</small><strong>${pct(window.correct / window.total)}</strong></div><div><small>满溢记录</small><strong>${window.overflow}</strong></div></div>
    <p class="workflow-source">${window.task_id ? `<a href="#tasks?task=${window.task_id}">宣教复测 #${window.task_id}</a>` : '基线观察'} · 窗口 ${code(`#${window.id}`)}</p>
    ${window.state ? `<div class="workflow-record"><strong>${conditionTypes[window.condition_type]} · ${statuses[window.state]}</strong>
      <p>${text(window.note)}</p><small>登记人 ${text(window.reported_by)}</small>
      ${window.decision_note ? `<p>${text(window.decision_note)}</p><small>签核人 ${text(window.decided_by)}</small>` : ''}</div>` : ''}
    ${window.state === 'pending' && canApprove() && window.reported_by !== state.staff.username ?
      `<form data-action="decide-condition" data-id="${window.id}"><label>签核结论<select name="decision">${options({verified: '核实记录', dismissed: '证据不足'})}</select></label>
      ${note('签核依据', '例如与桶站值班单时间吻合')}${formError}<button>保存签核</button></form>` : ''}
    ${!window.state && canEdit() && !window.pending_location && window.point_revision === window.revision && window.quality_state !== 'excluded' ?
      `<form data-action="report-condition" data-id="${window.id}"><label>现场条件<select name="condition_type">${options(conditionTypes)}</select></label>
      ${note('观察说明', '记录发生时间、位置和可核实事实')}${formError}<button>提交现场记录</button></form>` : ''}`;
}

export function conditionsPage() {
  const windows = state.conditions;
  const selected = windows[0];
  return `<div class="stats">${stat('观察窗口', windows.length, '当前列表')}${stat('待签核', windows.filter(w => w.state === 'pending').length, '由运营交叉核实')}${stat('已签核', windows.filter(w => w.state === 'verified').length, '可供匹配的整改任务引用')}</div>
    <div class="split workflow-split"><section class="pane">${paneHead('观察记录')}
    <ul class="task-list workflow-list">${windows.map(w => `<li><a href="#conditions?window=${w.id}" class="${selected.id === w.id ? 'chosen' : ''}">
      <span><strong>${text(w.name)}</strong><small>${code(w.code)} · ${w.sample_day} · ${labelSlot(w.slot)} · #${w.id}</small></span>
      <span class="workflow-tag">${statuses[w.state] ?? '可查看'}</span></a></li>`).join('')}</ul>${windows.length ? '' : empty('暂无观察记录。')}</section>
    <aside class="pane entry">${detail(selected)}</aside></div>`;
}
