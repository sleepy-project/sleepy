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
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import jwt
from jwt.exceptions import InvalidTokenError
from passlib.context import CryptContext
from sqlmodel import create_engine, SQLModel, Session, select
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from sse_starlette import EventSourceResponse, ServerSentEvent

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
    title='sleepy backend',
    version=f'{version_str} ({".".join(str(i) for i in version)})',
    lifespan=lifespan
)

# endregion app-context

# region auth

pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')
oauth2 = OAuth2PasswordBearer(tokenUrl='api/login')
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


async def current_user(sess: SessionDep, token: t.Annotated[str, Depends(oauth2)]):
    auth = sess.exec(select(m.AuthData)).first()
    if not auth:
        raise e.APIUnsuccessful(404, 'No authentication data found')
    credentials_exception = e.APIUnsuccessful(
        code=401,
        detail='Could not validate credentials',
        headers={'WWW-Authenticate': 'Bearer'},
    )
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


@devices_router.put('/{device_id}', status_code=204)
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
            await manager.evt_broadcast('device_updated', {'id': device_id, 'updated_fields': updated})
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
        await manager.evt_broadcast('device_added', {'id': device_id, 'name': req.name, 'status': status, 'using': using, 'fields': fields})
    meta = sess.exec(select(m.Metadata)).first()
    if meta:
        meta.last_updated = time()
    sess.commit()
    return


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

@user_router.post('/login', response_model=LoginResponse)
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
    if not user:
        raise HTTPException(
            status_code=401,
            detail='Incorrect username or password'
        )

    access_token_expires = timedelta(minutes=access_token_expires_minutes)
    access_token = create_access_token(
        sess, data={'sub': username}, expires_delta=access_token_expires
    )
    return {
        'access_token': access_token,
        'token_type': 'bearer'
    }


class CreateUserRequest(BaseModel):
    username: str
    password: str


@user_router.post('/', status_code=204)
async def create_user(sess: SessionDep, req: CreateUserRequest):
    auth = sess.exec(select(m.AuthData)).first()
    if auth:
        raise e.APIUnsuccessful(403, 'User already exists')
    else:
        sess.add(m.AuthData(
            username=req.username,
            hashed_password=pwd_hash(req.password)
        ))
        sess.commit()
        return


class UpdateUserRequest(BaseModel):
    old_username: str
    old_password: str
    new_username: str
    new_password: str


@user_router.put('/', status_code=204)
async def update_user(sess: SessionDep, req: UpdateUserRequest):
    auth = sess.exec(select(m.AuthData)).first()
    if not auth:
        raise e.APIUnsuccessful(404, 'No authentication data found')
    elif auth.username != req.old_username:
        raise e.APIUnsuccessful(401, 'Incorrect username or password')
    elif not pwd_verify(req.old_password, auth.hashed_password):
        raise e.APIUnsuccessful(401, 'Incorrect username or password')
    else:
        auth.username = req.new_username
        auth.hashed_password = pwd_hash(req.new_password)
        sess.commit()
        return


@user_router.get('/whoami')
async def whoami(sess: SessionDep, user: t.Annotated[str, Depends(current_user)]):
    return {
        'username': user
    }

# endregion auth

# region useless
@app.get('/api/health', status_code=200)
async def health():
    return {'status': 'ok'}

@app.get('/favicon.ico', status_code=200)
async def favicon():
    return

# endregion useless

# endregion routes

# region main

if __name__ == '__main__':
    app.include_router(devices_router)
    app.include_router(user_router)
    app.include_router(status_router)
    uvicorn.run(app, host=c.host, port=c.port)

# endregion main
