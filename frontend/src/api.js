import {workflowApi} from './workflow-api.js';

export const session = {
  get token() { return sessionStorage.getItem('qiwu-field-token'); },
  set token(value) {
    if (value) sessionStorage.setItem('qiwu-field-token', value);
    else sessionStorage.removeItem('qiwu-field-token');
  },
};

async function call(path, body) {
  const headers = new Headers();
  if (session.token) headers.set('Authorization', `Bearer ${session.token}`);
  if (body !== undefined) headers.set('Content-Type', 'application/json');
  const response = await fetch(`/api${path}`, {headers, method: body === undefined ? 'GET' : 'POST',
    body: body === undefined ? undefined : JSON.stringify(body)});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.detail ?? '请求未完成，请稍后重试。');
    error.status = response.status;
    throw error;
  }
  return data;
}

const qualityActions = {
  'challenge-window': id => `/quality/${id}`,
  'decide-window': id => `/quality/${id}/decision`,
  'request-overflow': id => `/overflow-dispatch/${id}`,
  'schedule-overflow': id => `/overflow-dispatch/${id}/schedule`,
  'resolve-overflow': id => `/overflow-dispatch/${id}/resolve`,
};

export const api = {
  ...workflowApi(call),
  quality: () => call('/quality'), overflowDispatch: () => call('/overflow-dispatch'),
  qualityAction: (action, id, data) => call(qualityActions[action](id), data),
  session: () => call('/session'), login: data => call('/session', data),
  points: () => call('/points'), addPoint: data => call('/points', data),
  move: (id, data) => call(`/points/${id}/relocation`, data),
  resolve: (id, action, data) => call(`/points/${id}/relocation/${action}`, data),
  windows: () => call('/windows'), addWindow: data => call('/windows', data),
  runs: () => call('/runs'), run: id => call(`/runs/${id}`), requestRun: data => call('/runs', data),
  retryRun: id => call(`/runs/${id}/retry`, {}),
  confirm: (id, data) => call(`/runs/${id}/confirm`, data),
  tasks: () => call('/tasks'), deliver: (id, data) => call(`/tasks/${id}/delivery`, data),
  review: (id, data) => call(`/tasks/${id}/review`, data),
};
