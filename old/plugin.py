import os
import importlib
import typing as t
from logging import getLogger
from functools import wraps
from contextlib import contextmanager
from traceback import format_exc
from collections import defaultdict
from datetime import datetime

import flask
from werkzeug.exceptions import HTTPException
from toml import loads as load_toml

from models import ConfigModel, _StatusItemModel
from data import Data, _DeviceStatusData
import utils as u

l = getLogger(__name__)

# region events


class BaseEvent:
    '''
    事件基类
    '''
    id: str
    '''事件 id'''
    time: datetime = datetime.now()
    '''事件生成时间'''
    interceptable: bool = True
    '''事件是否可拦截'''

    interception: tuple[t.Any, int] | None = None
    '''拦截后返回结果 (如被拦截)'''
    request: flask.Request | None = flask.request if flask.request else None
    '''触发事件的请求 (如有)'''

    def __init__(self):
        pass

    def intercept(self, response: t.Any, code: int = 200):
        '''
        中断事件, 并提前返回 (如果可中断)

        :param response: 中断后返回的内容
        :param code: 中断后返回的 HTTP 状态码
        '''
        if self.interceptable:
            self.interception = response, code

# region events-run


class AppInitializedEvent(BaseEvent):
    '''
    应用初始化完成事件
    '''
    id = 'app_initialized'
    interceptable = False


class AppStartedEvent(BaseEvent):
    '''
    应用启动事件
    '''
    id = 'app_started'
    interceptable = False


class AppStoppedEvent(BaseEvent):
    '''
    应用停止事件
    '''
    id = 'app_stopped'
    interceptable = False

    def __init__(self, exitcode: int):
        self.exitcode = exitcode

# endregion events-run

# region events-error


class APIUnsuccessfulEvent(BaseEvent):
    '''
    触发 APIUnsuccessful 事件
    '''
    id = 'api_unsuccessful'
    interceptable = True

    def __init__(self, error: u.APIUnsuccessful):
        self.error = error


class HTTPErrorEvent(BaseEvent):
    '''
    触发 HTTP Error 事件
    '''
    id = 'http_error'
    interceptable = True

    def __init__(self, error: HTTPException):
        self.error = error


class UnhandledErrorEvent(BaseEvent):
    '''
    触发未捕获错误事件
    '''
    id = 'unhandled_error'
    interceptable = True

    def __init__(self, error: Exception):
        self.error = error

# endregion events-error

# region events-request


class BeforeRequestHook(BaseEvent):
    '''
    before_request 钩子
    '''
    id = 'before_request'
    interceptable = True


class AfterRequestHook(BaseEvent):
    '''
    after_request 钩子
    '''
    id = 'after_request'
    interceptable = True

    def __init__(self, response: flask.Response):
        self.response = response

# endregion events-request

# region events-special


class IndexAccessEvent(BaseEvent):
    '''
    请求主页事件
    '''
    id = 'index_access'
    interceptable = True

    def __init__(self, page_title: str, page_desc: str, page_favicon: str, page_background: str, cards: dict[str, str], injects: list[str]):
        self.page_title = page_title
        self.page_desc = page_desc
        self.page_favicon = page_favicon
        self.page_background = page_background
        self.cards = cards
        self.injects = injects


class FaviconAccessEvent(BaseEvent):
    '''
    请求 /favicon.ico 事件
    '''
    id = 'favicon_access'
    interceptable = True

    def __init__(self, favicon_url: str):
        self.favicon_url = favicon_url


class MetadataAccessEvent(BaseEvent):
    '''
    请求 /api/meta 事件
    '''
    id = 'metadata_access'
    interceptable = True

    def __init__(self, metadata: dict):
        self.metadata = metadata


class MetricsAccessEvent(BaseEvent):
    '''
    请求 /api/metrics 事件
    '''
    id = 'metrics_access'
    interceptable = True

    def __init__(self, metrics_repsonse: dict[str, t.Any]):
        self.metrics_response = metrics_repsonse

# endregion events-special

# region events-status


class QueryAccessEvent(BaseEvent):
    '''
    请求 /api/status/query 事件
    '''
    id = 'query_access'
    interceptable = True

    def __init__(self, query_response: dict[str, t.Any]):
        self.query_response = query_response


class StreamConnectedEvent(BaseEvent):
    '''
    event stream 连接事件 (请求 /api/status/events)
    '''
    id = 'stream_connected'
    interceptable = True

    def __init__(self, event_id: int):
        # 说实话我也不知道为什么自己要加一个 Last-Event-Id
        self.event_id = event_id


class StreamDisconnectedEvent(BaseEvent):
    '''
    event stream 断开事件
    '''
    id = 'stream_disconnected'
    interceptable = False


class StatusUpdatedEvent(BaseEvent):
    '''
    手动状态更新事件
    '''
    id = 'status_updated'
    interceptable = True

    def __init__(self, old_exists: bool, old_status: _StatusItemModel, new_exists: bool, new_status: _StatusItemModel):
        '''
        :param old_exists: 旧状态是否存在
        :param old_status: 旧状态
        :param new_exists: 新状态是否存在
        :param new_status: 新状态
        '''
        self.old_exists = old_exists
        self.old_status = old_status
        self.new_exists = new_exists
        self.new_status = new_status


class StatuslistAccessEvent(BaseEvent):
    '''
    请求 /api/status/list 事件
    '''
    id = 'statuslist_access'
    interceptable = True

    def __init__(self, status_list: list[_StatusItemModel]):
        self.status_list = status_list

# endregion events-status

# region events-device


class DeviceSetEvent(BaseEvent):
    '''
    设备状态更新事件 (请求 /api/device/set)
    '''
    id = 'device_set'
    interceptable = True

    def __init__(self, device_id: str | None, show_name: str | None, using: bool | None, status: str | None, fields: dict[str, t.Any]):
        '''
        :param device_id: 设备 id
        :param show_name: 设备前台显示名称
        :param using: 设备是否在使用
        :param status: 设备状态
        '''
        self.device_id = device_id
        self.show_name = show_name
        self.using = using
        self.status = status
        self.fields = fields


class DeviceRemovedEvent(BaseEvent):
    '''
    设备移除事件
    '''
    id = 'device_removed'
    interceptable = True

    def __init__(self, exists: bool, device_id: str, show_name: str | None, using: bool | None, status: str | None, fields: dict[str, t.Any] | None):
        '''
        :param exists: 设备在请求时是否存在
        :param device_id: 设备 id
        :param show_name: 设备前台显示名称
        :param using: 设备是否在使用
        :param status: 设备状态
        '''
        self.exists = exists
        self.device_id = device_id
        self.show_name = show_name
        self.using = using
        self.status = status
        self.fields = fields


class DeviceClearedEvent(BaseEvent):
    '''
    设备清除事件
    '''
    id = 'device_cleared'
    interceptable = True

    def __init__(self, devices: dict[str, _DeviceStatusData]):
        self.devices = devices


class PrivateModeChangedEvent(BaseEvent):
    '''
    隐私模式切换事件
    '''
    id = 'private_mode_changed'
    interceptable = True

    def __init__(self, old_status: bool, new_status: bool):
        '''
        :param old_status: 旧状态
        :param new_status: 新状态
        '''
        self.old_status = old_status
        self.new_status = new_status

# endregion events-device

# endregion events

# region plugin-api


class VersionNotMatchException(BaseException):
    '''
    版本不匹配错误
    '''

    def __init__(self, plugin_name: str, now: tuple[int, int, int], min: tuple[int, int, int] | None = None, max: tuple[int, int, int] | None = None):
        self.now = '.'.join(str(v) for v in now)
        self.min = '.'.join(str(v) for v in min) if min else None
        self.max = '.'.join(str(v) for v in max) if max else None

        if self.min:
            self.message = f'Main program is version {self.now}, but plugin {plugin_name} needs >={self.min}!'
        elif self.max:
            self.message = f'Main program is version {self.now}, but plugin {plugin_name} needs <{self.max}!'
        else:
            self.message = f'Incorrent VersionNotMatchException calling on plugin {plugin_name}!'

    def __str__(self):
        return self.message

class Plugin:
    '''
    Sleepy 插件接口
    '''
    name: str
    '''插件名称 (即文件夹名)'''
    config: t.Any
    '''插件配置 (如传入 Model 则为对应 Model 实例, 否则为字典)'''
    _registry: dict[str, t.Any] = {}
    '''存放插件实例'''

    def __init__(
        self,
        name: str,
        config: t.Any = {},
        data: dict = {},
        require_version_min: tuple[int, int, int] | None = None,
        require_version_max: tuple[int, int, int] | None = None
    ):
        '''
        初始化插件

        :param name: 插件名称 (id?, 通常为 `__name__`)
        :param config: *(Model / dict)* 插件默认配置 (可选)
        :param data: 插件默认数据 (可选)
        :param require_version_min: 适用的最小 sleepy 版本 (包括)
        :param require_version_max: 适用的最小 sleepy 版本 (不包括)
        '''
        self.name = name.split('.')[-1]

        # 检查版本要求
        sleepy_ver = PluginInit.instance.version
        pyproject_path = u.get_path(f'plugins/{self.name}/pyproject.toml')
        if os.path.exists(pyproject_path):
            with open(pyproject_path, 'r', encoding='utf-8') as f:
                pyproject: dict = load_toml(f.read())
        else:
            pyproject: dict = {}

        require_version_min = require_version_min or tuple(pyproject.get('tool', {}).get('sleepy', {}).get('require_version_min', (None)))
        require_version_max = require_version_max or tuple(pyproject.get('tool', {}).get('sleepy', {}).get('require_version_max', ()))

        if require_version_min and (not require_version_min <= sleepy_ver):
            raise VersionNotMatchException(self.name, now=sleepy_ver, min=require_version_min)

        if require_version_max and (not sleepy_ver < require_version_max):
            raise VersionNotMatchException(self.name, now=sleepy_ver, max=require_version_max)

        # 初始化 & 注册插件
        Plugin._registry[self.name] = self

        # 加载配置)
        if not config:
            # 1. None -> raw
            self.config = PluginInit.instance.c.plugin.get(self.name, {})
        elif isinstance(config, dict):
            # 2. dict -> default + raw -> dict
            config_dict = u.deep_merge_dict(config, PluginInit.instance.c.plugin.get(self.name, {}))
            self.config = config_dict
        else:
            # 3. model -> default model + raw -> model
            config_dict = PluginInit.instance.c.plugin.get(self.name, {})
            self.config = config.model_validate(config_dict)

        self.data = u.deep_merge_dict(data, self.data)

    # region plugin-api-data

    @property
    def data(self):
        '''
        插件数据存储
        '''
        return PluginInit.instance.d.get_plugin_data(self.name)

    @data.setter
    def data(self, value: dict):
        PluginInit.instance.d.set_plugin_data(id=self.name, data=value)

    @contextmanager
    def data_context(self):
        '''
        数据上下文 (在退出时自动保存)

        ```
        with plugin.data_context() as data:
            data['calls'] = data.get('calls', 0) + 1
        ```
        '''
        data = self.data
        yield data
        if data != self.data:
            self.data = data

    def set_data(self, key, value):
        '''
        设置数据值
        '''
        data = self.data
        data[key] = value
        self.data = data

    def get_data(self, key, default=None):
        '''
        获取数据值
        '''
        return self.data.get(key, default)

    @property
    def global_config(self) -> ConfigModel:
        '''
        全局配置 (`config.Config()`)
        '''
        return PluginInit.instance.c

    @property
    def global_data(self) -> Data:
        '''
        全局数据 (`data.Data().data`)
        '''
        return PluginInit.instance.d

    @property
    def _app(self) -> flask.Flask:
        '''
        直接访问 flask.Flask 实例 (不建议使用)
        '''
        return PluginInit.instance.app

    # endregion plugin-api-data

    # region plugin-api-route

    def add_route(self, func: t.Callable, rule: str, _wrapper: t.Callable | None = None, **options: t.Any):
        '''
        注册插件路由 **(访问: `/plugin/<name>/<rule>`)**

        :param func: 处理路由的视图函数
        :param rule: 路由规则 (路径)
        :param options: 其他传递给 Flask 的参数 *(`_wrapper` 除外)*
        '''
        endpoint = options.pop('endpoint', func.__name__)
        full_rule = f'/plugin/{self.name}{"" if rule.startswith("/") else "/"}{rule}'

        PluginInit.instance._register_route(
            rule=full_rule,
            endpoint=f'plugin.{self.name}.{endpoint}',
            view_func=_wrapper or func,
            options=options
        )

    def route(self, rule: str, **options: t.Any):
        '''
        **[装饰器]** 注册插件路由 **(访问: `/plugin/<name>/<rule>`)**

        :param rule: 路由规则 (路径)
        :param options: 其他传递给 Flask 的参数
        ```
        @plugin.route('/endpoint')
        def handler():
            return 'Hello from plugin!'
        ```
        '''
        def decorator(f):

            @wraps(f)
            def wrapper(*args, **kwargs):
                return f(*args, **kwargs)

            self.add_route(
                func=f,
                rule=rule,
                _wrapper=wrapper,
                **options
            )
            return wrapper
        return decorator

    def add_global_route(self, func: t.Callable, rule: str, _wrapper: t.Callable | None = None, **options: t.Any):
        '''
        注册全局插件路由 **(访问: `/<rule>`)**

        :param func: 处理路由的视图函数
        :param rule: 路由规则 (路径)
        :param options: 其他传递给 Flask 的参数
        '''
        endpoint = options.pop('endpoint', func.__name__)
        full_rule = f'{"" if rule.startswith("/") else "/"}{rule}'

        PluginInit.instance._register_route(
            rule=full_rule,
            endpoint=f'plugin_global.{self.name}.{endpoint}',
            view_func=_wrapper or func,
            options=options
        )

    def global_route(self, rule: str, **options: t.Any):
        '''
        [装饰器] 注册全局插件路由 **(访问: `/<rule>`)**

        :param rule: 路由规则 (路径)
        :param options: 其他传递给 Flask 的参数
        ```
        @plugin.route('/global-endpoint')
        def handler():
            return "Hello from plugin"
        ```
        '''
        def decorator(f):
            @wraps(f)
            def wrapper(*args, **kwargs):
                return f(*args, **kwargs)

            self.add_global_route(
                func=f,
                rule=rule,
                _wrapper=wrapper,
                **options
            )
            return wrapper
        return decorator

    # endregion plugin-api-route

    # region plugin-api-cards

    def add_index_card(self, card_id: str, content: str | t.Callable):
        '''
        注册 index.html 卡片 (如已有则追加到末尾)

        :param card_id: 用于区分不同卡片
        :param content: 卡片 HTML 内容
        '''
        PluginInit.instance.index_cards[card_id].append(content)

    def index_card(self, card_id: str):
        '''
        [装饰器] 注册 index.html 卡片 (如已有则追加到末尾)

        :param card_id: 用于区分不同卡片
        '''
        def decorator(f):
            @wraps(f)
            def wrapper(*args, **kwargs):
                return f(*args, **kwargs)

            self.add_index_card(
                card_id=card_id,
                content=wrapper
            )
            return wrapper
        return decorator

    def add_panel_card(self, card_id: str, card_title: str, content: str | t.Callable):
        '''
        注册管理面板卡片 (唯一, 不可追加)

        :param card_id: 用于区分不同卡片
        :param content: 卡片 HTML 内容
        '''
        PluginInit.instance.panel_cards[card_id] = {
            'title': card_title,
            'plugin': self.name,
            'content': content
        }
        return card_id

    def panel_card(self, card_id: str, card_title: str):
        '''
        [装饰器] 注册管理面板卡片 (唯一, 不可追加)

        :param card_id: 用于区分不同卡片
        '''
        def decorator(f):
            @wraps(f)
            def wrapper(*args, **kwargs):
                return f(*args, **kwargs)

            self.add_panel_card(
                card_id=card_id,
                card_title=card_title,
                content=wrapper
            )
            return wrapper
        return decorator

    # endregion plugin-api-cards

    # region plugin-api-injects

    def add_index_inject(self, content: str | t.Callable):
        '''
        主页注入 (不显示卡片)

        :param content: 注入 HTML 内容
        '''
        PluginInit.instance.index_injects.append(content)

    def index_inject(self):
        '''
        [装饰器] 主页注入 (不显示卡片)
        '''
        def decorator(f):
            @wraps(f)
            def wrapper(*args, **kwargs):
                return f(*args, **kwargs)

            self.add_index_inject(wrapper)
            return wrapper
        return decorator

    def add_panel_inject(self, content: str | t.Callable):
        '''
        管理面板注入 (不显示卡片)

        :param content: 注入 HTML 内容
        '''
        PluginInit.instance.panel_injects.append(content)

    def panel_inject(self):
        '''
        [装饰器] 管理面板注入 (不显示卡片)
        '''
        def decorator(f):
            @wraps(f)
            def wrapper(*args, **kwargs):
                return f(*args, **kwargs)

            self.add_panel_inject(wrapper)
            return wrapper
        return decorator

    # endregion plugin-api-injects

    def register_event(self, event: type[BaseEvent], handler: t.Callable):
        '''
        注册事件处理器

        :param event: 要注册的事件对象
        :param handler: 处理函数
        '''
        PluginInit.instance.events[event.id].append(handler)

    def event_handler(self, event: type[BaseEvent]):
        '''
        [装饰器] 注册事件处理器

        :param event: 要注册的事件对象
        '''
        def decorator(f):
            @wraps(f)
            def wrapper(*args, **kwargs):
                return f(*args, **kwargs)

            self.register_event(event=event, handler=wrapper)
            return wrapper
        return decorator

    def init(self):
        '''
        初始化时将执行此函数 (可覆盖)
        '''

# endregion plugin-api

# region plugin-init


class PluginInit:
    '''
    Plugin System Init
    '''
    version: tuple[int, int, int]
    '''主程序版本'''
    c: ConfigModel
    d: Data
    app: flask.Flask
    plugins_loaded: list[Plugin] = []
    '''已加载的插件'''
    index_cards: defaultdict[str, list[str | t.Callable]] = defaultdict(list)
    '''主页卡片'''
    index_injects: list[str | t.Callable] = []
    '''主页注入'''
    panel_cards: dict[str, dict[str, str | t.Callable]] = {}
    '''管理面板卡片'''
    panel_injects: list[str | t.Callable] = []
    '''管理面板注入'''
    events: defaultdict[str, list[t.Callable]] = defaultdict(list)
    '''事件注册表'''

    def __init__(self, version: tuple[int, int, int], config: ConfigModel, data: Data, app: flask.Flask):
        self.version = version
        self.c = config
        self.d = data
        self.app = app
        PluginInit.instance = self

    def load_plugins(self):
        '''
        加载插件
        '''
        for plugin_name in self.c.plugins_enabled:
            # 加载单个插件
            try:
                if not os.path.isfile(u.get_path(f'plugins/{plugin_name}/__init__.py')):
                    l.warning(f'[plugin] Invaild plugin {plugin_name}! it doesn\'t exist!')
                    continue

                perf = u.perf_counter()
                module = importlib.import_module(f'plugins.{plugin_name}')

                # 查找 & 初始化插件实例
                for attr in dir(module):
                    obj = getattr(module, attr)
                    if isinstance(obj, Plugin) and obj.name == plugin_name:
                        obj.init()
                        # self._register_routes(obj)
                        self.plugins_loaded.append(obj)
                        l.debug(f'[plugin] init plugin {plugin_name} took {perf()}ms')
                        break
                else:
                    l.warning(f'[plugin] Invaild plugin {plugin_name}! it doesn\'t have a plugin instance!')

            except VersionNotMatchException as e:
                l.warning(f'[plugin] {e}')
            except Exception as e:
                l.warning(f'[plugin] Error when loading plugin {plugin_name}: {e}\n{format_exc()}')

        loaded_count = len(self.plugins_loaded)
        loaded_names = ", ".join([n.name for n in self.plugins_loaded])
        l.info(f'{loaded_count} plugin{"s" if loaded_count > 1 else ""} enabled: {loaded_names}' if loaded_count > 0 else f'No plugins enabled.')

    def _register_route(self, rule: str, endpoint: str, view_func: t.Callable, options: dict[str, t.Any]):
        '''
        注册路由
        '''
        self.app.add_url_rule(
            rule,
            endpoint=endpoint,
            view_func=view_func,
            **options
        )
        l.debug(f'Registered Route: {rule} -> {endpoint}')

    def trigger_event(self, event):
        '''
        触发事件

        :param event: 事件实例 (不可只使用 id)
        '''
        for e in self.events[event.id]:
            try:
                event = e(event=event, request=event.request)
                if event.intercepted:
                    break
            except Exception as err:
                l.warning(f'[plugin] Error when trigging event {event.id} with function {e}: {err}\n{format_exc()}')
        return event

# endregion plugin-init
