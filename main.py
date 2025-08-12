# coding: utf-8

from time import time
import logging
from contextlib import asynccontextmanager
from sys import stdout
import typing as t

from toml import load as load_toml
from fastapi import FastAPI, Depends
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import create_engine, SQLModel, Field, Session, select
from pydantic import BaseModel

from config import config as c
import utils as u

# region init

# init logger
l = logging.getLogger('uvicorn')  # get logger
logging.basicConfig(level=logging.DEBUG if c.debug else logging.INFO)  # log level
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


class Metadata(SQLModel, table=True):
    '''
    元数据
    '''
    id: int = Field(default=0, primary_key=True, index=True)
    status: int = Field(default=0)
    private_mode: bool = Field(default=False)
    last_updated: float = Field(default=time())


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as sess:
        meta = sess.exec(select(Metadata)).first()
        if not meta:
            l.debug('No metadata found, creating...')
            sess.add(Metadata())
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
    if c.log_file:
        l.info(f'Saving logs to {log_file_path}')
    # create db
    create_db_and_tables()
    yield
    l.info('Bye.')

app = FastAPI(lifespan=lifespan)

oauth2 = OAuth2PasswordBearer(tokenUrl='api/token')

# region routes


@app.get('/')
async def root():
    return {
        'hello': 'sleepy',
        'version': version,
        'version_str': version_str
    }


@app.get('/api/status')
async def get_status(sess: SessionDep):
    meta = sess.exec(select(Metadata)).first()
    if meta and not meta.private_mode:
        return {
            'success': True,
            'status': meta.status
        }
    else:
        return {
            'success': True,
            'status': None
        }


class SetStatusRequest(BaseModel):
    status: int


@app.post('/api/status')
async def set_status(sess: SessionDep, req: SetStatusRequest):
    meta = sess.exec(select(Metadata)).first()
    if meta:
        meta.status = req.status
        meta.last_updated = time()
        sess.commit()
    return {
        'success': True
    }


@app.get('/api/private_mode')
async def get_private_mode(sess: SessionDep):
    meta = sess.exec(select(Metadata)).first()
    if meta:
        return {
            'success': True,
            'private_mode': meta.private_mode
        }


class SetPrivateModeRequest(BaseModel):
    private_mode: bool


@app.post('/api/private_mode')
async def set_private_mode(sess: SessionDep, req: SetPrivateModeRequest):
    meta = sess.exec(select(Metadata)).first()
    if meta:
        meta.private_mode = req.private_mode
        meta.last_updated = time()
        sess.commit()
    return {
        'success': True
    }

# endregion routes
