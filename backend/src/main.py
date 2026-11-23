import logging
import os
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pymysql import OperationalError
from redis import Redis
from redis.exceptions import RedisError
from starlette.concurrency import run_in_threadpool

from scripts.seed_demo import seed
from src.contracts import Delivery, Login, Note, RegisterPoint, Relocation, Role, RunRequest, Window
from src.fieldwork import add_point, add_window, propose_move, resolve_move
from src.outreach import deliver, review_retest
from src import quality, workflow_schema
from src.workflow_routes import router as workflow_router
from src.runs import confirm_run, get_run, queue_run
from src.security import allow, login, signed_in
from src.storage import register

log = logging.getLogger('uvicorn.error')
redis = Redis.from_url(os.getenv('REDIS_URL', 'redis://127.0.0.1:6379/0'), socket_timeout=2)


@asynccontextmanager
async def lifespan(app):
    await run_in_threadpool(quality.initialize)
    await run_in_threadpool(workflow_schema.initialize)
    if os.getenv('SEED_DEMO', 'true').lower() == 'true':
        try:
            await run_in_threadpool(seed)
        except Exception:
            log.exception('Demo seed failed')
    yield


app = FastAPI(title='栖梧社区投放手册', lifespan=lifespan)
app.include_router(quality.router)
app.include_router(workflow_router)
field_staff = allow(Role.ANALYST, Role.ADMIN)
operations = allow(Role.ADMIN)


@app.middleware('http')
async def guard_login(request, call_next):
    if request.method == 'POST' and request.url.path == '/session':
        key = f'sorting:login:{request.client.host if request.client else "unknown"}'
        try:
            count = await run_in_threadpool(redis.eval, '''
                local n = redis.call('INCR', KEYS[1])
                if n == 1 then redis.call('EXPIRE', KEYS[1], 60) end
                return n
                ''', 1, key)
        except RedisError:
            return JSONResponse({'detail': '登录保护暂不可用'}, 503)
        if count > 24:
            return JSONResponse({'detail': '登录尝试过多，请稍后重试'}, 429, headers={'Retry-After': '60'})
    return await call_next(request)


@app.middleware('http')
async def trace_request(request, call_next):
    request_id = uuid4().hex
    response = await call_next(request)
    response.headers['X-Request-ID'] = request_id
    if request.url.path != '/health':
        log.info('request_id=%s %s %s %s', request_id, request.method, request.url.path, response.status_code)
        response.headers['Cache-Control'] = 'no-store'
    return response


@app.exception_handler(RequestValidationError)
async def invalid_form(request, error):
    fields = ['.'.join(str(key) for key in item['loc'][1:]) for item in error.errors()]
    messages = [item['msg'].removeprefix('Value error, ') for item in error.errors()]
    return JSONResponse({'detail': messages[0], 'fields': fields}, 422)


@app.exception_handler(OperationalError)
@app.exception_handler(RedisError)
async def unavailable(request, error):
    log.warning('Dependency unavailable: %s', type(error).__name__)
    return JSONResponse({'detail': '服务暂不可用，请稍后重试'}, 503)


@app.get('/health')
def health():
    with register() as ledger:
        ledger.one('SELECT id FROM field_register WHERE id=1')
    redis.ping()
    return {'status': 'up'}


@app.post('/session')
def create_session(form: Login):
    return login(form)


@app.get('/session')
def session(staff=Depends(signed_in)):
    return staff


@app.get('/points')
def points(staff=Depends(signed_in)):
    with register() as ledger:
        return ledger.rows('''SELECT p.*, (SELECT COUNT(*) FROM sampling_windows w
            WHERE w.point_id=p.id AND w.point_revision=p.revision AND w.task_id IS NULL) AS window_count
            FROM disposal_points p ORDER BY p.code''')


@app.post('/points', status_code=201)
def register_point(form: RegisterPoint, staff=Depends(operations)):
    return add_point(form, staff['username'])


@app.post('/points/{point_id}/relocation')
def relocate(point_id: int, form: Relocation, staff=Depends(field_staff)):
    return propose_move(point_id, form, staff['username'])


@app.post('/points/{point_id}/relocation/confirm')
def confirm_move(point_id: int, form: Note, staff=Depends(operations)):
    return resolve_move(point_id, form, staff['username'], True)


@app.post('/points/{point_id}/relocation/clear')
def clear_move(point_id: int, form: Note, staff=Depends(operations)):
    return resolve_move(point_id, form, staff['username'], False)


@app.get('/windows')
def windows(staff=Depends(signed_in)):
    with register() as ledger:
        return ledger.rows('''SELECT w.*,p.code,p.name AS point_name,p.revision AS current_revision
            FROM sampling_windows w JOIN disposal_points p ON p.id=w.point_id
            ORDER BY w.sample_day DESC,w.id DESC LIMIT 250''')


@app.post('/windows', status_code=201)
def record_window(form: Window, staff=Depends(field_staff)):
    return add_window(form, staff['username'])


@app.get('/runs')
def runs(staff=Depends(signed_in)):
    with register() as ledger:
        return ledger.rows('''SELECT id,from_day,through_day,state,requested_clusters,created_at
            FROM behavior_runs ORDER BY id DESC LIMIT 40''')


@app.get('/runs/{run_id}')
def run_detail(run_id: int, staff=Depends(signed_in)):
    with register() as ledger:
        return get_run(ledger, run_id)


@app.post('/runs', status_code=202)
def request_run(form: RunRequest, staff=Depends(field_staff)):
    return queue_run(form, staff['username'])


@app.post('/runs/{run_id}/confirm')
def publish(run_id: int, form: Note, staff=Depends(operations)):
    return confirm_run(run_id, form, staff['username'])


@app.get('/tasks')
def tasks(staff=Depends(signed_in)):
    with register() as ledger:
        return ledger.rows('''SELECT t.*,p.code,p.name AS point_name,r.through_day,p.pending_location,
            (SELECT COUNT(*) FROM sampling_windows w WHERE w.task_id=t.id) AS retest_windows,
            COALESCE((SELECT SUM(w.total) FROM sampling_windows w WHERE w.task_id=t.id),0) AS retest_total
            FROM outreach_tasks t JOIN disposal_points p ON p.id=t.point_id
            JOIN behavior_runs r ON r.id=t.run_id ORDER BY t.id DESC LIMIT 250''')


@app.post('/tasks/{task_id}/delivery')
def record_delivery(task_id: int, form: Delivery, staff=Depends(field_staff)):
    return deliver(task_id, form, staff['username'])


@app.post('/tasks/{task_id}/review')
def assess_outreach(task_id: int, form: Note, staff=Depends(operations)):
    return review_retest(task_id, form, staff['username'])


@app.get('/audit')
def audit(staff=Depends(operations)):
    with register() as ledger:
        return ledger.rows('SELECT * FROM field_audit ORDER BY id DESC LIMIT 100')
