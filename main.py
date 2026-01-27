# Copyright (C) 2026 sleepy-project contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See the GNU General Public License for more details.
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

# coding: utf-8

from time import time
from datetime import datetime, timezone, timedelta
from logging import getLogger as logging_getLogger, WARNING, Handler as LoggingHandler
from contextlib import asynccontextmanager
import typing as t
import asyncio
from contextvars import ContextVar
from sys import stderr
from traceback import format_exc
from uuid import uuid4 as uuid, UUID
from hashlib import sha256
import argparse
import inspect

from uvicorn import run
from loguru import logger as l
from toml import load as load_toml
from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request, Header, WebSocket, WebSocketDisconnect, status as hc, Security
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.encoders import jsonable_encoder
from sqlmodel import create_engine, SQLModel, Session, select
from pydantic import BaseModel, model_validator
from starlette.exceptions import HTTPException as StarletteHTTPException
from sse_starlette import EventSourceResponse, ServerSentEvent
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html
from fastapi.openapi.utils import get_openapi
from fastapi.security import APIKeyHeader
import bcrypt

from config import config as c
import errors as e
import models as m
import utils as u
from utils import cnen as ce
from plugin import plugin_manager

# region init

reqid: ContextVar[str] = ContextVar('sleepy_reqid', default='not-in-request')

# init logger
l.remove()


def log_format(record):
    reqid = record['extra'].get('reqid', 'fallback-logid')
    return '<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | <yellow>' + reqid + '</yellow> | <cyan>{name}</cyan>:<cyan>{line}</cyan> | <level>{message}</level>\n'


l.add(
    stderr,
    level=c.log.level,
    format=log_format,
    backtrace=True,
    diagnose=True
)
if c.log.file:
    l.add(
        c.log.file,
        level=c.log.file_level or c.log.level,
        format=log_format,
        colorize=False,
        rotation=c.log.rotation,
        retention=c.log.retention,
        enqueue=True
    )
l.configure(extra={'reqid': 'not-in-request'})


class InterceptHandler(LoggingHandler):
    def emit(self, record):
        logger_opt = l.opt(depth=6, exception=record.exc_info)
        logger_opt.log(record.levelname, record.getMessage())


logging_getLogger('uvicorn').handlers.clear()
logging_getLogger('uvicorn.access').handlers.clear()
logging_getLogger('uvicorn.error').handlers.clear()
logging_getLogger().handlers = [InterceptHandler()]
logging_getLogger().setLevel(c.log.level)
logging_getLogger('watchfiles').level = WARNING

# load metadata

with open(u.get_path('pyproject.toml'), 'r', encoding='utf-8') as f:
    pyproject_file: dict = load_toml(f).get('tool', {}).get('sleepy', {})
    version: tuple[int, int, int] = pyproject_file.get('version', (0, 0, 0))
    version_str: str = pyproject_file.get('version-str', 'unknown')
    version_full = f'{version_str} ({".".join(str(i) for i in version)})'

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


def perform_fresh_start():
    l.warning('Fresh start requested: dropping all tables before start')
    SQLModel.metadata.drop_all(engine)
    create_db_and_tables()


def parse_cli_args():
    parser = argparse.ArgumentParser(description='Sleepy Backend server runner')
    parser.add_argument('--fresh-start', action='store_true', help='Drop and recreate database before starting the server')
    return parser.parse_args()


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
    l.info(f'Sleepy Backend version {version_full}')
    l.debug(f'Startup Config: {c}')
    if c.log.file:
        l.info(f'Saving logs to {c.log.file}')
    # create db
    create_db_and_tables()

    l.info('Loading Plugins')
    try:
        plugin_manager.load_all_plugins()
        plugin_manager.setup_plugin_routes(app)
        loaded = plugin_manager.get_loaded_plugins()
        if loaded:
            l.info(f'Successfully loaded {len(loaded)} plugin(s): {", ".join(loaded)}')
        else:
            l.info('No plugins loaded')
    except Exception as ex:
        l.error(f'Error loading plugins: {ex}')

    yield

    l.info('Unloading Plugins')
    for plugin_name in list(plugin_manager.get_loaded_plugins()):
        try:
            plugin_manager.unload_plugin(plugin_name)
        except Exception as ex:
            l.error(f'Error unloading plugin {plugin_name}: {ex}')

app = FastAPI(
    title='Sleepy Backend',
    version=f'{version_str} ({".".join(str(i) for i in version)})',
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None
)


@app.middleware('http')
async def log_requests(request: Request, call_next: t.Callable):
    request_id = str(uuid())
    token = reqid.set(request_id)
    with l.contextualize(reqid=request_id):
        if request.client:
            ip = f'[{request.client.host}]' if ':' in request.client.host else request.client.host
            port = request.client.port
        else:
            ip = 'unknown-ip'
            port = 0
        l.info(f'Incoming request: {ip}:{port} - {request.method} {request.url.path}')
        resp: Response
        p = u.perf_counter()
        try:
            resp = await call_next(request)
            l.info(f'Outgoing response: {resp.status_code} ({p()}ms)')
        except Exception as e:
            l.error(f'Server error: {e} ({p()}ms)\n{format_exc()}')
            resp = Response(f'Internal Server Error ({request_id})', 500)
        resp.headers['X-Sleepy-Version'] = version_full
        resp.headers['X-Sleepy-Request-Id'] = request_id
        reqid.reset(token)
        return resp


@app.middleware('http')
async def plugin_response_middleware(request: Request, call_next: t.Callable):
    response = await call_next(request)

    if plugin_manager.get_loaded_plugins():
        response = plugin_manager.apply_response_modifiers(
            request,
            response,
            request.url.path
        )

    return response

# endregion app-context

# region custom-docs


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,  # type: ignore
        title=f"{app.title} - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        # or https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/5.27.1/swagger-ui-bundle.js
        swagger_js_url="https://s4.zstatic.net/ajax/libs/swagger-ui/5.27.1/swagger-ui-bundle.js",
        # or https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/5.27.1/swagger-ui.css
        swagger_css_url="https://s4.zstatic.net/ajax/libs/swagger-ui/5.27.1/swagger-ui.css",
        swagger_favicon_url="https://ghsrc.wyf9.top/icons/sleepy_icon_nobg.png",
    )


@app.get(app.swagger_ui_oauth2_redirect_url, include_in_schema=False)  # type: ignore
async def swagger_ui_redirect():
    return get_swagger_ui_oauth2_redirect_html()


@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    return get_redoc_html(
        openapi_url=app.openapi_url or '/openapi.json',
        title=f'{app.title} - ReDoc',
        # or https://unpkg.com/redoc@2/bundles/redoc.standalone.jsstandalone.js
        redoc_js_url="https://cdn.jsdmirror.com/npm/redoc@2/bundles/redoc.standalone.js",
        redoc_favicon_url="https://ghsrc.wyf9.top/icons/sleepy_icon_nobg.png"
    )


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    components = openapi_schema.setdefault('components', {})
    security_schemes = components.setdefault('securitySchemes', {})
    security_schemes.setdefault('SleepyToken', {
        'type': 'apiKey',
        'in': 'header',
        'name': 'X-Sleepy-Token',
        'description': ce('在 `X-Sleepy-Token` 中提供 token', '`X-Sleepy-Token` header for sending the raw token')
    })
    for path in openapi_schema.get('paths', {}).values():
        for operation in path.values():
            if 'responses' not in operation:
                operation['responses'] = {}

            for status_code, response in operation['responses'].items():
                if isinstance(response, str):
                    operation['responses'][status_code] = {'description': response}

                if 'headers' not in operation['responses'][status_code]:
                    operation['responses'][status_code]['headers'] = {}

                operation['responses'][status_code]['headers'].setdefault(
                    'X-Sleepy-Version', {
                        'description': ce('Sleepy 版本', 'Sleepy version'),
                        'schema': {'type': 'string'}
                    }
                )
                operation['responses'][status_code]['headers'].setdefault(
                    'X-Sleepy-Request-Id', {
                        'description': ce('Sleepy 请求 ID', 'Sleepy Request ID'),
                        'schema': {'type': 'string'}
                    }
                )

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

# endregion custom-docs

# region error-handlers


@app.exception_handler(e.APIUnsuccessful)
async def api_unsuccessful_exception_handler(request: Request, exc: e.APIUnsuccessful):
    log_fn = l.error if exc.code >= 500 else l.info
    log_fn(f'APIUnsuccessful: {exc}')
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

# region auth

AUTH_ROOT_USERNAME = '__sleepy__'
AUTH_ACCESS_PREFIX = 'auth_access'
AUTH_REFRESH_PREFIX = 'auth_refresh'
AUTH_ALLOWED_TYPES: tuple[str, ...] = ('web', 'dev')
DEV_LOGIN_ALLOWED = bool(getattr(c, 'dev', False) or getattr(c, 'env', {}).get('dev', False))
sleepy_token_header = APIKeyHeader(name='X-Sleepy-Token', scheme_name='SleepyToken', auto_error=False)

auth_router = APIRouter(
    prefix='/api/auth',
    tags=['auth']
)


class InitRequest(BaseModel):
    password: str
    hashed: bool = True


class InitResponse(BaseModel):
    initialized: bool = True


class AuthLoginRequest(BaseModel):
    password: str
    type: t.Literal['web', 'dev'] = 'web'
    device_uid: str | None = None
    hashed: bool = True

    @model_validator(mode='after')
    def _ensure_dev_allowed(self):
        if self.type == 'dev' and not DEV_LOGIN_ALLOWED:
            raise ValueError('Dev login disabled in this environment')
        return self


class AuthRefreshRequest(BaseModel):
    token: UUID
    refresh_token: UUID


class AuthTokensResponse(BaseModel):
    token: UUID
    refresh_token: UUID
    expires_at: float | None = None
    type: str | None = None


class AuthTokenCheckResponse(BaseModel):
    expires_at: float | None = None
    type: str | None = None


def _hash_sha256(value: str) -> str:
    return sha256(value.encode('utf-8', errors='xmlcharrefreplace')).hexdigest()


def _normalize_password(password: str, hashed: bool) -> str:
    return password if hashed else _hash_sha256(password)


def _get_auth_secret(sess: Session) -> m.AuthSecret | None:
    return sess.exec(select(m.AuthSecret)).first()


def _is_auth_initialized(sess: Session) -> bool:
    return _get_auth_secret(sess) is not None


def _ensure_auth_initialized(sess: Session) -> m.AuthSecret:
    secret = _get_auth_secret(sess)
    if not secret:
        raise e.APIUnsuccessful(hc.HTTP_403_FORBIDDEN, 'Auth not initialized')
    return secret


def _token_parts(token_type: str) -> tuple[str, str | None, str | None]:
    parts = token_type.split(':') if token_type else []
    if not parts:
        return '', None, None
    base = parts[0]
    if len(parts) == 1:
        return base, None, None
    if len(parts) == 2:
        return base, None, parts[1]
    subtype = ':'.join(parts[1:-1]) or None
    device_hash = parts[-1]
    return base, subtype, device_hash


def _base_token_type(token_type: str) -> str:
    base, _, _ = _token_parts(token_type)
    return base


def _token_device_hash(token_type: str) -> str | None:
    _, _, device_hash = _token_parts(token_type)
    return device_hash


def _token_login_type(token_type: str) -> str | None:
    _, subtype, _ = _token_parts(token_type)
    return subtype


def _device_hash(device_uid: str) -> str:
    return sha256(device_uid.encode('utf-8', errors='xmlcharrefreplace')).hexdigest()


def create_token(
    sess: Session,
    prefix: str,
    device_hash: str,
    expire_delta: timedelta | None,
    *,
    login_type: str | None = None
):
    """
    Exported token creation function for plugins
    """
    token_value = str(uuid())
    expire_ts: float | None = None
    if expire_delta:
        expire_ts = (datetime.now(timezone.utc) + expire_delta).timestamp()
    fragments = [prefix]
    if login_type:
        fragments.append(login_type)
    fragments.append(device_hash)
    token_type = ':'.join(fragments)
    sess.add(m.TokenData(
        type=token_type,
        token=token_value,
        expire=expire_ts or 0.0
    ))
    l.info(f'Generated new {token_type} token {sha256(token_value.encode("utf-8"), usedforsecurity=False).hexdigest()} (sha256), expires: {expire_ts or 0.0}')
    return token_value, expire_ts


def _clear_device_tokens(sess: Session, device_hash: str):
    """
    Internal use for clearing web/dev sessions. 
    (Device plugins should implement their own clearing logic or reuse this carefully)
    """
    def _tokens_with_prefix(prefix: str) -> list[m.TokenData]:
        return list(sess.exec(select(m.TokenData).where(m.TokenData.type.startswith(f'{prefix}:'))).all())

    candidates = _tokens_with_prefix(AUTH_ACCESS_PREFIX) + _tokens_with_prefix(AUTH_REFRESH_PREFIX)
    for tk in candidates:
        if _token_device_hash(tk.type) == device_hash:
            sess.delete(tk)


def _issue_full_session(sess: Session, device_uid: str | None, login_type: str | None = None) -> AuthTokensResponse:
    resolved_login_type = login_type or 'web'
    if resolved_login_type == 'dev' and not DEV_LOGIN_ALLOWED:
        raise e.APIUnsuccessful(hc.HTTP_403_FORBIDDEN, 'Dev token issuance disabled')
    identifier = device_uid or resolved_login_type
    device_hash = _device_hash(identifier)
    
    # Clears previous tokens for this web/dev session
    _clear_device_tokens(sess, device_hash)
    
    access_token, expires_at = create_token(
        sess,
        AUTH_ACCESS_PREFIX,
        device_hash,
        timedelta(minutes=c.auth_access_token_expires_minutes),
        login_type=resolved_login_type
    )
    refresh_token, _ = create_token(
        sess,
        AUTH_REFRESH_PREFIX,
        device_hash,
        timedelta(days=c.auth_refresh_token_expires_days),
        login_type=resolved_login_type
    )
    sess.commit()
    return AuthTokensResponse(
        token=UUID(access_token),
        refresh_token=UUID(refresh_token),
        expires_at=expires_at,
        type=resolved_login_type
    )


def _issue_access_from_refresh(sess: Session, refresh_record: m.TokenData) -> AuthTokensResponse:
    _, login_type, device_hash = _token_parts(refresh_record.type)
    if not device_hash:
        raise e.APIUnsuccessful(hc.HTTP_401_UNAUTHORIZED, 'Malformed refresh token')
    access_token, expires_at = create_token(
        sess,
        AUTH_ACCESS_PREFIX,
        device_hash,
        timedelta(minutes=c.auth_access_token_expires_minutes),
        login_type=login_type
    )
    refresh_record.last_active = datetime.now(timezone.utc).timestamp()
    sess.add(refresh_record)
    sess.commit()
    return AuthTokensResponse(
        token=UUID(access_token),
        refresh_token=UUID(refresh_record.token),
        expires_at=expires_at,
        type=login_type
    )

@app.post('/api/init', response_model=InitResponse, name='Initialize auth secret')
async def init_auth(sess: SessionDep, req: InitRequest):
    if _is_auth_initialized(sess):
        raise e.APIUnsuccessful(hc.HTTP_409_CONFLICT, 'Auth already initialized')
    normalized = _normalize_password(req.password, req.hashed)
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(normalized.encode('utf-8', errors='xmlcharrefreplace'), salt)
    sess.add(m.AuthSecret(
        username=AUTH_ROOT_USERNAME,
        password=hashed_password,
        salt=salt
    ))
    sess.commit()
    return {'initialized': True}

@app.get('/api/init', response_model=InitResponse, name='Check auth initialization')
async def check_init_auth(sess: SessionDep):
    """查询是否已初始化，供前端自动跳转使用"""
    return {'initialized': _is_auth_initialized(sess)}

@auth_router.post('/login', response_model=AuthTokensResponse, name='Login and issue auth tokens')
async def auth_login(sess: SessionDep, req: AuthLoginRequest):
    secret = _ensure_auth_initialized(sess)
    normalized = _normalize_password(req.password, req.hashed)
    if not bcrypt.checkpw(normalized.encode('utf-8', errors='xmlcharrefreplace'), secret.password):
        l.warning('Auth password mismatch during login request')
        raise e.APIUnsuccessful(hc.HTTP_401_UNAUTHORIZED, 'Incorrect password')
    return _issue_full_session(sess, req.device_uid, req.type)


@auth_router.post('/refresh', response_model=AuthTokensResponse, name='Refresh auth token')
async def auth_refresh(sess: SessionDep, req: AuthRefreshRequest):
    _ensure_auth_initialized(sess)
    now_ts = datetime.now(timezone.utc).timestamp()
    access_token = sess.get(m.TokenData, str(req.token))
    refresh_token = sess.get(m.TokenData, str(req.refresh_token))

    if not access_token or _base_token_type(access_token.type) != AUTH_ACCESS_PREFIX:
        raise e.APIUnsuccessful(hc.HTTP_401_UNAUTHORIZED, 'Invalid token')
    if not refresh_token or _base_token_type(refresh_token.type) != AUTH_REFRESH_PREFIX:
        raise e.APIUnsuccessful(hc.HTTP_401_UNAUTHORIZED, 'Invalid refresh token')

    refresh_hash = _token_device_hash(refresh_token.type)
    access_hash = _token_device_hash(access_token.type)
    if not refresh_hash or refresh_hash != access_hash:
        raise e.APIUnsuccessful(hc.HTTP_401_UNAUTHORIZED, 'Token pair mismatch')

    if refresh_token.expire and refresh_token.expire > 0 and refresh_token.expire < now_ts:
        sess.delete(refresh_token)
        sess.commit()
        raise e.APIUnsuccessful(hc.HTTP_401_UNAUTHORIZED, 'Refresh token expired')

    if access_token.expire and access_token.expire > 0 and access_token.expire < now_ts:
        sess.delete(access_token)
        sess.commit()
        raise e.APIUnsuccessful(hc.HTTP_401_UNAUTHORIZED, 'Token expired')

    sess.delete(access_token)
    return _issue_access_from_refresh(sess, refresh_token)


class TokenDep:
    """
    Base Token Dependency.
    Validates token existence, expiration, and allowed login types (e.g., 'web', 'dev').
    
    Refactor Note: Device-specific hash validation has been removed from here.
    Plugins needing specific validations (like matching Device ID) should wrap this 
    or implement additional checks using the returned TokenData.
    """
    def __init__(
        self,
        allowed_token_types: tuple[str, ...] | None = None,
        *,
        throw: bool = True,
        allowed_login_types: tuple[str, ...] | None = None
    ):
        self.allowed_token_types = allowed_token_types or (AUTH_ACCESS_PREFIX,)
        if allowed_login_types and not DEV_LOGIN_ALLOWED:
            self.allowed_login_types = tuple(t for t in allowed_login_types if t != 'dev') or None
        else:
            self.allowed_login_types = allowed_login_types
        self.throw = throw

    def __call__(
        self,
        sess: SessionDep,
        token_value: t.Annotated[str | None, Security(sleepy_token_header)] = None,
        authorization: t.Annotated[str | None, Header(include_in_schema=False)] = None,
    ) -> m.TokenData | None:
        if token_value:
            l.debug('Got token from X-Sleepy-Token security header')
        elif authorization and authorization.startswith('Bearer '):
            token_value = authorization[7:]
            l.debug('Got token from Authorization header')
        else:
            l.debug('No token provided in headers')

        if not token_value:
            if self.throw:
                raise e.APIUnsuccessful(hc.HTTP_401_UNAUTHORIZED, 'Missing token')
            return None

        info: m.TokenData | None = sess.get(m.TokenData, token_value)
        now_ts = datetime.now(timezone.utc).timestamp()
        if info:
            if info.expire and info.expire > 0 and info.expire < now_ts:
                sess.delete(info)
                sess.commit()
                info = None
            elif _base_token_type(info.type) in self.allowed_token_types:
                login_type = _token_login_type(info.type)
                if self.allowed_login_types and login_type not in self.allowed_login_types:
                    l.debug(f'Token login type {login_type} is not allowed in {self.allowed_login_types}')
                else:
                    info.last_active = now_ts
                    sess.add(info)
                    sess.commit()
                    return info
            else:
                l.debug(f'Token type {info.type} is not allowed in {self.allowed_token_types}')
        else:
            l.debug('Token not found in database')

        if self.throw:
            raise e.APIUnsuccessful(hc.HTTP_401_UNAUTHORIZED, 'Invalid token')
        return None


@auth_router.get('/check', response_model=AuthTokenCheckResponse, name='Check token validity')
async def auth_check(
    token: m.TokenData | None = Security(TokenDep(allowed_token_types=(AUTH_ACCESS_PREFIX,), throw=False))
):
    if not token:
        raise e.APIUnsuccessful(hc.HTTP_403_FORBIDDEN, 'Invalid token')
    expires = token.expire if token.expire and token.expire > 0 else None
    token_type = _token_login_type(token.type)
    return {
        'expires_at': expires,
        'type': token_type
    }

# endregion auth

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
        raise e.APIUnsuccessful(hc.HTTP_500_INTERNAL_SERVER_ERROR, 'Cannot read metadata')


@app.get('/api/health', status_code=hc.HTTP_204_NO_CONTENT)
async def health():
    return


@app.get('/favicon.ico', status_code=hc.HTTP_200_OK, include_in_schema=False)
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
            raise e.APIUnsuccessful(hc.HTTP_500_INTERNAL_SERVER_ERROR, 'Cannot connect to event stream')

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
            await self.broadcast_pub({'event': event, 'data': data})
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
        await self.broadcast_pub({'event': event, 'data': data})

    async def connect_pub(self, ws: WebSocket):
        self._public_ws.add(ws)

    async def disconnect_pub(self, ws: WebSocket):
        self._public_ws.discard(ws)

    async def broadcast_pub(self, data: dict):
        if not self._public_ws:
            return
        stale: list[WebSocket] = []
        for conn in list(self._public_ws):
            try:
                await conn.send_json(data)
            except Exception as exc:
                l.debug(f'Failed to send WS broadcast: {exc}')
                stale.append(conn)
        for conn in stale:
            self._public_ws.discard(conn)


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

@app.websocket('/api/ws')
async def websocket_public(ws: WebSocket):
    await ws.accept()
    await manager.connect_pub(ws)
    stop_event = asyncio.Event()

    async def push_periodic_snapshot():
        interval = getattr(c, 'ws_refresh_interval', 5)
        while not stop_event.is_set():
            snapshot = None
            try:
                with Session(engine) as sess:
                    meta = sess.exec(select(m.Metadata)).first()
                    if meta:
                        devices = sess.exec(select(m.DeviceData)).all()
                        snapshot = {
                            'time': time(),
                            'status': meta.status,
                            'devices': devices,
                            'last_updated': meta.last_updated
                        }
                if snapshot:
                    await ws.send_json({'event': 'refresh', 'data': jsonable_encoder(snapshot)})
            except WebSocketDisconnect:
                stop_event.set()
                break
            except Exception as exc:
                l.warning(f'/api/ws push failed: {exc}')
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue

    sender_task = asyncio.create_task(push_periodic_snapshot())
    try:
        await ws.send_json({'event': 'connected', 'interval': getattr(c, 'ws_refresh_interval', 5)})
        while True:
            message = await ws.receive()
            if message['type'] == 'websocket.disconnect':
                break
            if message.get('text') or message.get('bytes'):
                l.debug('Received data on /api/ws, ignoring payload')
    except WebSocketDisconnect:
        pass
    finally:
        stop_event.set()
        sender_task.cancel()
        try:
            await sender_task
        except asyncio.CancelledError:
            pass
        await manager.disconnect_pub(ws)

# endregion routes-ws

# endregion routes

# region main

app.include_router(auth_router)

if __name__ == '__main__':

    plugin_manager.load_all_plugins()

    # 2. 构建参数解析器
    parser = argparse.ArgumentParser(description='Sleepy Backend Runner & CLI')
    
    # 全局参数（适用于服务器启动）
    parser.add_argument('--fresh-start', action='store_true', help='Drop and recreate database before starting')
    
    # 3. 注册插件命令
    #    结构变为: python main.py [Global Options] [PluginName] [Command] [Args]
    #    如果未提供 PluginName，则默认行为是启动服务器
    plugin_manager.setup_cli_commands(parser)

    # 4. 解析参数
    #    如果用户输入了插件命令，argparse 会匹配到子命令
    args = parser.parse_args()

    # 5. 处理 --fresh-start (无论 CLI 还是 Server 模式，如果指定了都执行)
    if hasattr(args, 'fresh_start') and args.fresh_start:
        perform_fresh_start()

    # 6. Determine action: Execute CLI Command or Start Server
    if hasattr(args, 'func'):
        # A subcommand was triggered
        cmd_name = getattr(args, 'command', 'unknown')
        l.info(f"Executing CLI command: {cmd_name}")
        
        try:
            # Support both async and sync CLI handlers
            if inspect.iscoroutinefunction(args.func):
                asyncio.run(args.func(args))
            else:
                args.func(args)
            l.info("CLI command executed successfully.")
            exit(0)
        except Exception as ex:
            l.error(f"CLI command failed: {ex}")
            l.error(format_exc())
            exit(1)
    else:
        # No subcommand provided, start the server
        l.info(f'Starting server: {f"[{c.host}]" if ":" in c.host else c.host}:{c.port}')
        run('main:app', host=c.host, port=c.port) 
        l.info('Bye.')
        exit(0)

# endregion main
