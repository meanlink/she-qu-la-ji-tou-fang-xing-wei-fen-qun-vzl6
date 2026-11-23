import {canApprove, canEdit, state} from '../state.js';
import {badge, code, empty, formError, goalLabel, input, labelSlot, note, options, paneHead, pct, text, today} from '../ui.js';

function reason(item) {
  switch (item.code) {
    case 'quality_pending': return `${item.point} 窗口 #${item.window_id} 的质量复核尚未完成。`;
    case 'sample_insufficient': return `${item.point} 匿名样本不足（${item.samples} / ${item.required_samples} 次，${item.windows} / ${item.required_windows} 窗口）。补采后重提。`;
    case 'migration_pending': return `${item.point} 迁移待核。请到点位档案核验地址。`;
    case 'too_few_points': return `只有 ${item.actual} 个点位，所选群数至少需要 ${item.required} 个点位。`;
    case 'source_changed': return '计算期间源数据已更新，正在按最新基线在本运行内重算。';
    case 'identical_profiles': return '不同的点位画像少于所选群数，请调整群数或补采。';
    case 'point_limit': return `单次分析最多 ${item.limit} 个点位。`;
    case 'calculation_failed': return '计算中断，数据未受影响，可点「重试」在本运行上继续。';
    default: return '计算失败，请重试。';
  }
}

const metric = (label, value) => `<div class="metric"><span>${label}</span><div><i style="--length:${pct(value)}"></i></div><strong>${pct(value, 0)}</strong></div>`;

function groupCards(result) {
  return `<div class="cohorts">${result.groups.map(group => `<article class="cohort"><div class="cohort-title">
      <span class="mono cohort-number">G${String(group.number).padStart(2, '0')}</span><h3>${text(group.label)}</h3>
      <span class="cohort-count">${group.members.length} 点 / ${group.samples} 次观察</span></div>
      <div class="metric-grid">${metric('分类正确', group.summary.accuracy)}${metric('晚间占比', group.summary.evening_share)}${metric('满溢发生', group.summary.overflow_rate)}</div>
      <ul class="members">${group.members.map(member => `<li><span>${code(member.code)} ${text(member.name)}</span><small>${member.action ? `${labelSlot(member.action.focus_slot)} · ${goalLabel(member.action.goal)}` : '常规跟踪'}</small></li>`).join('')}</ul>
    </article>`).join('')}</div>
    <details class="tree"><summary>查看层次合并路径</summary>
      <ol>${result.merges.map(merge => `<li>${code(merge.left.join(' + '))}<span>合并</span>${code(merge.right.join(' + '))}<span>距离 ${merge.distance.toFixed(3)}</span></li>`).join('')}</ol></details>`;
}

function progress(run) {
  const step = run.checkpoint?.steps ?? 0;
  const total = run.checkpoint?.total_steps ?? 0;
  const detail = total ? `层次合并 ${step} / ${total} 步，中断后将从最近一步继续` : '正在准备点位画像和距离表';
  return `<div class="run-progress" role="status"><span class="spinner" aria-hidden="true"></span>
    <span><strong>后台正在计算分群 #${run.id}</strong><br>${text(detail)}，采样录入不受影响，结果将自动刷新。</span></div>`;
}

function waiting(run) {
  return `<p class="empty" data-queued>分群已进入队列，等待后台 worker 领取计算，结果将自动刷新。</p>`;
}

export function groupsPage() {
  const {run, runs, windows} = state;
  const dates = windows.filter(w => !w.task_id && w.point_revision === w.current_revision).map(w => w.sample_day).sort();
  const through = run?.through_day ?? dates.at(-1) ?? today();
  const week = new Date(`${through}T00:00:00Z`);
  week.setUTCDate(week.getUTCDate() - 6);
  const from = run?.from_day ?? dates.find(day => day >= week.toISOString().slice(0, 10)) ?? through;
  const queue = canEdit() ? `<form id="request-run" data-action="run">
    ${input('from_day', '基线开始', `type="date" value="${from}" max="${today()}"`)}
    ${input('through_day', '基线结束', `type="date" value="${through}" max="${today()}"`)}
    <label>切分群数<select name="clusters">${options({2: '2 群', 3: '3 群', 4: '4 群'}, run?.requested_clusters ?? 3)}</select></label>
    ${formError}<button>请求分群</button>
  </form>` : '<p class="aside-note">巡查员和运营可提交分群。</p>';
  const canRetry = canEdit() && run && (run.state === 'paused' || run.state === 'failed');
  const retry = canRetry ? `<form data-action="retry-run" data-id="${run.id}">${formError}
    <button type="submit">重试本运行（不新增运行记录）</button></form>` : '';
  return `<div class="split group-layout"><section class="pane"><div class="run-head">${paneHead(run ? `分群 #${run.id}` : '分群工作台',
    run ? `${run.from_day} 至 ${run.through_day} · ${run.input_snapshot.points.length} 个在册点位 · 第 ${run.attempt} 轮` : '按点位汇总分类正确、晚间占比、满溢发生三项特征。')}${run ? badge(run.state) : ''}</div>
    ${!run ? empty('提交一段基线，查看群组画像和宣教建议。') : ''}
    ${run?.state === 'queued' ? waiting(run) : ''}
    ${run?.state === 'running' ? progress(run) : ''}
    ${run?.reasons.length ? `<ul class="blockers">${run.reasons.map(item => `<li>${text(reason(item))}</li>`).join('')}</ul>` : ''}
    ${retry}
    ${run?.result ? groupCards(run.result) : ''}
    ${run?.state === 'review' && canApprove() ? `<form id="confirm-run" data-action="confirm" data-id="${run.id}" data-attempt="${run.attempt}">
      ${note('运营确认记录', '填写需优先执行的点位或现场依据')}${formError}<button>确认并派发宣教</button></form>` : ''}
    ${run?.state === 'review' ? `<p class="aside-note">当前查看第 ${run.attempt} 轮计算结果；若源数据在查看期间更新，确认时会提示重新查看。</p>` : ''}
    ${run?.state === 'confirmed' ? `<p class="aside-note">已由 ${text(run.reviewed_by)} 确认。${text(run.review_note)}</p><a href="#tasks" class="quiet-link">查看已派发的宣教任务 →</a>` : ''}
    </section><aside class="pane entry">${paneHead('发起分群', '每点至少 30 次匿名观察和 2 个窗口。')}${queue}
      <div class="history">${paneHead('运行记录')}<ul>${runs.map(item => `<li><a href="#groups?run=${item.id}" class="${item.id === run?.id ? 'chosen' : ''}">
      <span>${code(`#${item.id}`)}<small>${text(item.from_day)} 至 ${text(item.through_day)} · 第 ${item.attempt} 轮</small></span>${badge(item.state)}</a></li>`).join('')}</ul>
      ${!runs.length ? '<p class="aside-note">尚未提交分群。</p>' : ''}</div>
    </aside></div>`;
}
