import {canApprove, canEdit, pointById, state} from '../state.js';
import {badge, code, empty, formError, input, note, paneHead, rowSet, stat, text} from '../ui.js';

function profile(point) {
  if (!point) return empty('请先登记一个投放点。');
  const moves = point.pending_location ? `
    <div class="move-note"><strong>待核地址</strong><p>${text(point.pending_location)}</p><small>${text(point.migration_note)}</small></div>
    ${canApprove() ? `<form id="resolve-move" data-action="resolve" data-id="${point.id}">
      ${note('核验记录', '填写现场核验依据')}${formError}
      <div class="actions"><button name="confirm" value="confirm">确认迁移</button><button class="secondary" name="clear" value="clear">撤销待核</button></div>
    </form>` : '<p class="aside-note">由社区运营到场核验后处理。</p>'}` : canEdit() ? `
    <details><summary>登记地址迁移</summary><form id="propose-move" data-action="move" data-id="${point.id}">
      ${input('location', '拟迁入地址', 'minlength="4" maxlength="160"')}${note('迁移说明', '说明围挡、拆除或其他原因')}
      ${formError}<button>提交迁移待核</button>
    </form></details>` : '';
  return `${paneHead(point.name, point.sector)}<div class="detail-key">${code(point.code)} ${badge(point.pending_location ? 'migrating' : 'active')}</div>
    <dl class="facts"><div><dt>现行地址</dt><dd>${text(point.location)}</dd></div>
    <div><dt>地址版本</dt><dd>V${point.revision}</dd></div>
    <div><dt>现址基线窗口</dt><dd>${point.window_count} 条</dd></div>
    ${point.sample_from ? `<div><dt>新址采样起始</dt><dd>${text(point.sample_from)}</dd></div>` : ''}</dl>${moves}`;
}

export function pointsPage(params) {
  const points = state.points;
  const selected = pointById(params.get('point')) ?? points[0];
  const migrating = points.filter(point => point.pending_location).length;
  return `<div class="stats">${stat('登记点位', points.length, '社区投放网络')}${stat('涉及片区', new Set(points.map(p => p.sector)).size, '按点位档案统计')}${stat('迁移待核', migrating, migrating ? '待核期间暂停分群' : '当前地址均可用于采样')}</div>
    <div class="split"><section class="pane">${paneHead('在册点位', '选择点位查看现址、样本覆盖与迁移记录。')}
    <div class="table-wrap"><table><thead><tr><th>点位</th><th>所在片区</th><th>现址采样</th><th>地址状态</th></tr></thead><tbody>
    ${rowSet(points, point => `<tr ${selected?.id === point.id ? 'class="selected"' : ''}><td><a href="#points?point=${point.id}">${text(point.name)}</a><small>${code(point.code)}</small></td>
      <td>${text(point.sector)}</td><td class="mono">${point.window_count} 窗口</td><td>${badge(point.pending_location ? 'migrating' : 'active')}</td></tr>`, 4, '登记后可查看点位档案。')}
    </tbody></table></div>
    ${canApprove() ? `<details class="new-point"><summary>新增投放点</summary><form id="new-point" data-action="add-point">
      <div class="input-pair">${input('code', '点位编号', 'placeholder="QW-07" pattern="[A-Z][A-Z0-9\\-]{2,15}"')}${input('name', '点位名称', 'minlength="2" maxlength="64"')}</div>
      <div class="input-pair">${input('sector', '片区', 'minlength="2" maxlength="40"')}${input('location', '精确地址', 'minlength="4" maxlength="160"')}</div>
      ${formError}<button>保存点位</button></form></details>` : ''}</section>
    <aside class="pane dark-pane">${profile(selected)}</aside></div>`;
}
