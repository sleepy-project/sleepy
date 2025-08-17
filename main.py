# coding: utf-8

from time import time
import logging
from logging.handlers import RotatingFileHandler
from contextlib import asynccontextmanager
import typing as t
from datetime import timedelta, datetime, timezone
import asyncio

from toml import load as load_toml
from fastapi import FastAPI, Depends, HTTPException, Request, Body
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
    title='Sleepy-Backend',
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


from fastapi import Body


@app.post('/api/login', response_model=LoginResponse)
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


@app.post('/api/user', status_code=204)
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


@app.put('/api/user', status_code=204)
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


@app.get('/api/whoami')
async def whoami(sess: SessionDep, user: t.Annotated[str, Depends(current_user)]):
    return {
        'username': user
    }

# endregion auth
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
    private_mode: bool
    devices: list[m.DeviceData]
    last_updated: float


@app.get('/api/query', response_model=QueryResponse)
async def query(sess: SessionDep):
    meta = sess.exec(select(m.Metadata)).first()
    if meta:
        if meta.private_mode:
            devices = []
        else:
            devices = sess.exec(select(m.DeviceData)).all()
        return {
            'time': time(),
            'status': meta.status,
            'private_mode': meta.private_mode,
            'devices': devices,
            'last_updated': meta.last_updated
        }
    else:
        raise e.APIUnsuccessful(500, 'Cannot read metadata')

# region routes-events


class EventsManager:
    def __init__(self):
        self._conns: t.Set[asyncio.Queue] = set()

    async def connect(self):
        try:
            queue = asyncio.Queue()
            self._conns.add(queue)
            l.info(f'EventStream connected, current connections: {len(self._conns)}')
            await self.broadcast('online-changed', {'online': len(self._conns)})
            return queue
        except asyncio.QueueShutDown:
            raise e.APIUnsuccessful(500, 'Cannot connect to event stream')

    async def disconnect(self, queue: asyncio.Queue):
        try:
            self._conns.discard(queue)
            l.info(f'EventStream disconnected, current connections: {len(self._conns)}')
        except asyncio.QueueShutDown:
            pass
        finally:
            l.debug(f'Broadcasting online count after disconnect: {len(self._conns)}')
            await self.broadcast('online-changed', {'online': len(self._conns)})

    async def broadcast(self, event: str, data: dict):
        l.debug(f'Broadcasting event {event} with data {data} to {len(self._conns)} connections')

        if not self._conns:
            l.debug(f'No active connections for broadcast event: {event}')
            return

        queues = list(self._conns.copy())
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
            self._conns.discard(queue)

        if failed_queues:
            l.debug(f'Removed {len(failed_queues)} failed queues, new connection count: {len(self._conns)}')
            await self.broadcast('online-changed', {'online': len(self._conns)})


evt_manager = EventsManager()


async def event_stream(sess: SessionDep):
    queue = await evt_manager.connect()
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
        await evt_manager.disconnect(queue)


@app.get('/api/events')
async def events(sess: SessionDep):
    return EventSourceResponse(event_stream(sess), media_type='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no'
    })

# endregion routes-events


# region routes-status


class GetStatusResponse(BaseModel):
    status: int | None = 0


@app.get('/api/status', response_model=GetStatusResponse)
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


@app.post('/api/status', status_code=204)
async def set_status(sess: SessionDep, req: SetStatusRequest, user: t.Annotated[str, Depends(current_user)]):
    meta = sess.exec(select(m.Metadata)).first()
    if meta:
        meta.status = req.status
        meta.last_updated = time()
        sess.commit()
        return
    else:
        raise e.APIUnsuccessful(500, 'Cannot update metadata')

# private mode


class GetPrivateModeResponse(BaseModel):
    private_mode: bool


@app.get('/api/private_mode', response_model=GetPrivateModeResponse)
async def get_private_mode(sess: SessionDep):
    meta = sess.exec(select(m.Metadata)).first()
    if meta:
        return {
            'private_mode': meta.private_mode
        }
    else:
        raise e.APIUnsuccessful(500, 'Cannot read metadata')


class SetPrivateModeRequest(BaseModel):
    private_mode: bool


@app.post('/api/private_mode', status_code=204)
async def set_private_mode(sess: SessionDep, req: SetPrivateModeRequest, user: t.Annotated[str, Depends(current_user)]):
    meta = sess.exec(select(m.Metadata)).first()
    if meta:
        meta.private_mode = req.private_mode
        meta.last_updated = time()
        sess.commit()
        return
    else:
        raise e.APIUnsuccessful(500, 'Cannot update metadata')

# endregion routes-status

# region routes-device


@app.get('/api/devices/{device_id}', response_model=m.DeviceData)
async def get_device(sess: SessionDep, device_id: str):
    meta = sess.exec(select(m.Metadata)).first()
    if meta and meta.private_mode:
        raise e.APIUnsuccessful(403, 'Private mode is enabled')
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


@app.put('/api/devices/{device_id}', status_code=204)
async def update_device(sess: SessionDep, device_id: str, req: UpdateDeviceRequest, user: t.Annotated[str, Depends(current_user)]):
    device = sess.get(m.DeviceData, device_id)
    if device:
        # exist -> update
        if req.name:
            device.name = req.name
        if req.status:
            device.status = req.status
        if req.using is not None:
            device.using = req.using
        if req.fields:
            device.fields = req.fields
        device.last_updated = time()
    else:
        # not exist -> create
        if not req.name:
            raise e.APIUnsuccessful(400, 'Device name is required')
        device = m.DeviceData(
            id=device_id,
            name=req.name,
            status=req.status or '',
            using=req.using if req.using is not None else False,
            fields=req.fields or {}
        )
        sess.add(device)
    meta = sess.exec(select(m.Metadata)).first()
    if meta:
        meta.last_updated = time()
    sess.commit()
    return


@app.delete('/api/devices/{device_id}', status_code=204)
async def delete_device(sess: SessionDep, device_id: str, user: t.Annotated[str, Depends(current_user)]):
    device = sess.get(m.DeviceData, device_id)
    if device:
        sess.delete(device)
        meta = sess.exec(select(m.Metadata)).first()
        if meta:
            meta.last_updated = time()
        sess.commit()
        return
    else:
        raise e.APIUnsuccessful(404, 'Device not found')


class GetDevicesResponse(BaseModel):
    devices: list[m.DeviceData]


@app.get('/api/devices', response_model=GetDevicesResponse)
async def get_devices(sess: SessionDep):
    meta = sess.exec(select(m.Metadata)).first()
    if meta and meta.private_mode:
        raise e.APIUnsuccessful(403, 'Private mode is enabled')
    devices = sess.exec(select(m.DeviceData)).all()
    return {
        'devices': devices
    }

# endregion routes-device

# endregion routes
