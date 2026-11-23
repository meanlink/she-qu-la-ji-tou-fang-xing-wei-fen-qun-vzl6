import {canApprove, canEdit, state} from '../state.js';
import {code, empty, formError, goalLabel, input, labelSlot, note, options, paneHead, text, today} from '../ui.js';
import {conditionTypes} from './conditions.js';

const tactics = {accuracy: {replace_signs: '更新桶前标识', guided_sorting: '安排现场分拣示范'},
  overflow: {stagger_window: '增设错峰提示', alternate_point: '指引至备用点位'}};
const verdict = result => `${result.gain_pp.toFixed(1)} / ${result.target_pp.toFixed(0)} 个百分点`;
const taskLink = id => `<a href="#tasks?task=${id}">宣教 #${id} →</a>`;
const windowLinks = ids => ids.map(id => `<a href="#conditions?window=${id}">#${id}</a>`).join(' · ') || '—';

function issuePanel(task, candidates) {
  const evidence = task.evidence;
  const cohort = candidates.filter(member => member.run_id === task.run_id && member.cohort === task.cohort && member.goal === task.goal);
  const conditionOptions = Object.fromEntries(evidence.verified_conditions.map(c => [c.window_id, `${c.source === 'baseline' ? '基线' : '复测'} #${c.window_id} · ${conditionTypes[c.condition_type]}`]));
  return `${paneHead(`分群 #${task.run_id} / G${task.cohort}`, `${goalLabel(task.goal)} · ${cohort.length} 个待交接点位`)}
    <ul class="workflow-slots">${cohort.map(t => `<li><div><strong>${text(t.name)}</strong><small>${labelSlot(t.focus_slot)} · 改善 / 目标 ${verdict(t.result)}</small></div>${taskLink(t.id)}</li>`).join('')}</ul>
    <div class="workflow-record">${taskLink(task.id)}<p>同一时段基线 ${windowLinks(evidence.baseline_window_ids)}</p><p>已评估复测 ${windowLinks(evidence.retest_window_ids)}</p>
      ${evidence.verified_conditions.map(c => `<p>${conditionTypes[c.condition_type]} · ${text(c.note)}</p>`).join('')}</div>
    ${canApprove() ? `<form data-action="issue-handoff" data-id="${task.id}"><label>整改动作<select name="tactic">${options(tactics[task.goal])}</select></label>
      <label>引用现场条件<select name="condition_window_id"><option value="">无需引用</option>${options(conditionOptions)}</select></label>
      ${input('due_day', '整改期限', `type="date" min="${today()}" value="${today()}"`)}${note('班次与交接要求', '记录点位责任人和需要核实的现场变化')}${formError}<button>派发群组整改</button></form>` : ''}`;
}

function memberCard(handoff, member) {
  const retired = member.revision !== member.point_revision;
  const writable = !handoff.closed_at && !member.outcome && (retired ? canApprove() : canEdit() && !member.pending_location);
  return `<article class="workflow-member"><header><div><strong>${text(member.name)}</strong><small>${code(member.code)} · V${member.point_revision} · ${labelSlot(member.focus_slot)}</small></div>${taskLink(member.task_id)}</header>
    <p>复测改善 / 目标 ${verdict(member.result)}</p>
    ${member.outcome ? `<div class="workflow-record"><strong>${member.outcome === 'relocated' ? '旧址停止' : '已执行'}${member.event_day > handoff.due_day ? ' · 超期' : ''}</strong><p>${text(member.note)}</p><small>${member.event_day} · ${text(member.recorded_by)}</small></div>` : ''}
    ${!member.outcome && retired ? '<p class="aside-note">点位已迁移，待运营确认旧址停止。</p>' : ''}
    ${!member.outcome && member.pending_location ? '<p class="aside-note">迁移待核，暂停现场执行。</p>' : ''}
    ${writable ? `<form data-action="handoff-outcome" data-id="${handoff.id}" data-task="${member.task_id}"><input type="hidden" name="outcome" value="${retired ? 'relocated' : 'implemented'}">
      ${input('event_day', '现场结果日期', `type="date" min="${handoff.issued_day}" max="${today()}" value="${today()}"`)}
      ${note('现场证据', retired ? '记录迁移后停止旧址施工的依据' : '填写实际完成的现场变更、位置及时间')}${formError}<button>${retired ? '确认旧址停止' : '登记现场执行'}</button></form>` : ''}</article>`;
}

function handoffPanel(handoff) {
  const done = handoff.members.filter(member => member.outcome).length;
  return `${paneHead(tactics[handoff.goal][handoff.tactic], `分群 #${handoff.run_id} / G${handoff.cohort} · 交接 #${handoff.id}`)}
    <div class="workflow-metrics"><div><small>点位回执</small><strong>${done} / ${handoff.members.length}</strong></div><div><small>整改期限</small><strong>${code(handoff.due_day)}</strong></div></div>
    <div class="workflow-record"><p>${text(handoff.note)}</p><small>派发人 ${text(handoff.issued_by)} · ${handoff.issued_day}</small>
      ${handoff.condition_window_id ? `<p>引用 <a href="#conditions?window=${handoff.condition_window_id}">窗口 #${handoff.condition_window_id}</a> · ${conditionTypes[handoff.condition_type]} · ${text(handoff.condition_note)}</p>` : ''}</div>
    ${handoff.closed_at ? `<div class="workflow-record"><strong>已结案</strong><p>${text(handoff.close_note)}</p><small>复核人 ${text(handoff.closed_by)}</small></div>` : ''}
    ${handoff.members.map(member => memberCard(handoff, member)).join('')}
    ${!handoff.closed_at && canApprove() && done === handoff.members.length ? `<form data-action="close-handoff" data-id="${handoff.id}">${note('运营结案意见', '复核现场交付和后续责任')}${formError}<button>签署结案</button></form>` : ''}`;
}

export function handoffsPage(params) {
  const {candidates, handoffs} = state.handoffs;
  const task = candidates[0];
  const selected = params.has('task') && task ? null : handoffs[0];
  const detail = selected ? handoffPanel(selected) : task ? issuePanel(task, candidates) : empty('暂无需整改或已派发的群组交接。');
  return `<div class="split workflow-split"><section class="pane">${paneHead('群组整改队列', '同次分群、同一群组且目标相同的未达标点位可一起交接。')}
    <ul class="task-list workflow-list">${candidates.map(t => `<li><a href="#handoffs?task=${t.id}" class="${!selected && t.id === task?.id ? 'chosen' : ''}">
      <span><strong>${text(t.name)}</strong><small>分群 #${t.run_id} / G${t.cohort} · ${goalLabel(t.goal)}</small></span><span class="workflow-tag">待派发</span></a></li>`).join('')}
      ${handoffs.map(h => `<li><a href="#handoffs?handoff=${h.id}" class="${h.id === selected?.id ? 'chosen' : ''}">
      <span><strong>${tactics[h.goal][h.tactic]}</strong><small>分群 #${h.run_id} / G${h.cohort} · 交接 #${h.id} · ${h.members.length} 个点位</small></span><span class="workflow-tag">${h.closed_at ? '已结案' : h.due_day < today() ? '已超期' : '执行中'}</span></a></li>`).join('')}</ul>
    ${candidates.length || handoffs.length ? '' : empty('尚无未达标宣教任务。')}</section><aside class="pane entry">${detail}</aside></div>`;
}
