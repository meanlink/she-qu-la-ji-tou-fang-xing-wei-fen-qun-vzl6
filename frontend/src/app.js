import {api, session} from './api.js';
import {roles, state} from './state.js';
import {empty, formError, text} from './ui.js';
import {pointsPage} from './pages/points.js';
import {windowsPage} from './pages/windows.js';
import {groupsPage} from './pages/groups.js';
import {qualityPage, overflowPage} from './pages/quality.js';
import {tasksPage} from './pages/tasks.js';
import {conditionsPage} from './pages/conditions.js';
import {appointmentsPage} from './pages/appointments.js';
import {handoffsPage} from './pages/handoffs.js';

const app = document.querySelector('#app');
const notice = document.querySelector('#notice');
const pages = {
  points: {title: '点位档案', description: '维护社区投放点的使用地址，防止旧址样本与新址串用。', render: pointsPage},
  windows: {title: '投放采样', description: '按点位、日期和时段汇总匿名观察，供基线分析和宣教复测使用。', render: windowsPage},
  quality: {title: '采样复核', description: '处理现场计数争议，确定可用于分群的匿名采样。', render: qualityPage},
  overflow: {title: '满溢清运', description: '按有效采样安排清运，登记执行和现场结果。', render: overflowPage},
  groups: {title: '行为分群', description: '比较在册点位的投放表现，由社区运营复核群组和宣教建议。', render: groupsPage},
  conditions: {title: '现场条件', description: '核实伴随采样的现场事实，为复测和群组整改保留上下文。', render: conditionsPage, load: api.conditions},
  appointments: {title: '复测排班', description: '为宣教任务预留同址、同时段的两个观察班次。', render: appointmentsPage, load: api.appointments},
  handoffs: {title: '群组整改', description: '对未达标点位派发同群整改，逐点核实现场交付。', render: handoffsPage, load: api.handoffs},
  tasks: {title: '宣教跟踪', description: '记录现场宣教，用同一投放点、同一时段的观察核实变化。', render: tasksPage},
};
let generation = 0;
let poll;
let noticeTimer;

function current() {
  const [key, query] = location.hash.slice(1).split('?');
  return [Object.hasOwn(pages, key) ? key : 'points', new URLSearchParams(query)];
}

function announce(message) {
  notice.textContent = message;
  clearTimeout(noticeTimer);
  if (message) noticeTimer = setTimeout(() => { notice.textContent = ''; }, 4200);
}

const identity = `<span class="mark" aria-hidden="true"><i></i><i></i><i></i></span><div><strong>投放手册</strong><span>栖梧社区 · 环境运营</span></div>`;

function loginScreen() {
  app.innerHTML = `<main class="login"><section class="login-plate"><div class="brand">${identity}</div>
  <div class="login-heading"><p class="eyeline">栖梧社区环境工作站</p><h1>社区垃圾<br>投放行为分群</h1><p>基于点位匿名采样安排宣教，并在同一时段复测。</p></div>
  <div class="field-signs" aria-hidden="true"><div><i></i><b>早</b></div><div><i></i><b>午</b></div><div><i></i><b>晚</b></div></div>
  <p class="login-caption">采集 → 分群 → 宣教 → 复测</p></section>
  <section class="login-entry"><form id="login-form" data-action="login"><p class="eyeline">值班入口</p><h2>登录工作台</h2>
  <label>岗位账号<input name="username" autocomplete="username" required autofocus></label>
  <label>密码<input name="password" type="password" autocomplete="current-password" required></label>
  ${formError}<button>进入工作台</button></form></section></main>`;
}

function shell(key, body) {
  const page = pages[key];
  app.innerHTML = `<div class="shell"><aside class="rail"><div class="brand">${identity}</div>
    <nav aria-label="社区工作导航">${Object.entries(pages).map(([path, item]) => `<a href="#${path}" ${path === key ? 'aria-current="page"' : ''}><i aria-hidden="true"></i>${item.title}</a>`).join('')}</nav>
    <div class="profile"><span class="avatar" aria-hidden="true">${text(state.staff.display_name[0])}</span><span><strong>${text(state.staff.display_name.split(' · ')[0])}</strong><small>${roles[state.staff.role]}</small></span><button type="button" id="logout">退出</button></div>
    </aside><main class="workspace"><header class="heading"><div><p class="eyeline">栖梧社区 / 环境运营</p><h1>${page.title}</h1><p>${page.description}</p></div><span class="scope"><i></i>点位级匿名记录</span></header>
    <div class="view">${body}</div></main></div>`;
}

async function refresh() {
  const token = ++generation;
  clearTimeout(poll);
  if (!state.staff) { loginScreen(); return; }
  const [key, params] = current();
  try {
    let data;
    if (pages[key].load) data = {[key]: await pages[key].load(params)};
    if (key === 'points') data = {points: await api.points()};
    if (key === 'windows') {
      const [points, windows, tasks] = await Promise.all([api.points(), api.windows(), params.has('task') ? api.tasks() : []]);
      data = {points, windows, tasks};
    }
    if (key === 'groups') {
      const [runs, windows] = await Promise.all([api.runs(), api.windows()]);
      const runId = runs.find(run => run.id === Number(params.get('run')))?.id ?? runs[0]?.id;
      data = {runs, windows, run: runId ? await api.run(runId) : null};
    }
    if (key === 'tasks') data = {tasks: await api.tasks()};
    if (key === 'quality') data = {quality: await api.quality()};
    if (key === 'overflow') data = {overflowDispatch: await api.overflowDispatch()};
    if (token !== generation) return;
    Object.assign(state, data);
    shell(key, pages[key].render(params));
    if (key === 'groups' && (data.run?.state === 'queued' || data.run?.state === 'running')) {
      poll = setTimeout(refresh, 1200);
    }
  } catch (error) {
    if (token !== generation) return;
    if (error.status === 401) logout();
    else shell(key, `${empty(error.message)}<button type="button" id="retry">重新加载</button>`);
  }
}

function logout() {
  session.token = null;
  state.staff = null;
  refresh();
}

async function change(form, fields, submitter) {
  const id = Number(form.dataset.id);
  switch (form.dataset.action) {
    case 'login': {
      const result = await api.login(fields);
      session.token = result.access_token;
      state.staff = result.staff;
      return {};
    }
    case 'add-point': {
      const point = await api.addPoint(fields);
      return {location: `#points?point=${point.id}`, message: '投放点已登记'};
    }
    case 'move':
      await api.move(id, fields);
      return {message: '已提交迁移待核'};
    case 'resolve':
      await api.resolve(id, submitter.value, fields);
      return {message: submitter.value === 'confirm' ? '地址版本已更新' : '已撤销待核迁移'};
    case 'window':
      for (const key of ['point_id', 'total', 'correct', 'overflow']) fields[key] = Number(fields[key]);
      if (form.dataset.task) fields.task_id = Number(form.dataset.task);
      await api.addWindow(fields);
      return {message: fields.task_id ? '复测窗口已入账' : '基线窗口已入账'};
    case 'run': {
      const run = await api.requestRun({...fields, clusters: Number(fields.clusters)});
      return {location: `#groups?run=${run.id}`, message: run.state === 'paused' ? '分群暂停，请查看原因' : '已收到分群请求'};
    }
    case 'retry-run': {
      const run = await api.retryRun(id);
      return {location: `#groups?run=${id}`, message: run.state === 'paused' ? '仍有阻塞，请查看暂停原因' : '已在原运行上重新排队计算'};
    }
    case 'confirm': {
      const result = await api.confirm(id, {...fields, attempt: Number(form.dataset.attempt)});
      return {message: `运营已确认，派发 ${result.created_tasks} 项宣教任务`};
    }
    case 'deliver':
      await api.deliver(id, fields);
      return {message: '宣教已登记，可以开始复测'};
    case 'review-task':
      await api.review(id, fields);
      return {message: '复测结论已归档'};
    case 'challenge-window':
    case 'decide-window':
    case 'request-overflow':
    case 'schedule-overflow':
    case 'resolve-overflow':
      await api.qualityAction(form.dataset.action, id, fields);
      return {message: '台账已更新'};
    case 'report-condition':
    case 'decide-condition':
    case 'save-appointment':
    case 'issue-handoff':
    case 'handoff-outcome':
    case 'close-handoff':
      return api.workflowAction(form, fields);
    default: throw new Error('表单操作不可用');
  }
}

app.addEventListener('submit', async event => {
  const form = event.target;
  if (!form.dataset.action) return;
  event.preventDefault();
  const fields = Object.fromEntries(new FormData(form));
  const errorNode = form.querySelector('.form-error');
  const buttons = [...form.querySelectorAll('button')];
  errorNode.hidden = true;
  buttons.forEach(button => { button.disabled = true; });
  try {
    const result = await change(form, fields, event.submitter);
    if (result.message) announce(result.message);
    if (result.location && location.hash !== result.location) location.hash = result.location;
    else await refresh();
  } catch (error) {
    if (error.status === 401 && form.dataset.action !== 'login') logout();
    else {
      errorNode.textContent = error.message;
      errorNode.hidden = false;
      // A stale view was rejected: reload the run so the operator reads the newest generation before retrying.
      if (error.status === 409 && ['confirm', 'retry-run'].includes(form.dataset.action)) {
        announce(error.message);
        await refresh();
      }
    }
  } finally {
    buttons.forEach(button => { button.disabled = false; });
  }
});
app.addEventListener('click', event => {
  if (event.target.id === 'logout') logout();
  if (event.target.id === 'retry') refresh();
});
window.addEventListener('hashchange', refresh);
if (session.token) {
  try { state.staff = await api.session(); }
  catch { session.token = null; }
}
await refresh();
