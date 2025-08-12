# coding: utf-8

import logging
from contextlib import asynccontextmanager
from sys import stdout

from toml import load as load_toml
from fastapi import FastAPI

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    '''
    - yield 往上 -> on_startup
    - yield 往下 -> on_exit
    '''

    l.info(f'{"="*15} Application Startup {"="*15}')
    l.info(f'Sleepy Backend version {version_str} ({".".join(str(i) for i in version)})')
    if c.log_file:
        l.info(f'Saving logs to {log_file_path}')
    yield
    l.info('Bye.')

app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root():
    l.info('test')
    return {
        'hello': 'sleepy',
        'version': version,
        'version-str': version_str
    }
