export const state = {staff: null, points: [], windows: [], runs: [], run: null, tasks: []};
export const pointById = id => state.points.find(point => point.id === Number(id));
export const taskById = id => state.tasks.find(task => task.id === Number(id));
export const canEdit = () => ['admin', 'analyst'].includes(state.staff.role);
export const canApprove = () => state.staff.role === 'admin';
export const roles = {analyst: '现场巡查', admin: '社区运营', viewer: '社区联络'};
export const slots = {morning: '早间', midday: '午间', evening: '晚间'};
export const labels = {queued: '计算排队', paused: '分群暂停', review: '待运营确认', confirmed: '已确认', failed: '计算失败',
  assigned: '待宣教', retesting: '复测中', improved: '已改善', followup: '需跟进', obsolete: '迁移作废',
  active: '正常使用', migrating: '迁移待确认'};
