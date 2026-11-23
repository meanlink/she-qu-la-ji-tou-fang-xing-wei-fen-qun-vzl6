import {labels, slots} from './state.js';

export const text = value => String(value ?? '').replace(/[&<>"']/g,
  char => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'})[char]);
export const pct = (value, digits = 1) => `${(Number(value) * 100).toFixed(digits)}%`;
export const today = () => new Intl.DateTimeFormat('sv-SE', {timeZone: 'Asia/Shanghai'}).format(new Date());
export const code = value => `<span class="code">${text(value)}</span>`;
export const badge = state => `<span class="badge ${text(state)}"><i></i>${text(labels[state] ?? state)}</span>`;
export const empty = message => `<div class="empty">${text(message)}</div>`;
export const rowSet = (rows, render, count, message) => rows.map(render).join('') ||
  `<tr><td colspan="${count}">${empty(message)}</td></tr>`;
export const options = (values, selected) => Object.entries(values).map(([key, value]) =>
  `<option value="${text(key)}" ${String(key) === String(selected) ? 'selected' : ''}>${text(value)}</option>`).join('');
export const labelSlot = slot => slots[slot] ?? '—';
export const input = (name, label, attributes = '') => `<label>${text(label)}<input name="${name}" ${attributes} required></label>`;
export const note = (label, hint) => `<label>${text(label)}<textarea name="note" rows="2" minlength="4" maxlength="240" placeholder="${text(hint)}" required></textarea></label>`;
export const formError = '<p class="form-error" role="alert" hidden></p>';
export const stat = (label, value, caption) => `<div class="stat"><span>${text(label)}</span><strong>${text(value)}</strong><small>${text(caption)}</small></div>`;
export const paneHead = (title, detail = '') => `<header class="pane-head"><h2>${text(title)}</h2>${detail ? `<p>${text(detail)}</p>` : ''}</header>`;
export const goalLabel = goal => goal === 'accuracy' ? '提高分类正确率' : '降低满溢发生率';
export const goalAction = goal => goal === 'accuracy' ? '在目标时段示范易混投品类并更新桶前标识' : '在目标时段提示错峰投放并张贴替代点位指引';
