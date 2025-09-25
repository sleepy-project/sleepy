# coding: utf-8

from time import time
import logging
from logging.handlers import RotatingFileHandler
from contextlib import asynccontextmanager
import typing as t
from datetime import timedelta, datetime, timezone
import asyncio
import uvicorn

from toml import load as load_toml
from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request, Body, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates
import jwt
from jwt.exceptions import InvalidTokenError
from passlib.context import CryptContext
from sqlmodel import create_engine, SQLModel, Session, select
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from sse_starlette import EventSourceResponse, ServerSentEvent
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html
from werkzeug.utils import safe_join

from config import config as c
import utils as u
import errors as e
import models as m

# region init

# init logger
loglvl = getattr(logging, c.log.level.upper(), logging.INFO)
l = logging.getLogger('uvicorn')  # get logger
logging.basicConfig(level=loglvl)  # log level
l.level = loglvl  # set logger level
root_logger = logging.getLogger()  # get root logger
root_logger.handlers.clear()  # clear default handlers
stream_handler = logging.StreamHandler()  # get stream handler
stream_handler.setFormatter(u.CustomFormatter())  # set stream formatter
# set file handler
if c.log.file:
    log_file_path = u.get_path(c.log.file)
    if c.log.rotating:
        file_handler = RotatingFileHandler(
            log_file_path, encoding='utf-8', errors='ignore', maxBytes=int(c.log.rotating_size * 1024), backupCount=c.log.rotating_count
        )
    else:
        file_handler = logging.FileHandler(log_file_path, encoding='utf-8', errors='ignore')
    file_handler.setFormatter(u.CustomFormatter())
    root_logger.addHandler(file_handler)
logging.getLogger('watchfiles').level = logging.WARNING  # set watchfiles logger level

# load metadata

with open(u.get_path('pyproject.toml'), 'r', encoding='utf-8') as f:
    file: dict = load_toml(f).get('tool', {}).get('sleepy', {})
    version: tuple[int, int, int] = file.get('version', (0, 0, 0))
    version_str: str = file.get('version-str', 'unknown')

# endregion init

# region models

# init db
engine = create_engine(c.database, connect_args={'check_same_thread': False})


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as sess:
        meta = sess.exec(select(m.Metadata)).first()
        if not meta:
            l.info('No metadata found, creating...')
            sess.add(m.Metadata())
            sess.commit()


def get_session():
    with Session(engine) as sess:
        yield sess


SessionDep = t.Annotated[Session, Depends(get_session)]

# endregion models

# region app-context


@asynccontextmanager
async def lifespan(app: FastAPI):
    '''
    - yield 往上 -> on_startup
    - yield 往下 -> on_exit
    '''
    # startup log
    l.info(f'{"=" * 15} Application Startup {"=" * 15}')
    l.info(f'Sleepy Backend version {version_str} ({".".join(str(i) for i in version)})')
    l.debug(f'Startup Config: {c}')
    if c.log.file:
        l.info(f'Saving logs to {log_file_path}')
    # create db
    create_db_and_tables()
    yield
    l.info('Bye.')

app = FastAPI(
    title='Sleepy Backend',
    version=f'{version_str} ({".".join(str(i) for i in version)})',
    lifespan=lifespan,
    docs_url=None,
    # redoc_url=None
)

templates=Jinja2Templates(directory="./")

# endregion app-context

# region custom-docs


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,  # type: ignore
        title=app.title + " - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/5.27.1/swagger-ui-bundle.js",
        swagger_css_url="https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/5.27.1/swagger-ui.css",
        swagger_favicon_url="https://ghsrc.wyf9.top/icons/sleepy_icon_nobg.png",
    )


@app.get(app.swagger_ui_oauth2_redirect_url, include_in_schema=False)  # type: ignore
async def swagger_ui_redirect():
    return get_swagger_ui_oauth2_redirect_html()

# 暂时用不到
# u need? pls wait for https://github.com/cdnjs/packages/issues/2049
# or use SLOW jsdelivr (at least it's slow for me)
# @app.get("/redoc", include_in_schema=False)
# async def redoc_html():
#     return get_redoc_html(
#         openapi_url=app.openapi_url,  # type: ignore
#         title=app.title + " - ReDoc",
#         redoc_js_url="https://unpkg.com/redoc@2/bundles/redoc.standalone.js",
#     )

# endregion custom-docs

# region auth

pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')
oauth2 = OAuth2PasswordBearer(tokenUrl='api/user/')
algorithm: str = 'HS256'
access_token_expires_minutes: int = 30


def pwd_verify(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def pwd_hash(password):
    return pwd_context.hash(password)


def auth_user(sess: SessionDep, username: str, password: str):
    auth = sess.exec(select(m.AuthData)).first()
    if not auth:
        raise e.APIUnsuccessful(404, 'No authentication data found')
    elif auth.username != username:
        return False
    elif not pwd_verify(password, auth.hashed_password):
        return False
    else:
        return True


def create_access_token(sess: SessionDep, data: dict, expires_delta: timedelta | None = None):
    auth = sess.exec(select(m.AuthData)).first()
    if not auth:
        raise e.APIUnsuccessful(404, 'No authentication data found')
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({'exp': expire})
    encoded_jwt = jwt.encode(to_encode, auth.secret_key, algorithm=algorithm)
    return encoded_jwt


credentials_exception = e.APIUnsuccessful(
    code=401,
    detail='Could not validate credentials',
    headers={'WWW-Authenticate': 'Bearer'},
)


async def current_user(sess: SessionDep, token: t.Annotated[str, Depends(oauth2)]):
    if not token:
        raise credentials_exception

    auth = sess.exec(select(m.AuthData)).first()
    if not auth:
        raise e.APIUnsuccessful(401, 'No authentication data found', headers={'WWW-Authenticate': 'Bearer'})

    try:
        payload = jwt.decode(token, auth.secret_key, algorithms=[algorithm])
        username = payload.get('sub')
        exp = payload.get('exp')
        if username != auth.username:
            raise credentials_exception
        if exp and datetime.fromtimestamp(exp, timezone.utc) < datetime.now(timezone.utc):
            raise credentials_exception
    except InvalidTokenError:
        raise credentials_exception
    return auth.username


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'

# ========== Theme ==========

# region theme

def render_template(filename: str, _dirname: str = 'templates', _theme: str | None = None, **context) -> str | None:
    '''
    渲染模板 (使用指定主题)

    :param filename: 文件名
    :param _dirname: `theme/[主题名]/<dirname>/<filename>`
    :param _theme: 主题 (未指定则从 `flask.g.theme` 读取)
    :param **context: 将传递给 `flask.render_template_string` 的模板上下文
    '''
    _theme = _theme or c.default_theme
    jinja_env=templates.env
    template_path = safe_join('theme', f'{_theme}/{_dirname}/{filename}')

    # 1. 返回主题
    #if not content is None:
    if u.is_file_exist(template_path):
        l.debug(f'[theme] return template {_dirname}/{filename} from theme {_theme}')
        return jinja_env.get_template(template_path).render(**context)

    # 2. 主题不存在 -> fallback 到默认
    #content = d.get_cached_text('theme', f'default/{_dirname}/{filename}')
    template_path = safe_join('theme', f'default/{_dirname}/{filename}')
    if u.is_file_exist(template_path):
        l.debug(f'[theme] return template {_dirname}/{filename} from default theme')
        return jinja_env.get_template(template_path).render(**context)

    # 3. 默认也不存在 -> 404
    l.warning(f'[theme] template {_dirname}/{filename} not found')
    return None

@app.get('/static/{filename:path}',name="static")  # keep name for url_for('static', filename=...)
def static_proxy(filename: str, request: Request):
    '''
    静态文件的主题处理 (重定向到 /static-themed/主题名/文件名)
    '''
    # 重定向
    return u.no_cache_response(RedirectResponse(f'/static-themed/{request.state.theme}/{filename}', 302))

@app.get('/static-themed/{theme}/{filename:path}')
def static_themed(theme: str, filename: str):
    '''
    经过主题分隔的静态文件 (便于 cdn / 浏览器 进行缓存)
    '''
    filepath = safe_join('theme', f'{theme}/static/{filename}')
    # 1. 返回主题
    if u.is_file_exist(filepath):
        resp = FileResponse(filepath)
        l.debug(f'[theme] return static file {filename} from theme {theme}')
        return resp
    # 2. 主题不存在 (而且不是默认) -> fallback 到默认
    elif theme != 'default':
        l.debug(f'[theme] static file {filename} not found in theme {theme}, fallback to default')
        return u.no_cache_response(RedirectResponse(f'/static-themed/default/{filename}', 302))
    # 3. 默认主题也没有 -> 404
    else:
        l.warning(f'[theme] static file {filename} not found')
        raise u.no_cache_response(HTTPException(status_code=404, detail=f'Static file {filename} in theme {theme} not found'))


@app.get('/default/{filename:path}')
def static_default_theme(filename: str):
    '''
    兼容在非默认主题中使用:
    ```
    import { ... } from "../../default/static/utils";
    ```
    '''
    if not filename.endswith('.js'):
        filename += '.js'
    return FileResponse(safe_join('theme/default', filename))

# endregion theme

# region error-handlers

@app.exception_handler(e.APIUnsuccessful)
async def api_unsuccessful_exception_handler(request: Request, exc: e.APIUnsuccessful):
    l.error(f'APIUnsuccessful: {exc}')
    return JSONResponse(status_code=exc.code, content={
        'code': exc.code,
        'message': exc.message,
        'detail': exc.detail
    }, headers=exc.headers)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    l.error(f'HTTPException: {exc}')
    return JSONResponse(status_code=exc.status_code, content={
        'code': exc.status_code,
        'message': e.APIUnsuccessful.codes.get(exc.status_code, f'HTTP Error {exc.status_code}'),
        'detail': exc.detail
    }, headers=exc.headers)

# endregion error-handlers

# region inject

@app.middleware('http')
async def read_themes(request: Request, call_next):
    # set context vars
    if 'sleepy-theme' in request.cookies:
        # got sleepy-theme
        request.state.theme = request.cookies['sleepy-theme']
    else:
        # use default theme
        request.state.theme = c.default_theme
    return await call_next(request)

@app.middleware('http')
async def redirect_api(request: Request, call_next):
    from models import redirect_map
    if request.url.path in redirect_map:
        new_path = redirect_map.get(request.url.path, '/')
        query = request.url.query
        if query:
            redirect_path = f'{new_path}?{query}'
        else:
            redirect_path = new_path
        return RedirectResponse(redirect_path, status_code=301)

    if request.query_params.get('theme'):
        theme = request.query_params.get('theme')
        url=request.url.remove_query_params('theme')
        l.debug(f'Redirecting to new url: {url}')
        resp = RedirectResponse(str(url), status_code=302)
        resp.set_cookie('sleepy-theme', theme, samesite='lax')
        return resp

    return await call_next(request)


# endregion inject

# region routes

# root


class RootResponse(BaseModel):
    hello: str = 'sleepy'
    version: tuple[int, int, int] = (6, 0, 0)
    version_str: str = '6.0.0'


@app.get('/', response_model=RootResponse)
async def root():
    return {
        'hello': 'sleepy',
        'version': version,
        'version_str': version_str
    }


class QueryResponse(BaseModel):
    time: float
    status: int
    devices: list[m.DeviceData]
    last_updated: float


@app.get('/api/query', response_model=QueryResponse)
async def query(sess: SessionDep):
    meta = sess.exec(select(m.Metadata)).first()
    if meta:
        devices = sess.exec(select(m.DeviceData)).all()
        return {
            'time': time(),
            'status': meta.status,
            'devices': devices,
            'last_updated': meta.last_updated
        }
    else:
        raise e.APIUnsuccessful(500, 'Cannot read metadata')


@app.get('/api/health', status_code=204)
async def health():
    return


@app.get('/favicon.ico', status_code=200, include_in_schema=False)
async def favicon():
    return RedirectResponse('https://ghsrc.wyf9.top/icons/sleepy_icon_nobg.png', 302)

# region routes-events


class ConnManager:
    def __init__(self):
        self._events: t.Set[asyncio.Queue] = set()
        self._public_ws: t.Set[WebSocket] = set()

    async def evt_connect(self):
        try:
            queue = asyncio.Queue()
            self._events.add(queue)
            l.info(f'EventStream connected, current connections: {len(self._events)}')
            await self.evt_broadcast('online-changed', {'online': len(self._events)})
            return queue
        except asyncio.QueueShutDown:
            raise e.APIUnsuccessful(500, 'Cannot connect to event stream')

    async def evt_disconnect(self, queue: asyncio.Queue):
        try:
            self._events.discard(queue)
            l.info(f'EventStream disconnected, current connections: {len(self._events)}')
        except asyncio.QueueShutDown:
            pass
        finally:
            l.debug(f'Broadcasting online count after disconnect: {len(self._events)}')
            await self.evt_broadcast('online-changed', {'online': len(self._events)})

    async def evt_broadcast(self, event: str, data: dict | None = None):
        l.debug(f'Broadcasting event {event} with data {data} to {len(self._events)} connections')

        if not self._events:
            l.debug(f'No active connections for broadcast event: {event}')
            return

        queues = list(self._events.copy())
        failed_queues = []

        for queue in queues:
            try:
                queue.put_nowait((event, data))
            except asyncio.QueueFull:
                l.debug('Queue full during put, removing from connections')
                failed_queues.append(queue)
            except asyncio.QueueShutDown:
                l.debug('Queue shutdown during put, removing from connections')
                failed_queues.append(queue)
            except Exception as e:
                l.debug(f'Error putting to queue: {e}, removing from connections')
                failed_queues.append(queue)

        for queue in failed_queues:
            self._events.discard(queue)

        if failed_queues:
            l.debug(f'Removed {len(failed_queues)} failed queues, new connection count: {len(self._events)}')
            await self.evt_broadcast('online-changed', {'online': len(self._events)})

    async def connect_pub(self, ws: WebSocket):
        self._public_ws.add(ws)

    async def disconnect_pub(self, ws: WebSocket):
        self._public_ws.discard(ws)

    async def broadcast_pub(self, data: dict):
        await asyncio.gather(*(asyncio.create_task(c.send_json(data)) for c in self._public_ws), return_exceptions=True)


manager = ConnManager()


async def event_stream(sess: SessionDep):
    queue = await manager.evt_connect()
    try:
        yield ServerSentEvent(
            id='0',
            event='connected',
            data=await query(sess)
        )
        id = 0
        event: str
        data: dict
        while True:
            id += 1
            event, data = await queue.get()
            yield ServerSentEvent(
                id=str(id),
                event=event,
                data=data
            )
    except (asyncio.CancelledError, asyncio.QueueShutDown) as e:
        l.debug(f'Event stream exception: {e}')
        pass
    finally:
        l.debug('Event stream closing, calling disconnect')
        await manager.evt_disconnect(queue)


@app.get('/api/events')
async def events(sess: SessionDep):
    return EventSourceResponse(event_stream(sess), media_type='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no'
    }, ping=c.ping_interval)

# endregion routes-events

# region routes-ws


@app.websocket('/api/devices/{device_id}')
async def websocket_device(ws: WebSocket, user: t.Annotated[str, Depends(current_user)]):
    try:
        await ws.accept()
        while True:
            data: dict = await ws.receive_json()

    except WebSocketDisconnect:
        pass


@app.websocket('/api/ws')
async def websocket_public(ws: WebSocket):
    try:
        await ws.accept()
        await manager.connect_pub(ws)
        while True:
            data = await ws.receive_json()
    except WebSocketDisconnect:
        await manager.disconnect_pub(ws)

# endregion routes-ws

# region routes-status

status_router = APIRouter(
    prefix='/api/status',
    tags=['status']
)


class GetStatusResponse(BaseModel):
    status: int | None = 0


@status_router.get('/', response_model=GetStatusResponse)
async def get_status(sess: SessionDep):
    meta = sess.exec(select(m.Metadata)).first()
    if meta:
        return {
            'status': meta.status
        }
    else:
        raise e.APIUnsuccessful(500, 'Cannot read metadata')


class SetStatusRequest(BaseModel):
    status: int


@status_router.post('/', status_code=204)
async def set_status(sess: SessionDep, req: SetStatusRequest, user: t.Annotated[str, Depends(current_user)]):
    meta = sess.exec(select(m.Metadata)).first()
    if not meta:
        raise e.APIUnsuccessful(500, 'Cannot update metadata')
    elif meta.status == req.status:
        return
    else:
        meta.status = req.status
        meta.last_updated = time()
        sess.commit()
        await manager.evt_broadcast('status_changed', {'status': req.status})
        return

# endregion routes-status

# region routes-device

devices_router = APIRouter(
    prefix='/api/devices',
    tags=['devices']
)


@devices_router.get('/{device_id}', response_model=m.DeviceData)
async def get_device(sess: SessionDep, device_id: str):
    device = sess.get(m.DeviceData, device_id)
    if device:
        return device
    else:
        raise e.APIUnsuccessful(404, 'Device not found')


class UpdateDeviceRequest(BaseModel):
    name: str | None = None
    status: str | None = None
    using: bool | None = None
    fields: dict | None = None


@devices_router.put('/{device_id}', status_code=204, name='Create or update a device')
async def update_device(sess: SessionDep, device_id: str, req: UpdateDeviceRequest, user: t.Annotated[str, Depends(current_user)]):
    device = sess.get(m.DeviceData, device_id)
    if device:
        updated = {}
        # exist -> update
        if req.name:
            device.name = req.name
            updated['name'] = req.name
        if req.status:
            device.status = req.status
            updated['status'] = req.status
        if req.using is not None:
            device.using = req.using
            updated['using'] = req.using
        if req.fields:
            device.fields = req.fields
            updated['fields'] = req.fields
        if updated:
            device.last_updated = time()
            meta = sess.exec(select(m.Metadata)).first()
            if meta:
                meta.last_updated = time()
            sess.commit()
            await manager.evt_broadcast('device_updated', {'id': device_id, 'updated_fields': updated})
        return
    else:
        # not exist -> create
        if not req.name:
            raise e.APIUnsuccessful(400, 'Device name is required')
        status = req.status or ''
        using = req.using if req.using is not None else False
        fields = req.fields or {}
        device = m.DeviceData(
            id=device_id,
            name=req.name,
            status=status,
            using=using,
            fields=fields
        )
        sess.add(device)
        meta = sess.exec(select(m.Metadata)).first()
        if meta:
            meta.last_updated = time()
        sess.commit()
        await manager.evt_broadcast('device_added', {'id': device_id, 'name': req.name, 'status': status, 'using': using, 'fields': fields})
        return Response(status_code=201)


@devices_router.delete('/{device_id}', status_code=204)
async def delete_device(sess: SessionDep, device_id: str, user: t.Annotated[str, Depends(current_user)]):
    device = sess.get(m.DeviceData, device_id)
    if device:
        sess.delete(device)
        meta = sess.exec(select(m.Metadata)).first()
        if meta:
            meta.last_updated = time()
        sess.commit()
        await manager.evt_broadcast('device_deleted', {'id': device_id})
    return


class GetDevicesResponse(BaseModel):
    devices: list[m.DeviceData]


@devices_router.get('/', response_model=GetDevicesResponse)
async def get_devices(sess: SessionDep):
    devices = sess.exec(select(m.DeviceData)).all()
    return {
        'devices': devices
    }


@devices_router.delete('/', status_code=204)
async def clear_devices(sess: SessionDep, user: t.Annotated[str, Depends(current_user)]):
    devices = sess.exec(select(m.DeviceData)).all()
    for d in devices:
        sess.delete(d)
    meta = sess.exec(select(m.Metadata)).first()
    if meta:
        meta.last_updated = time()
    sess.commit()
    await manager.evt_broadcast('devices_cleared')
    return

# endregion routes-device

# region routes-user

user_router = APIRouter(
    prefix='/api/user',
    tags=['user']
)


@user_router.post('/', response_model=LoginResponse, name='Register (if no user exists) and login')
async def login(
    sess: SessionDep,
    form_data: t.Annotated[OAuth2PasswordRequestForm, Depends()] = None,  # type: ignore
    json_data: t.Annotated[LoginRequest, Body()] = None  # type: ignore
):
    if form_data:
        username = form_data.username
        password = form_data.password
    elif json_data:
        username = json_data.username
        password = json_data.password
    else:
        raise HTTPException(
            status_code=400,
            detail='Either form data or JSON data is required'
        )

    user = auth_user(sess, username=username, password=password)
    if user:
        new_register = False
    else:
        # check if user exists or not
        auth = sess.exec(select(m.AuthData)).first()
        if auth:
            raise HTTPException(
                status_code=401,
                detail='Incorrect username or password'
            )
        else:
            # register & login
            new_register = True
            sess.add(m.AuthData(
                username=username,
                hashed_password=pwd_hash(password)
            ))
            sess.commit()
            user = auth_user(sess, username=username, password=password)

    access_token_expires = timedelta(minutes=access_token_expires_minutes)
    access_token = create_access_token(
        sess, data={'sub': username}, expires_delta=access_token_expires
    )

    return JSONResponse({
        'access_token': access_token,
        'token_type': 'bearer',
        'new_register': new_register
    }, 201 if new_register else 200)


class UpdateUserRequest(BaseModel):
    old_username: str | None = None
    old_password: str | None = None
    new_username: str
    new_password: str


@user_router.put('/', status_code=204, name='Create or update user')
async def update_user(sess: SessionDep, req: UpdateUserRequest):
    auth = sess.exec(select(m.AuthData)).first()
    if not auth:
        sess.add(m.AuthData(
            username=req.new_username,
            hashed_password=pwd_hash(req.new_password)
        ))
        sess.commit()
        return Response(status_code=201)
    elif auth.username != req.old_username:
        raise e.APIUnsuccessful(401, 'Incorrect username or password')
    elif not pwd_verify(req.old_password, auth.hashed_password):
        raise e.APIUnsuccessful(401, 'Incorrect username or password')
    else:
        auth.username = req.new_username
        auth.hashed_password = pwd_hash(req.new_password)
        sess.commit()
        return


class WhoamiResponse(BaseModel):
    username: str


@user_router.get('/', response_model=WhoamiResponse)
async def whoami(user: t.Annotated[str, Depends(current_user)] = None):  # type: ignore
    return {
        'username': user
    }


class GetRegisteredResponse(BaseModel):
    registered: bool


@user_router.get('/registered')
async def get_registered(sess: SessionDep):
    auth = sess.exec(select(m.AuthData)).first()
    return {
        'registered': bool(auth)
    }

# endregion auth

# endregion routes

# region main

app.include_router(devices_router)
app.include_router(user_router)
app.include_router(status_router)

if __name__ == '__main__':
    uvicorn.run(app, host=c.host, port=c.port)

# endregion main
