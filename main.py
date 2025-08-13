# coding: utf-8

from time import time
import logging
from contextlib import asynccontextmanager
from sys import stdout
import typing as t

from toml import load as load_toml
from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
# from fastapi.security import OAuth2PasswordBearer # 一会会用
from sqlmodel import create_engine, SQLModel, Session, select
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from config import config as c
import utils as u
import errors as e
import models as m

# region init

# init logger
l = logging.getLogger('uvicorn')  # get logger
logging.basicConfig(level=logging.DEBUG if c.debug else logging.INFO)  # log level
l.level = logging.DEBUG if c.debug else logging.INFO  # set logger level
root_logger = logging.getLogger()  # get root logger
root_logger.handlers.clear()  # clear default handlers
stream_handler = logging.StreamHandler(stdout)  # get stream handler
stream_handler.setFormatter(u.CustomFormatter(colorful=c.colorful_log))  # set stream formatter
# set file handler
if c.log_file:
    log_file_path = u.get_path(c.log_file)
    file_handler = logging.FileHandler(log_file_path, encoding='utf-8', errors='ignore')
    file_handler.setFormatter(u.CustomFormatter(colorful=False))
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
    with Session(engine) as session:
        yield session


SessionDep = t.Annotated[Session, Depends(get_session)]

# endregion models


@asynccontextmanager
async def lifespan(app: FastAPI):
    '''
    - yield 往上 -> on_startup
    - yield 往下 -> on_exit
    '''
    # startup log
    l.info(f'{"="*15} Application Startup {"="*15}')
    l.info(f'Sleepy Backend version {version_str} ({".".join(str(i) for i in version)})')
    l.debug(f'Startup Config: {c}')
    if c.log_file:
        l.info(f'Saving logs to {log_file_path}')
    # create db
    create_db_and_tables()
    yield
    l.info('Bye.')

app = FastAPI(
    debug=c.debug,
    title='Sleepy-Backend',
    version=f'{version_str} ({".".join(str(i) for i in version)})',
    lifespan=lifespan
)

# oauth2 = OAuth2PasswordBearer(tokenUrl='api/token')

# region error-handlers


@app.exception_handler(e.APIUnsuccessful)
async def api_unsuccessful_exception_handler(request: Request, exc: e.APIUnsuccessful):
    l.error(f'APIUnsuccessful: {exc}')
    return JSONResponse(status_code=exc.code, content={
        'code': exc.code,
        'message': exc.message,
        'detail': exc.detail
    })


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    l.error(f'HTTPException: {exc}')
    return JSONResponse(status_code=exc.status_code, content={
        'code': exc.status_code,
        'message': e.APIUnsuccessful.codes.get(exc.status_code, f'HTTP Error {exc.status_code}'),
        'detail': exc.detail
    })

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

# query


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
async def set_status(sess: SessionDep, req: SetStatusRequest):
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
async def set_private_mode(sess: SessionDep, req: SetPrivateModeRequest):
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
async def update_device(sess: SessionDep, device_id: str, req: UpdateDeviceRequest, resp: Response):
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
        resp.status_code = 201
    meta = sess.exec(select(m.Metadata)).first()
    if meta:
        meta.last_updated = time()
    sess.commit()
    return


@app.delete('/api/devices/{device_id}', status_code=204)
async def delete_device(sess: SessionDep, device_id: str):
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
