# coding: utf-8

from io import BytesIO
from pathlib import Path
from time import time
from datetime import datetime, timezone, timedelta
from logging import getLogger as logging_getLogger, WARNING, Handler as LoggingHandler
from contextlib import asynccontextmanager
import typing as t
import asyncio
from contextvars import ContextVar
from sys import stderr
import os
from traceback import format_exc
from uuid import uuid4 as uuid, UUID
from hashlib import sha256
from mimetypes import guess_type
import argparse

from uvicorn import run
from loguru import logger as l
from toml import load as load_toml
from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request, Header, WebSocket, WebSocketDisconnect, status as hc, Security
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse,StreamingResponse , Response
from fastapi.encoders import jsonable_encoder
from starlette.templating import Jinja2Templates as Jinja2Templates  # noqa
from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.templating import _TemplateResponse as TemplateResponse

from sqlmodel import create_engine, SQLModel, Session, select
from pydantic import BaseModel, model_validator
from starlette.exceptions import HTTPException as StarletteHTTPException
from sse_starlette import EventSourceResponse, ServerSentEvent
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html
from fastapi.openapi.utils import get_openapi
from fastapi.security import APIKeyHeader
import bcrypt
from werkzeug.security import safe_join
import schedule

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
    diagnose=True,
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


def _create_token(
    sess: Session,
    prefix: str,
    device_hash: str,
    expire_delta: timedelta | None,
    *,
    login_type: str | None = None
):
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
    l.info(f'Generated new {token_type} token {sha256(token_value.encode('utf-8'), usedforsecurity=False).hexdigest()} (sha256), expires: {expire_ts or 0.0}')
    return token_value, expire_ts


def _clear_device_tokens(sess: Session, device_hash: str):
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
    _clear_device_tokens(sess, device_hash)
    access_token, expires_at = _create_token(
        sess,
        AUTH_ACCESS_PREFIX,
        device_hash,
        timedelta(minutes=c.auth_access_token_expires_minutes),
        login_type=resolved_login_type
    )
    refresh_token, _ = _create_token(
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
    access_token, expires_at = _create_token(
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
async def _init_auth(sess: SessionDep, req: InitRequest):
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

@app.post('/api/init', response_model=InitResponse, name='Initialize auth secret')
async def init_auth(sess: SessionDep, req: InitRequest):
    return await _init_auth(sess,req)

async def _auth_login(sess: SessionDep, req: AuthLoginRequest):
    secret = _ensure_auth_initialized(sess)
    normalized = _normalize_password(req.password, req.hashed)
    if not bcrypt.checkpw(normalized.encode('utf-8', errors='xmlcharrefreplace'), secret.password):
        l.warning('Auth password mismatch during login request')
        raise e.APIUnsuccessful(hc.HTTP_401_UNAUTHORIZED, 'Incorrect password')
    return _issue_full_session(sess, req.device_uid, req.type)

@auth_router.post('/login', response_model=AuthTokensResponse, name='Login and issue auth tokens')
async def auth_login(sess: SessionDep, req: AuthLoginRequest):
    return await _auth_login(sess,req)

async def _auth_refresh(sess: SessionDep, req: AuthRefreshRequest):
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

@auth_router.post('/refresh', response_model=AuthTokensResponse, name='Refresh auth token')
async def auth_refresh(sess: SessionDep, req: AuthRefreshRequest):
    
    return await _auth_refresh(sess,req)


class TokenDep:
    def __init__(
        self,
        allowed_token_types: tuple[str, ...] | None = None,
        *,
        throw: bool = True,
        allowed_login_types: tuple[str, ...] | None = None,
        device_id: str | None = None
    ):
        self.allowed_token_types = allowed_token_types or (AUTH_ACCESS_PREFIX,)
        if allowed_login_types and not DEV_LOGIN_ALLOWED:
            self.allowed_login_types = tuple(t for t in allowed_login_types if t != 'dev') or None
        else:
            self.allowed_login_types = allowed_login_types
        self.throw = throw
        self.device_id = device_id

    def __call__(
        self,
        sess: SessionDep,
        token_value: t.Annotated[str | None, Security(sleepy_token_header)] = None,
        authorization: t.Annotated[str | None, Header(include_in_schema=False)] = None,
        request:Request = None, # type: ignore
    ) -> m.TokenData | None:
        if token_value:
            l.debug('Got token from X-Sleepy-Token security header')
        elif authorization and authorization.startswith('Bearer '):
            token_value = authorization[7:]
            l.debug('Got token from Authorization header')
        else:
            if request == None:
                l.debug('No token provided in headers')
            else:
                l.debug('No token provided in headers,try to get in cookie')
                
            

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
                    if self.device_id:
                        if login_type in ('web', 'dev'):
                            pass
                        elif login_type == 'device':
                            token_device_hash = _token_device_hash(info.type)
                            expected_device_hash = _device_hash(self.device_id)
                            if token_device_hash != expected_device_hash:
                                l.info(f'Device token cannot access device {self.device_id}')
                                if self.throw:
                                    raise e.APIUnsuccessful(hc.HTTP_403_FORBIDDEN, 'Unauthorized for this device')
                                return None
                        else:
                            l.info(f'Unknown login type {login_type} for device access')
                            if self.throw:
                                raise e.APIUnsuccessful(hc.HTTP_403_FORBIDDEN, 'Invalid token type')
                            return None

                    info.last_active = now_ts
                    sess.add(info)
                    sess.commit()
                    return info
            else:
                l.info(f'Token type {info.type} is not allowed in {self.allowed_token_types}')
        else:
            l.info('Token not found in database')

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



class QueryResponse(BaseModel):
    time: float
    status: int
    devices: list[m.DeviceData]
    last_updated: float

async def _query(sess: SessionDep):
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

@app.get('/api/query', response_model=QueryResponse)
async def query(sess: SessionDep):
    return await _query(sess)

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


@app.websocket('/api/devices/{device_id}')
async def websocket_device(ws: WebSocket, device_id: str):
    """
    设备 WebSocket 端点
    允许: web, dev, 以及该设备自己的 device token
    """

    token_value = ws.query_params.get('token') or ws.headers.get('x-sleepy-token')

    if not token_value:
        l.warning(f'WebSocket connection to device {device_id} rejected: missing token')
        await ws.close(code=1008, reason='Missing token')
        return

    with Session(engine) as sess:
        try:
            token_dep = TokenDep(
                allowed_login_types=('web', 'dev', 'device'),
                device_id=device_id,
                throw=True
            )

            token_info = token_dep(
                sess=sess,
                token_value=token_value,
                authorization=None
            )

            if not token_info:
                l.warning(f'WebSocket connection to device {device_id} rejected: invalid token')
                await ws.close(code=1008, reason='Invalid token')
                return

            login_type = _token_login_type(token_info.type)
            l.info(f'WebSocket connected for device {device_id} with {login_type} token')

        except e.APIUnsuccessful as ex:
            l.warning(f'WebSocket connection to device {device_id} rejected: {ex.message}')
            await ws.close(code=1008, reason=ex.message)
            return

    try:
        await ws.accept()

        while True:
            data: dict = await ws.receive_json()
            # 解析字段
            using = data.get('using')
            status = data.get('status')
            fields = data.get('fields', {})
            # 类型转换
            using_bool = str(using) == '1' or using is True
            # 数据库操作
            with Session(engine) as sess:
                device = sess.exec(select(m.DeviceData).where(m.DeviceData.id == device_id)).first()
                if not device:
                    device = m.DeviceData(
                        id=device_id,
                        name=device_id,
                        status=str(status) if status is not None else '',
                        using=using_bool,
                        fields=fields,
                        last_updated=time()
                    )
                    sess.add(device)
                else:
                    device.status = str(status) if status is not None else device.status
                    device.using = using_bool
                    device.fields = fields
                    device.last_updated = time()
                sess.commit()
            # 返回结果
            await ws.send_json({
                'ok': True,
                'id': device_id,
                'status': status,
                'using': using,
                'fields': fields
            })

    except WebSocketDisconnect:
        l.info(f'WebSocket disconnected for device {device_id}')
    except Exception as ex:
        l.error(f'WebSocket error for device {device_id}: {ex}')
        try:
            await ws.close(code=1011, reason='Internal error')
        except:
            pass


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

# region routes-status

status_router = APIRouter(
    prefix='/api/status',
    tags=['status']
)


class GetStatusResponse(BaseModel):
    status: int | None = 0

async def _get_status(sess: SessionDep):
    meta = sess.exec(select(m.Metadata)).first()
    if meta:
        return {
            'status': meta.status
        }
    else:
        raise e.APIUnsuccessful(hc.HTTP_500_INTERNAL_SERVER_ERROR, 'Cannot read metadata')

@status_router.get('/', response_model=GetStatusResponse)
async def get_status(sess: SessionDep):
    return await _get_status(sess)

class SetStatusRequest(BaseModel):
    status: int

async def _set_status(
    sess: SessionDep,
    req: SetStatusRequest,
):
    meta = sess.exec(select(m.Metadata)).first()
    if not meta:
        raise e.APIUnsuccessful(hc.HTTP_500_INTERNAL_SERVER_ERROR, 'Cannot update metadata')
    elif meta.status == req.status:
        return
    else:
        meta.status = req.status
        meta.last_updated = time()
        sess.commit()
        await manager.evt_broadcast('status_changed', {'status': req.status})
        return
@status_router.post('/', status_code=hc.HTTP_204_NO_CONTENT)
async def set_status(
    sess: SessionDep,
    req: SetStatusRequest,
    _: m.TokenData = Security(TokenDep(allowed_login_types=('web', 'dev')))
):
    await _set_status(sess,req)

# endregion routes-status

# region routes-device

devices_router = APIRouter(
    prefix='/api/devices',
    tags=['devices']
)

async def _get_device(sess: SessionDep, device_id: str):
    device = sess.get(m.DeviceData, device_id)
    if device:
        return device
    else:
        raise e.APIUnsuccessful(hc.HTTP_404_NOT_FOUND, 'Device not found')
@devices_router.get('/{device_id}', response_model=m.DeviceData)
async def get_device(sess: SessionDep, device_id: str):
    return await _get_device(sess,device_id)


class UpdateDeviceRequest(BaseModel):
    name: str | None = None
    status: str | None = None
    using: bool | None = None
    fields: dict | None = None


class CreateDeviceRequest(BaseModel):
    name: str
    # name: str
    status: str | None = None
    using: bool | None = None
    fields: dict | None = None


class CreateDeviceResponse(BaseModel):
    id: str
    device: m.DeviceData
    token: UUID
    refresh_token: UUID
    expires_at: float | None = None

async def _create_device(
    sess: SessionDep,
    req: CreateDeviceRequest,
):
    device_id = uuid().hex
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
    tokens = _issue_full_session(sess, device_id, 'device')
    await manager.evt_broadcast('device_added', {
        'id': device_id,
        'name': req.name,
        'status': status,
        'using': using,
        'fields': fields
    })
    return {
        'id': device_id,
        'device': device,
        'token': tokens.token,
        'refresh_token': tokens.refresh_token,
        'expires_at': tokens.expires_at
    }
@devices_router.post('/', response_model=CreateDeviceResponse, status_code=hc.HTTP_201_CREATED, name='Create a device')
async def create_device(
    request : Request,
    sess: SessionDep,
    req: CreateDeviceRequest,
    _: m.TokenData = Security(TokenDep(allowed_login_types=('web', 'dev')))
):
    return await _create_device(sess,req)

async def _update_device(
    sess: SessionDep,
    device_id: str,
    req: UpdateDeviceRequest,):
    device = sess.get(m.DeviceData, device_id)
    if device:
        updated = {}
        # exist -> update
        if req.name is not None:
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
        raise e.APIUnsuccessful(hc.HTTP_404_NOT_FOUND, 'Device not found')

@devices_router.put('/{device_id}', status_code=hc.HTTP_204_NO_CONTENT, name='Update a device')
async def update_device(
    sess: SessionDep,
    device_id: str,
    req: UpdateDeviceRequest,
    token_value: t.Annotated[str | None, Security(sleepy_token_header)] = None,
    authorization: t.Annotated[str | None, Header(include_in_schema=False)] = None
):

    TokenDep(
        allowed_login_types=('web', 'dev', 'device'),
        device_id=device_id
    )(sess, token_value, authorization)
    await _update_device(sess,device_id,req)


    
async def _delete_device(
    sess: SessionDep,
    device_id: str,
):
    device = sess.get(m.DeviceData, device_id)
    if device:
        device_hash = _device_hash(device.id)
        sess.delete(device)
        meta = sess.exec(select(m.Metadata)).first()
        if meta:
            meta.last_updated = time()
        _clear_device_tokens(sess, device_hash)
        sess.commit()
        await manager.evt_broadcast('device_deleted', {'id': device_id})
@devices_router.delete('/{device_id}', status_code=hc.HTTP_204_NO_CONTENT)
async def delete_device(
    sess: SessionDep,
    device_id: str,
    _: m.TokenData = Security(TokenDep(allowed_login_types=('web', 'dev')))
):
    await _delete_device(sess,device_id)
    return


class GetDevicesResponse(BaseModel):
    devices: list[m.DeviceData]

async def _get_devices(sess: SessionDep) -> t.Sequence[m.DeviceData]:
    devices = sess.exec(select(m.DeviceData)).all()
    return devices

@devices_router.get('/', response_model=GetDevicesResponse)
async def get_devices(sess: SessionDep):
    return {
        'devices': await _get_devices(sess)
    }

async def _clear_devices(sess: SessionDep):
    devices = sess.exec(select(m.DeviceData)).all()
    for d in devices:
        _clear_device_tokens(sess, _device_hash(d.id))
        sess.delete(d)
    meta = sess.exec(select(m.Metadata)).first()
    if meta:
        meta.last_updated = time()
    sess.commit()
    await manager.evt_broadcast('devices_cleared')
    return

@devices_router.delete('/', status_code=hc.HTTP_204_NO_CONTENT)
async def clear_devices(
    sess: SessionDep,
    _: m.TokenData = Security(TokenDep(allowed_login_types=('web', 'dev')))
):
    await _clear_devices(sess=sess)
    return

# endregion routes-device

# endregion routes

# region frontend

# --- 缓存系统
_cache: dict[str, tuple[float, BytesIO]] = {}

def get_cached_file(dirname: str, filename: str) -> BytesIO | None:
        '''
        加载文件 (经过缓存)

        :param dirname: 路径
        :param filename: 文件名
        :return bytesIO: (加载成功) 文件内容 **(字节流)**
        :return None: (加载失败) 空
        '''
        filepath = os.path.join(u.get_path(dirname), filename)
        if not filepath:
            # unsafe -> none
            return None
        try:
            if app.debug:
                # debug -> load directly
                with open(filepath, 'rb') as f:
                    return BytesIO(f.read())
            else:
                cache_key = f'f-{dirname}/{filename}'
                # check cache & expire
                now = time()
                cached = _cache.get(cache_key)
                if cached and now - cached[0] < c.cache_age:
                    # has cache, and not expired
                    return cached[1]
                else:
                    # no cache, or expired
                    with open(filepath, 'rb') as f:
                        ret = BytesIO(f.read())
                    _cache[cache_key] = (now, ret)
                    return ret
        except FileNotFoundError or IsADirectoryError:
            # not found / isn't file -> none
            return None

def get_cached_text(dirname: str, filename: str) -> str | None:
        '''
        加载文本文件 (经过缓存)

        :param dirname: 路径
        :param filename: 文件名
        :return bytes: (加载成功) 文件内容 **(字符串)**
        :return None: (加载失败) 空
        '''
        raw = get_cached_file(dirname, filename)
        if raw:
            try:
                return str(raw.getvalue(), encoding='utf-8')
            except UnicodeDecodeError:
                return None
        else:
            return None

def _clean_cache():
        '''
        清理过期缓存
        '''
        if app.debug:
            return
        now = time()
        for name in _cache.keys():
            if now - _cache.get(name, (now, ''))[0] > c.cache_age:
                f = _cache.pop(name, (0, None))[1]
                if f:
                    f.close()
# ========== Theme ==========

# region theme
_themes_available_cache = sorted(u.list_dirs('theme', name_only=True))


def themes_available() -> list[str]:
    if app.debug:
        return sorted(u.list_dirs('theme', name_only=True))
    else:
        return _themes_available_cache
    
#generated by ai
def render_template(request: Request,filename: str, _dirname: str = 'templates', _theme: str | None = None, **context) -> str | None:
    '''
    渲染模板 (使用指定主题)

    :param filename: 文件名
    :param _dirname: `theme/[主题名]/<dirname>/<filename>`
    :param _theme: 主题 (未指定则从 `flask.g.theme` 读取)
    :param **context: 将传递给 `flask.render_template_string` 的模板上下文
    '''
    l.info(f'[render_template] filename:{filename}')
    if _theme is None:
        _theme = request.cookies.get("sleepy-theme", "default")
    # content = get_cached_text('theme', f'{_theme}/{_dirname}/{filename}')
    path_obj = Path('theme') / _theme / _dirname
    content = path_obj / filename
    if not content.exists():
        # 回退到默认主题
        path_obj = Path("theme") / "default" / _dirname
        content = path_obj / filename
        if not content.exists():
            raise HTTPException(404, f"Template {_dirname}/{filename} not found")
    env = Environment(
        loader=FileSystemLoader(path_obj),
        autoescape=select_autoescape(['html', 'xml'])
    )
    env.globals['request'] = request
    env.globals['url_for'] = request.url_for
    
    template = env.get_template(name=filename)
    return template.render(**context)

@app.get('/static/static/{filename:path}', name="static")
def static_proxy(filename: str):
    '''
    静态文件的主题处理 (重定向到 /static-themed/主题名/static/文件名)
    '''
    # 重定向
    l.info(f'/static-themed/{c.page.theme}/static/{filename}')
    return RedirectResponse(f'/static-themed/{c.page.theme}/static/{filename}', 302)

@app.get('/static/{filename:path}', name="theme")
def theme_proxy(filename: str):
    '''
    静态文件的主题处理 (重定向到 /static-themed/主题名/文件名)
    '''
    # 重定向
    return RedirectResponse(f'/static-themed/{c.page.theme}/{filename}', 302)




@app.get('/static-themed/{theme}/{filename:path}')
def static_themed(theme: str, filename: str):
    '''
    经过主题分隔的静态文件 (便于 cdn / 浏览器 进行缓存)
    '''
    try:
        l.debug(f'[theme] return static file {filename} from theme {theme}')
        return FileResponse(f"theme/{theme}/{filename}")
    except :
        # 2. 主题不存在 (而且不是默认) -> fallback 到默认
        if theme != 'default':
            l.debug(f'[theme] static file {filename} not found in theme {theme}, fallback to default')
            # return u.no_cache_response(flask.redirect(f'/static-themed/default/{filename}', 302))
            return RedirectResponse(f'/static-themed/default/{filename}', 302)

        # 3. 默认主题也没有 -> 404
        else:
            l.warning(f'[theme] static file {filename} not found')
            return HTTPException(404,f"static file {filename} not found")


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
    return FileResponse(f"./theme/default/{filename}")


# endregion theme

# ----- Panel (Admin) -----

# region routes-panel
panel_router = APIRouter(
    prefix='/panel',
    tags=['panel']
)

@app.get('/panel')
def admin_panel(request:Request,
                sess: SessionDep,
                ):
    '''
    管理面板
    - Method: **GET**
    '''
    token = TokenDep(
        throw=False,
        allowed_login_types=('web',),
    )(sess, request.cookies.get("sleepy_secret_token"), None,request=request)

    if(token == None):
        return RedirectResponse("/panel/login")
    # 加载管理面板卡片
    # cards = {}
    # for name, card in plugin_manager.panel_cards.items():
    #     if hasattr(card['content'], '__call__'):
    #         cards[name] = card.copy()
    #         cards[name]['content'] = card['content']()  # type: ignore
    #     else:
    #         cards[name] = card

    # 处理管理面板注入
    # inject = ''
    # for i in p.panel_injects:
    #     if hasattr(i, '__call__'):
    #         inject += str(i()) + '\n'  # type: ignore
    #     else:
    #         inject += str(i) + '\n'

    # 问题是plugin没写(
    return HTMLResponse(render_template(
        request,
        'panel.html',
        c=c,
        cards={"":""},
        current_theme='default',
        available_themes=themes_available(),
        # cards=cards,
        # inject=inject
    ))
@panel_router.get('/init')
def panel_init(request:Request,
                sess: SessionDep,
                ):
    '''
    init页面
    - Method: **GET**
    '''
    if _is_auth_initialized(sess):
        return RedirectResponse("/panel/login")
    return HTMLResponse(render_template(
        request,
        'init.html',
        c=c,
        current_theme='default'
    ))

@panel_router.get('/login')
def panel_login(request:Request,
                sess: SessionDep,):
    '''
    登录页面
    - Method: **GET**
    '''
    token = TokenDep(
        throw=False,
        allowed_login_types=('web',),
    )(sess, request.cookies.get("sleepy_secret_token"), None,request=request)


    # if(token != None):
    #     return RedirectResponse("/panel")
    return HTMLResponse(render_template(
        request,
        'login.html',
        c=c,
        current_theme='default'
    ))


# region routes-panel-api

@panel_router.get('/verify')
@panel_router.post('/verify')
async def panel_api_verify_secret(request:Request,
                sess: SessionDep):
    '''
    验证密钥是否有效
    - Method: **GET / POST**
    '''
    token = TokenDep(
        throw=True,
        allowed_login_types=('web',),
    )(sess, request.cookies.get("sleepy_secret_token"), None,request=request)

    l.debug('[Panel] Secret verified')
    return {
        'success': True,
        'code': 'OK',
        'message': 'Secret verified'
    }
panel_api_router = APIRouter(
    prefix='/panel/api',
    tags=['panel-api']
)
@panel_api_router.get('/init')
async def panel_api_init(request:Request,
                sess: SessionDep,
                req:InitRequest
                ):
    '''
    登录页面
    - Method: **GET**
    '''
    return await _init_auth(sess,req)

@panel_api_router.post('/login')
async def panel_api_login(request:Request,
                sess: SessionDep,
                req: AuthLoginRequest
                ):
    '''
    登录页面api
    - Method: **GET**
    '''
    response = await _auth_login(sess,req)
    request.cookies['sleepy_secret_refresh_token'] = response.refresh_token.hex
    request.cookies['sleepy_secret_token'] = response.token.hex
    request.cookies['expires_at'] = str(response.expires_at)
    
    return response

# endregion routes-panel-api
# endregion routes-panel
app.include_router(auth_router)
app.include_router(devices_router)
app.include_router(status_router)
app.include_router(panel_router)
app.include_router(panel_api_router)

@app.get('/')
async def root(request: Request,sess: SessionDep):
    '''
    根目录返回 html
    - Method: **GET**
    '''
    # 获取更多信息 (more_text)
    more_text: str = c.page.more_text
    # if c.metrics.enabled:
    #     daily, weekly, monthly, yearly, total = d.metric_data_index
    #     more_text = more_text.format(
    #         visit_daily=daily,
    #         visit_weekly=weekly,
    #         visit_monthly=monthly,
    #         visit_yearly=yearly,
    #         visit_total=total
    #     )
    # lazyboy
    print(1)
    meta = sess.exec(select(m.Metadata)).first()
    if meta:
        devices = sess.exec(select(m.DeviceData)).all()
    else:
        return HTTPException(500,"async def root(request: Request,sess: SessionDep):devices = sess.exec(select(m.DeviceData)).all() error!")
    main_card: str = render_template(  # type: ignore
        request=request,
        filename='main.index.html',
        _dirname='cards',
        username=c.page.name,
        status=devices[0].status,
        last_updated=datetime.fromtimestamp(devices[0].last_updated, timezone.utc).strftime(f'%Y-%m-%d %H:%M:%S') + ' (UTC+8)'
    )
    more_info_card: str = render_template(  # type: ignore
        request=request,
        filename='more_info.index.html',
        _dirname='cards',
        more_text=more_text,
        username=c.page.name,
        learn_more_link=c.page.learn_more_link,
        learn_more_text=c.page.learn_more_text,
        available_themes=themes_available()
    )
    l.info(2)

    # 加载插件卡片
    cards = {
        'main': main_card,
        'more-info': more_info_card
    }
    # for name, values in p.index_cards.items():
    #     value = ''
    #     for v in values:
    #         if hasattr(v, '__call__'):
    #             value += f'{v()}<br/>\n'  # type: ignore - pylance 不太行啊 (?
    #         else:
    #             value += f'{v}<br/>\n'
    #     cards[name] = value

    # 处理主页注入
    # injects: list[str] = []
    # for i in plu.index_injects:
    #     if hasattr(i, '__call__'):
    #         injects.append(str(i()))  # type: ignore
    #     else:
    #         injects.append(str(i))

    # evt = plugin_manager.trigger_event(pl.IndexAccessEvent(page_title=c.page.title, page_desc=c.page.desc, page_favicon=c.page.favicon, page_background=c.page.background, cards=cards, injects=injects))

    # if evt.interception:
    #     return evt.interception
    # 返回 html
    return HTMLResponse(render_template(
        request=request,
        filename='index.html',
        page_title=c.page.title,
        page_desc=c.page.desc,
        page_favicon=c.page.favicon,
        page_background=c.page.background,
        cards=cards,
        # inject='\n'.join(evt.injects)
    ))

    
# endregion frontend
# region main

@app.get('/{path_name:path}')
async def serve_public(request: Request, path_name: str):
    '''
    服务 `/data/public` / `/public` 文件夹下文件
    '''
    l.debug(f'Serving static file: {path_name}')
    file = get_cached_file('data/public', path_name) or get_cached_file('public', path_name)
    if file:
        mime = guess_type(path_name)[0] or 'text/plain'
        return StreamingResponse(file)
    else:
        return HTTPException(404)

if __name__ == '__main__':
    args = parse_cli_args()
    if args.fresh_start:
        perform_fresh_start()
    schedule.every(c.cache_age).seconds.do(_clean_cache)  # cache
    l.info(f'Starting server: {f"[{c.host}]" if ":" in c.host else c.host}:{c.port}')  # with {c.workers} workers')
    run('main:app', host=c.host, port=c.port)  # , workers=c.workers)
    l.info('Bye.')
    exit(0)

# endregion main
