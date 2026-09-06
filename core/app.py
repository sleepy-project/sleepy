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

'''
应用组装

启动时序 (v6 在这里出过两处错, 都在下面注明):

1. 配置 / 日志
2. **加载插件** —— 插件模块被 import, 其模型类进入 SQLModel.metadata
3. **建表** —— 必须在插件加载之后, 否则插件声明的表永远不会被创建
   (v6 的顺序是先建表再加载插件)
4. 注册路由 (含插件路由), 此时 OpenAPI 才是完整的
5. 进入 lifespan, 触发插件的 on_startup

另外, 插件加载放在模块级而不是 lifespan 内, 配合 `uvicorn.run(app_object)`
可以避免 v6 那种「`__main__` 加载一次 + `run('main:app')` 按模块名再 import 一次」
的双重初始化。
'''

import asyncio
import typing as t
from contextlib import asynccontextmanager
from json import dumps as _json_dumps
from time import time
from traceback import format_exc
from uuid import uuid4 as uuid

from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect, status as hc
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html
from fastapi.openapi.utils import get_openapi
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, RedirectResponse
from loguru import logger as l
from pydantic import BaseModel
from sse_starlette import EventSourceResponse, ServerSentEvent
from starlette.exceptions import HTTPException as StarletteHTTPException
from toml import load as load_toml

from core import auth
from core import db
from core import errors as e
from core import utils as u
from core.broadcast import manager
from core.config import config as c
from core.events import bus, APIUnsuccessfulEvent, UnhandledErrorEvent, AppStartupEvent, AppShutdownEvent
from core.logging import setup_logging, reqid
from core.plugin import plugin_manager

def json_dumps(data: t.Any) -> str:
    '''
    SSE 载荷序列化

    必须显式转成 JSON: sse_starlette 对非字符串只做 `str()`, 直接传 dict
    会发出 Python repr (单引号), 客户端 `JSON.parse` 必然失败。
    v6 的 `data=await query(sess)` 正是这个问题。
    '''
    return _json_dumps(jsonable_encoder(data), ensure_ascii=False)


# region metadata


def _load_version() -> tuple[tuple[int, int, int], str]:
    try:
        with open(u.get_path('pyproject.toml', create_dirs=False), 'r', encoding='utf-8') as f:
            meta: dict = load_toml(f).get('tool', {}).get('sleepy', {})
        raw = meta.get('version', (0, 0, 0))
        return tuple(raw), str(meta.get('version-str', 'unknown'))  # type: ignore[return-value]
    except Exception as ex:
        l.warning(f'Failed to read version from pyproject.toml: {ex}')
        return (0, 0, 0), 'unknown'


version, version_str = _load_version()
version_full = f'{version_str} ({".".join(str(i) for i in version)})'

# endregion metadata

# region models


class RootResponse(BaseModel):
    hello: str = 'sleepy'
    version: tuple[int, int, int] = (7, 0, 0)
    version_str: str = '7.0.0'


# endregion models


@asynccontextmanager
async def lifespan(app: FastAPI):
    '''
    - yield 之前 -> 启动
    - yield 之后 -> 关闭
    '''
    l.info(f'{"=" * 15} Application Startup {"=" * 15}')
    l.info(f'Sleepy Backend version {version_full}')
    if c.log.file:
        l.info(f'Saving logs to {c.log.file}')

    loaded = plugin_manager.get_loaded_plugins()
    if loaded:
        l.info(f'{len(loaded)} plugin(s) active: {", ".join(loaded)}')
    else:
        l.warning('No plugins loaded — core alone serves no business endpoints')

    await plugin_manager.startup_events()
    await bus.emit(AppStartupEvent())

    yield

    l.info('Shutting down')
    await bus.emit(AppShutdownEvent())
    await plugin_manager.shutdown_events()
    for plugin_name in list(plugin_manager.get_loaded_plugins()):
        plugin_manager.unload_plugin(plugin_name)


def create_app(load_plugins: bool = True, create_tables: bool = True) -> FastAPI:
    '''
    组装应用

    :param load_plugins: 是否加载插件 (已加载过则跳过)
    :param create_tables: 是否建表
    '''
    setup_logging()

    app = FastAPI(
        title='Sleepy Backend',
        version=version_full,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None
    )

    # --- 插件与建表 (顺序见模块 docstring) ---
    if load_plugins and not plugin_manager.get_loaded_plugins():
        l.info('Loading plugins')
        plugin_manager.load_all_plugins()
    if create_tables:
        db.create_db_and_tables()

    _setup_middleware(app)
    _setup_error_handlers(app)
    _setup_core_routes(app)
    _setup_docs(app)

    app.include_router(auth.router)
    app.include_router(auth.init_router)

    plugin_manager.setup_plugin_routes(app)

    return app


# region middleware


def _setup_middleware(app: FastAPI):
    @app.middleware('http')
    async def log_requests(request: Request, call_next: t.Callable):
        request_id = str(uuid())
        token = reqid.set(request_id)
        with l.contextualize(reqid=request_id):
            if request.client:
                ip = f'[{request.client.host}]' if ':' in request.client.host else request.client.host
                port = request.client.port
            else:
                ip, port = 'unknown-ip', 0
            l.info(f'Incoming request: {ip}:{port} - {request.method} {request.url.path}')

            p = u.perf_counter()
            try:
                resp: Response = await call_next(request)
                l.info(f'Outgoing response: {resp.status_code} ({p()}ms)')
            except Exception as ex:
                l.error(f'Server error: {ex} ({p()}ms)\n{format_exc()}')
                await bus.emit(UnhandledErrorEvent(ex))
                resp = Response(f'Internal Server Error ({request_id})', hc.HTTP_500_INTERNAL_SERVER_ERROR)

            resp.headers['X-Sleepy-Version'] = version_full
            resp.headers['X-Sleepy-Request-Id'] = request_id
            reqid.reset(token)
            return resp

    @app.middleware('http')
    async def plugin_response_middleware(request: Request, call_next: t.Callable):
        response = await call_next(request)
        if plugin_manager.get_loaded_plugins():
            response = plugin_manager.apply_response_modifiers(request, response, request.url.path)
        return response

    # 浏览器端客户端 (client/browser-script.user.js) 从任意页面发起上报,
    # 没有 CORS 会被浏览器直接拦下。v6 遗漏了这一项。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=c.cors_origins,
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
        expose_headers=['X-Sleepy-Version', 'X-Sleepy-Request-Id']
    )


# endregion middleware

# region error-handlers


def _setup_error_handlers(app: FastAPI):
    @app.exception_handler(e.APIUnsuccessful)
    async def api_unsuccessful_handler(request: Request, exc: e.APIUnsuccessful):
        evt = await bus.emit(APIUnsuccessfulEvent(exc))
        if evt.interception:
            content, code = evt.interception
            return JSONResponse(status_code=code, content=content)

        log_fn = l.error if exc.code >= 500 else l.info
        log_fn(f'APIUnsuccessful: {exc}')
        return JSONResponse(
            status_code=exc.code,
            content={'code': exc.code, 'message': exc.message, 'detail': exc.detail},
            headers=exc.headers
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        l.info(f'HTTPException: {exc.status_code} {exc.detail}')
        return JSONResponse(
            status_code=exc.status_code,
            content={
                'code': exc.status_code,
                'message': e.APIUnsuccessful.codes.get(exc.status_code, f'HTTP Error {exc.status_code}'),
                'detail': exc.detail
            },
            headers=getattr(exc, 'headers', None)
        )


# endregion error-handlers

# region core-routes


def _setup_core_routes(app: FastAPI):
    '''
    core 自身的路由

    只有框架级接口 —— 状态、设备这类业务接口由插件提供。
    '''

    @app.get('/', response_model=RootResponse, tags=['core'])
    async def root():
        return {'hello': 'sleepy', 'version': version, 'version_str': version_str}

    @app.get('/api/v1/health', status_code=hc.HTTP_204_NO_CONTENT, tags=['core'])
    async def health():
        return

    @app.get('/favicon.ico', status_code=hc.HTTP_200_OK, include_in_schema=False)
    async def favicon():
        return RedirectResponse('https://ghsrc.wyf9.top/icons/sleepy_icon_nobg.png', 302)

    @app.get('/api/v1/plugins', tags=['core'], name='List loaded plugins')
    async def list_plugins():
        return [plugin_manager.get_plugin_info(name) for name in plugin_manager.get_loaded_plugins()]

    @app.get('/api/v1/plugins/{plugin_id}', tags=['core'], name='Get plugin info')
    async def plugin_info(plugin_id: str):
        info = plugin_manager.get_plugin_info(plugin_id)
        if not info:
            raise e.APIUnsuccessful(hc.HTTP_404_NOT_FOUND, f'Plugin {plugin_id} not found')
        return info

    # --- SSE ---

    async def event_stream():
        queue = await manager.sse_connect()
        try:
            # data 必须自己序列化成 JSON: sse_starlette 对非字符串只做 str(),
            # 直接传 dict 会发出 Python repr (单引号), 客户端 JSON.parse 必然失败。
            # v6 的 `data=await query(sess)` 就是这个问题。
            yield ServerSentEvent(id='0', event='connected', data=json_dumps({
                'time': time(),
                'online': manager.online,
                **manager.snapshot()
            }))
            seq = 0
            while True:
                event, data = await queue.get()
                seq += 1
                yield ServerSentEvent(id=str(seq), event=event, data=json_dumps(data))
        except (asyncio.CancelledError, asyncio.QueueShutDown) as ex:
            l.debug(f'Event stream closing: {type(ex).__name__}')
        finally:
            await manager.sse_disconnect(queue)

    @app.get('/api/v1/events', tags=['core'], name='Server-sent event stream')
    async def events():
        return EventSourceResponse(
            event_stream(),
            media_type='text/event-stream',
            headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive', 'X-Accel-Buffering': 'no'},
            ping=c.ping_interval
        )

    # --- WebSocket ---

    @app.websocket('/api/v1/ws')
    async def websocket_public(ws: WebSocket):
        await ws.accept()
        await manager.ws_connect(ws)
        stop_event = asyncio.Event()

        async def push_snapshot_periodically():
            '''
            定时快照

            推送以事件驱动为主 (插件变更数据后调 broadcast); 这里的定时快照是兜底,
            用于纠正客户端因短暂断连而错过的事件。
            '''
            while not stop_event.is_set():
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=c.ws_refresh_interval)
                    return
                except asyncio.TimeoutError:
                    pass
                try:
                    await ws.send_json({'event': 'refresh', 'data': manager.snapshot()})
                except Exception as ex:
                    l.debug(f'/api/v1/ws periodic push failed: {ex}')
                    stop_event.set()
                    return

        sender = asyncio.create_task(push_snapshot_periodically())
        try:
            await ws.send_json({
                'event': 'connected',
                'interval': c.ws_refresh_interval,
                'data': manager.snapshot()
            })
            while True:
                message = await ws.receive()
                if message['type'] == 'websocket.disconnect':
                    break
        except WebSocketDisconnect:
            pass
        except Exception as ex:
            l.debug(f'/api/v1/ws receive loop ended: {ex}')
        finally:
            stop_event.set()
            sender.cancel()
            try:
                await sender
            except asyncio.CancelledError:
                pass
            await manager.ws_disconnect(ws)


# endregion core-routes

# region docs


def _setup_docs(app: FastAPI):
    @app.get('/docs', include_in_schema=False)
    async def custom_swagger_ui_html():
        return get_swagger_ui_html(
            openapi_url=app.openapi_url or '/openapi.json',
            title=f'{app.title} - Swagger UI',
            oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
            swagger_js_url='https://s4.zstatic.net/ajax/libs/swagger-ui/5.27.1/swagger-ui-bundle.js',
            swagger_css_url='https://s4.zstatic.net/ajax/libs/swagger-ui/5.27.1/swagger-ui.css',
            swagger_favicon_url='https://ghsrc.wyf9.top/icons/sleepy_icon_nobg.png',
        )

    if app.swagger_ui_oauth2_redirect_url:
        @app.get(app.swagger_ui_oauth2_redirect_url, include_in_schema=False)
        async def swagger_ui_redirect():
            return get_swagger_ui_oauth2_redirect_html()

    @app.get('/redoc', include_in_schema=False)
    async def redoc_html():
        return get_redoc_html(
            openapi_url=app.openapi_url or '/openapi.json',
            title=f'{app.title} - ReDoc',
            redoc_js_url='https://cdn.jsdmirror.com/npm/redoc@2/bundles/redoc.standalone.js',
            redoc_favicon_url='https://ghsrc.wyf9.top/icons/sleepy_icon_nobg.png'
        )

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes)

        components = schema.setdefault('components', {})
        components.setdefault('securitySchemes', {}).setdefault('SleepyToken', auth.OPENAPI_SECURITY_SCHEME)

        for path in schema.get('paths', {}).values():
            for operation in path.values():
                for status_code, response in operation.setdefault('responses', {}).items():
                    if isinstance(response, str):
                        operation['responses'][status_code] = {'description': response}
                    headers = operation['responses'][status_code].setdefault('headers', {})
                    headers.setdefault('X-Sleepy-Version', {
                        'description': u.cnen('Sleepy 版本', 'Sleepy version'),
                        'schema': {'type': 'string'}
                    })
                    headers.setdefault('X-Sleepy-Request-Id', {
                        'description': u.cnen('Sleepy 请求 ID', 'Sleepy Request ID'),
                        'schema': {'type': 'string'}
                    })

        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = custom_openapi  # type: ignore[method-assign]


# endregion docs


app = create_app()
'''
模块级应用实例 (供 `uvicorn core.app:app` / `fastapi run` 使用)
'''
