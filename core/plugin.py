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
插件系统

core 是空壳: 所有业务功能都是插件。区别只在于分发方式 ——

- `builtin/`  内置插件, 随仓库分发、受 git 跟踪, `git clone` 下来就能跑
- `plugins/`  用户自行安装的插件, 不受 git 跟踪

同名时 `plugins/` 覆盖 `builtin/`, 用户因此可以用自己的实现替换任一内置功能,
而不需要任何在线 registry。v6 那套「启动时从第三方站点下载 zip 并 exec_module」
的安装机制不再存在。
'''

import argparse
import importlib.util
import inspect
import os
import sys
import typing as t
from dataclasses import dataclass, field

from fastapi import APIRouter, FastAPI, Request, Response
from loguru import logger as l
from packaging.specifiers import SpecifierSet
from packaging.version import Version, InvalidVersion
from pydantic import BaseModel as PydanticBaseModel
from pyproject_parser import PyProject
from sqlmodel import SQLModel

from core import db
from core import utils as u
from core.broadcast import manager
from core.config import config as global_config
from core.events import bus, BaseEvent, EventLike

MODULE_NAMESPACE = 'sleepy_plugin'
'''动态加载插件时使用的模块名前缀'''


@dataclass
class PluginMetadata:
    '''插件元数据 (来自插件的 pyproject.toml)'''
    name: str
    version: str
    description: str = ''
    author: str = ''
    enabled: bool = True
    dependencies: t.Dict[str, str] = field(default_factory=dict)
    '''依赖: `{"插件名": "版本约束"}`, 无约束时值为 `*`'''
    source: str = 'builtin'
    '''来源目录: `builtin` 或 `external`'''


class PluginRoute:
    '''插件路由包装器'''

    def __init__(self, path: str, endpoint: t.Callable, methods: list[str], override: bool = False, **kwargs):
        self.path = path
        self.endpoint = endpoint
        self.methods = methods
        self.override = override
        self.kwargs = kwargs


class PluginMount:
    '''插件挂载包装器 (StaticFiles 或其他 ASGI App)'''

    def __init__(self, path: str, app: t.Any, name: str | None = None):
        self.path = path
        self.app = app
        self.name = name


@dataclass
class CliArgument:
    args: t.List[str]
    kwargs: t.Dict[str, t.Any]


@dataclass
class CliCommand:
    name: str
    handler: t.Callable[[argparse.Namespace], t.Any]
    help: str
    arguments: t.List[CliArgument] = field(default_factory=list)


class PluginBase:
    '''
    插件基类
    '''

    def __init__(self, metadata: PluginMetadata):
        self.metadata = metadata
        self.router: t.Optional[APIRouter] = None
        self.exports: t.Dict[str, t.Any] = {}
        '''
        对外暴露的 API

        其他插件通过 `plugin_manager.api('device')['set_device']` 取用。
        这样插件之间不必互相 import —— 动态加载的模块没有稳定的 import 路径。
        '''

        self._routes: t.List[PluginRoute] = []
        self._mounts: t.List[PluginMount] = []
        self._cli_commands: t.List[CliCommand] = []
        self._config_schema: t.Optional[type[PydanticBaseModel]] = None
        self._config_instance: t.Optional[PydanticBaseModel] = None

    # region routes

    def add_route(
        self,
        path: str,
        endpoint: t.Callable,
        methods: t.List[str] | None = None,
        override: bool = False,
        **kwargs
    ):
        '''
        添加路由

        :param path: 完整路径 (不加插件前缀)
        :param endpoint: 处理函数
        :param methods: HTTP 方法, 默认 `['GET']`
        :param override: 是否覆盖已存在的同路径路由
        '''
        route = PluginRoute(path=path, endpoint=endpoint, methods=methods or ['GET'], override=override, **kwargs)
        self._routes.append(route)
        l.debug(f'Plugin {self.metadata.name} registered route: {path} {route.methods} (override={override})')

    def mount(self, path: str, app: t.Any, name: str | None = None):
        '''
        挂载 ASGI 应用 (如 StaticFiles) 到指定路径
        '''
        self._mounts.append(PluginMount(path=path, app=app, name=name))
        l.debug(f'Plugin {self.metadata.name} registered mount: {path}')

    def get_routes(self, override_only: bool = False) -> t.List[PluginRoute]:
        if override_only:
            return [r for r in self._routes if r.override]
        return self._routes

    def get_mounts(self) -> t.List[PluginMount]:
        return self._mounts

    # endregion routes

    # region data

    def register_model(self, model: type[SQLModel]) -> type[SQLModel]:
        '''
        声明本插件使用的数据表

        建表发生在所有插件加载完成之后, 因此在 `__init__` 或 `on_load` 里调用都可以。
        '''
        return db.register_model(model, self.metadata.name)

    def register_config(self, schema_class: type[PydanticBaseModel]) -> None:
        '''
        注册插件配置 Schema

        应在 `__init__` 中调用。配置项写在 `plugin.<插件目录名>` 下,
        由 PluginManager 在 `on_load` 结束后解析并校验。
        '''
        self._config_schema = schema_class
        l.debug(f'Plugin {self.metadata.name} registered config schema: {schema_class.__name__}')

    def get_config(self) -> PydanticBaseModel:
        '''
        获取已校验的插件配置

        需先 `register_config()`, 且只能在 `on_load()` 完成之后使用。
        '''
        if self._config_schema is None:
            raise RuntimeError(
                f'Plugin {self.metadata.name} has not registered a config schema. '
                'Call register_config() in __init__ first.'
            )
        if self._config_instance is None:
            raise RuntimeError(
                f'Plugin {self.metadata.name} config has not been resolved yet. '
                'Config is available after on_load() completes.'
            )
        return self._config_instance

    # endregion data

    # region events

    def subscribe(self, event: EventLike, handler: t.Callable):
        '''
        订阅事件 (插件卸载时自动反注册)
        '''
        bus.subscribe(event, handler, plugin=self.metadata.name)

    async def emit(self, event: BaseEvent) -> BaseEvent:
        '''
        触发事件
        '''
        return await bus.emit(event)

    async def broadcast(self, event: str, data: dict | None = None):
        '''
        向所有 SSE / WebSocket 连接推送
        '''
        await manager.broadcast(event, data)

    def register_snapshot_provider(self, provider: t.Callable[[], t.Dict[str, t.Any]]):
        '''
        注册快照提供者 (新连接接入时下发的初始数据)
        '''
        manager.register_snapshot_provider(provider, plugin=self.metadata.name)

    # endregion events

    # region cli

    def add_cli_command(
        self,
        command: str,
        handler: t.Callable[[argparse.Namespace], t.Any],
        help: str = '',
        arguments: t.List[tuple[t.List[str], t.Dict[str, t.Any]]] | None = None
    ):
        '''
        注册一个 CLI 子命令
        '''
        cmd_args = [CliArgument(args=names, kwargs=opts) for names, opts in (arguments or [])]
        self._cli_commands.append(CliCommand(name=command, handler=handler, help=help, arguments=cmd_args))
        l.debug(f'Plugin {self.metadata.name} registered CLI command: {command}')

    def get_cli_commands(self) -> t.List[CliCommand]:
        return self._cli_commands

    # endregion cli

    # region hooks

    def on_load(self):
        '''插件加载时调用 (同步, 无 event loop)'''

    def on_unload(self):
        '''插件卸载时调用'''

    def on_register_cli(self, subparsers: argparse._SubParsersAction):
        '''注册 CLI 子命令时调用'''

    async def on_startup(self):
        '''应用启动时调用 (异步, 有 event loop)'''

    async def on_shutdown(self):
        '''应用关闭时调用'''

    def setup_routes(self, app: FastAPI):
        '''直接操作 app 注册路由 (推荐优先使用 add_route)'''

    def modify_response(self, request: Request, response: Response, endpoint: str) -> Response:
        '''修改响应'''
        return response

    # endregion hooks


class PluginManager:
    '''
    插件管理器
    '''

    def __init__(self):
        self.builtin_dir = u.get_path(global_config.plugins.builtin_dir, is_dir=True)
        self.external_dir = u.get_path(global_config.plugins.external_dir, is_dir=True)
        self.plugins: t.Dict[str, PluginBase] = {}
        self.metadata: t.Dict[str, PluginMetadata] = {}
        self._app: t.Optional[FastAPI] = None
        self._response_modifiers: t.List[tuple[str, t.Callable]] = []
        self._overridden_routes: t.Dict[str, str] = {}
        self._plugin_routes: t.Dict[str, t.List[t.Any]] = {}
        '''插件名 -> 它注册进 app.routes 的路由对象, 卸载时据此移除'''

    # region discovery

    def discover_plugins(self) -> t.Dict[str, tuple[str, str]]:
        '''
        发现插件

        :return: `{插件目录名: (插件目录绝对路径, 来源)}`
            同名时 `plugins/` 覆盖 `builtin/`
        '''
        found: t.Dict[str, tuple[str, str]] = {}
        for base_dir, source in ((self.builtin_dir, 'builtin'), (self.external_dir, 'external')):
            if not os.path.exists(base_dir):
                continue
            for item in sorted(os.listdir(base_dir)):
                plugin_path = os.path.join(base_dir, item)
                if not os.path.isdir(plugin_path):
                    continue
                if not os.path.exists(os.path.join(plugin_path, 'pyproject.toml')):
                    continue
                if not os.path.exists(os.path.join(plugin_path, '__init__.py')):
                    continue
                if item in found and source == 'external':
                    l.info(f'Plugin {item} from plugins/ overrides the builtin one')
                found[item] = (plugin_path, source)
        return found

    def load_metadata(self, plugin_name: str, plugin_path: str, source: str) -> t.Optional[PluginMetadata]:
        '''
        解析插件的 pyproject.toml
        '''
        pyproject_path = os.path.join(plugin_path, 'pyproject.toml')
        try:
            pyproject = PyProject.load(pyproject_path)
            project = pyproject.project
            if project is None:
                l.error(f'Plugin {plugin_name}: missing [project] table')
                return None

            tool_sleepy = pyproject.tool.get('sleepy', {}) if pyproject.tool else {}
            authors = project.get('authors')

            raw_deps = tool_sleepy.get('dependencies', [])
            normalized_deps: t.Dict[str, str] = {}
            if isinstance(raw_deps, list):
                # 兼容旧格式 ["plugin_a", "plugin_b"]
                normalized_deps = {dep: '*' for dep in raw_deps if isinstance(dep, str)}
            elif isinstance(raw_deps, dict):
                normalized_deps = {k: str(v) for k, v in raw_deps.items()}

            return PluginMetadata(
                name=plugin_name,
                version=str(project.get('version') or '0.0.0'),
                description=project.get('description') or '',
                author=(authors[0].get('name') or '') if authors else '',
                enabled=tool_sleepy.get('enabled', True),
                dependencies=normalized_deps,
                source=source
            )
        except Exception as ex:
            l.error(f'Failed to parse pyproject.toml for {plugin_name}: {ex}')
            return None

    # endregion discovery

    # region loading

    def _check_dependencies_met(self, plugin_name: str, dependencies: t.Dict[str, str]) -> bool:
        for dep_name, spec_str in dependencies.items():
            if dep_name not in self.plugins:
                l.debug(f'Plugin {plugin_name} missing dependency: {dep_name}')
                return False
            if spec_str == '*':
                continue
            target_version_str = self.plugins[dep_name].metadata.version
            try:
                if not SpecifierSet(spec_str).contains(Version(target_version_str)):
                    l.error(f'Plugin {plugin_name} requires {dep_name} {spec_str}, but found {target_version_str}')
                    return False
            except InvalidVersion:
                l.warning(f'Cannot parse version for dependency check: {dep_name}={target_version_str}')
                return False
        return True

    def _resolve_plugin_config(self, plugin: PluginBase, plugin_name: str):
        '''
        解析并校验插件配置
        '''
        if plugin._config_schema is None:
            return

        plugin_configs: t.Dict[str, t.Any] = getattr(global_config, 'plugin', {}) or {}
        file_config: t.Dict[str, t.Any] = plugin_configs.get(plugin_name) or {}

        # 环境变量: SLEEPY_PLUGIN_<PLUGIN_ID>_<KEY>
        # 直接扫描环境变量而不是走 config.plugin, 因为三段及以上的插件名
        # 经 process_env_split 嵌套后会落在错误的中间键上。
        env_prefix = f'SLEEPY_PLUGIN_{plugin_name.replace("-", "_").upper()}_'
        env_config: t.Dict[str, t.Any] = {}
        for k, v in os.environ.items():
            k_upper = k.upper()
            if k_upper.startswith(env_prefix):
                remaining = k_upper[len(env_prefix):].lower()
                env_config = u.deep_merge_dict(env_config, u.process_env_split(remaining.split('_'), v))

        raw_config = u.deep_merge_dict(file_config, env_config)
        try:
            plugin._config_instance = plugin._config_schema(**raw_config)
            l.debug(f'Plugin {plugin_name} config resolved')
        except Exception as ex:
            l.error(f'Plugin {plugin_name} config validation failed: {ex}. Falling back to defaults.')
            try:
                plugin._config_instance = plugin._config_schema()
            except Exception as ex2:
                l.error(f'Plugin {plugin_name} failed to create default config: {ex2}')

    def load_plugin(self, plugin_name: str, plugin_path: str, source: str) -> bool:
        '''
        加载单个插件
        '''
        metadata = self.load_metadata(plugin_name, plugin_path, source)
        if not metadata:
            return False
        if not metadata.enabled:
            l.info(f'Plugin {plugin_name} is disabled in its pyproject.toml, skipping')
            return False
        if plugin_name in global_config.plugins.disabled:
            l.info(f'Plugin {plugin_name} is disabled by config, skipping')
            return False
        if not self._check_dependencies_met(plugin_name, metadata.dependencies):
            l.error(f'Plugin {plugin_name} cannot be loaded due to missing or incompatible dependencies')
            return False

        module_name = f'{MODULE_NAMESPACE}.{plugin_name}'
        init_file = os.path.join(plugin_path, '__init__.py')
        try:
            spec = importlib.util.spec_from_file_location(module_name, init_file)
            if not spec or not spec.loader:
                l.error(f'Failed to create module spec for plugin {plugin_name}')
                return False
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            if not hasattr(module, 'Plugin'):
                l.error(f'Plugin {plugin_name} does not define a Plugin class')
                return False
            plugin_instance = getattr(module, 'Plugin')(metadata)
            if not isinstance(plugin_instance, PluginBase):
                l.error(f'Plugin {plugin_name}: Plugin class must inherit from PluginBase')
                return False

            plugin_instance.on_load()
            self._resolve_plugin_config(plugin_instance, plugin_name)
            self.plugins[plugin_name] = plugin_instance
            self.metadata[plugin_name] = metadata

            # 只有真正覆盖了 modify_response 的插件才进入响应链;
            # v6 用 hasattr 判断, 而基类总是定义了该方法, 于是每个插件都被挂上一个空修改器。
            if type(plugin_instance).modify_response is not PluginBase.modify_response:
                self._response_modifiers.append((plugin_name, plugin_instance.modify_response))

            l.info(f'Plugin loaded: {plugin_name} v{metadata.version} ({source})')
            return True
        except Exception as ex:
            l.error(f'Failed to load plugin {plugin_name}: {ex}')
            sys.modules.pop(module_name, None)
            return False

    def load_all_plugins(self):
        '''
        按依赖拓扑序加载全部插件
        '''
        discovered = self.discover_plugins()
        if not discovered:
            l.info('No plugins found')
            return

        l.info(f'Found {len(discovered)} plugin(s): {", ".join(sorted(discovered))}')

        metas: t.Dict[str, PluginMetadata] = {}
        for name, (path, source) in discovered.items():
            meta = self.load_metadata(name, path, source)
            if meta:
                metas[name] = meta

        remaining = set(metas.keys())
        loaded: set[str] = set()

        while remaining:
            progress = False
            for name in sorted(remaining):
                deps = metas[name].dependencies.keys()
                # 只等待「存在且会被加载」的依赖, 依赖本身缺失时不再空转
                pending = [d for d in deps if d in remaining and d != name]
                if pending:
                    continue
                path, source = discovered[name]
                if self.load_plugin(name, path, source):
                    loaded.add(name)
                remaining.discard(name)
                progress = True
            if not progress:
                l.error(f'Cannot load plugins due to dependency cycles: {", ".join(sorted(remaining))}')
                break

    # endregion loading

    # region lifecycle

    async def startup_events(self):
        for name, plugin in self.plugins.items():
            try:
                await plugin.on_startup()
            except Exception as ex:
                l.error(f'Plugin {name} startup error: {ex}')

    async def shutdown_events(self):
        for name, plugin in self.plugins.items():
            try:
                await plugin.on_shutdown()
            except Exception as ex:
                l.error(f'Plugin {name} shutdown error: {ex}')

    def unload_plugin(self, plugin_name: str) -> bool:
        '''
        卸载插件

        与 v6 不同, 这里会把插件注册的路由一并从 `app.routes` 移除 ——
        v6 只清了 modifier 和 sys.modules, 卸载后请求仍会打到已删模块的函数上。
        '''
        if plugin_name not in self.plugins:
            l.warning(f'Plugin {plugin_name} is not loaded')
            return False
        try:
            plugin = self.plugins[plugin_name]
            plugin.on_unload()

            if self._app is not None:
                removed = 0
                for route in self._plugin_routes.get(plugin_name, []):
                    if route in self._app.routes:
                        self._app.routes.remove(route)
                        removed += 1
                        l.debug(f'Removed route {getattr(route, "path", route)} of plugin {plugin_name}')
                if removed:
                    self._mark_routes_changed(self._app)
            self._plugin_routes.pop(plugin_name, None)

            bus.unsubscribe_plugin(plugin_name)
            manager.unregister_plugin(plugin_name)

            self._response_modifiers = [(n, f) for n, f in self._response_modifiers if n != plugin_name]
            self._overridden_routes = {k: v for k, v in self._overridden_routes.items() if v != plugin_name}

            del self.plugins[plugin_name]
            del self.metadata[plugin_name]
            sys.modules.pop(f'{MODULE_NAMESPACE}.{plugin_name}', None)
            l.info(f'Plugin unloaded: {plugin_name}')
            return True
        except Exception as ex:
            l.error(f'Failed to unload plugin {plugin_name}: {ex}')
            return False

    # endregion lifecycle

    # region routes

    @staticmethod
    def _iter_routes(routes: list) -> t.Iterator[tuple[list, t.Any]]:
        '''
        递归遍历路由, 产出 `(所属列表, 路由对象)`

        新版 FastAPI 的 `include_router()` 不再把子路由展平进 `app.routes`,
        而是插入一个 `_IncludedRouter` 代理。只看顶层的话会漏掉所有通过
        router 注册的路由。
        '''
        for route in list(routes):
            inner = getattr(route, 'original_router', None)
            if inner is not None:
                yield from PluginManager._iter_routes(inner.routes)
            else:
                yield routes, route

    @staticmethod
    def _mark_routes_changed(app: FastAPI):
        '''
        使 FastAPI 的路由匹配缓存失效

        直接改动 `routes` 列表不会自增 `_routes_version`, `_IncludedRouter`
        会继续用旧的候选集。
        '''
        for router in (getattr(app, 'router', None), *(
            getattr(r, 'original_router', None) for r in app.routes
        )):
            mark = getattr(router, '_mark_routes_changed', None)
            if callable(mark):
                mark()
        app.openapi_schema = None

    def _remove_existing_route(self, app: FastAPI, path: str, methods: t.List[str]):
        removed = 0
        for owner, route in self._iter_routes(app.routes):
            if getattr(route, 'path', None) != path:
                continue
            if not any(m in (getattr(route, 'methods', None) or set()) for m in methods):
                continue
            owner.remove(route)
            removed += 1
            l.info(f'Removed existing route: {path} {getattr(route, "methods", [])}')
        if removed:
            self._mark_routes_changed(app)

    def _add_plugin_route(self, app: FastAPI, plugin_name: str, route: PluginRoute):
        if route.override:
            self._remove_existing_route(app, route.path, route.methods)
            for method in route.methods:
                self._overridden_routes[f'{route.path}:{method}'] = plugin_name
            l.info(f'Plugin {plugin_name} overriding route: {route.path} {route.methods}')

        before = len(app.routes)
        app.add_api_route(route.path, route.endpoint, methods=route.methods, **route.kwargs)
        self._plugin_routes.setdefault(plugin_name, []).extend(app.routes[before:])
        l.debug(f'Added plugin route: {route.path} {route.methods}')

    def setup_plugin_routes(self, app: FastAPI):
        '''
        注册全部插件的路由与挂载
        '''
        self._app = app

        for plugin_name, plugin in self.plugins.items():
            try:
                if plugin.router:
                    before = len(app.routes)
                    app.include_router(
                        plugin.router,
                        prefix=f'/api/plugin/{plugin_name}',
                        tags=[f'plugin:{plugin_name}']
                    )
                    self._plugin_routes.setdefault(plugin_name, []).extend(app.routes[before:])
                    l.info(f'Registered router for plugin {plugin_name} at /api/plugin/{plugin_name}')

                for mount in plugin.get_mounts():
                    app.mount(path=mount.path, app=mount.app, name=mount.name)
                    l.info(f'Plugin {plugin_name} mounted app at {mount.path}')

                plugin.setup_routes(app)

                for route in plugin.get_routes():
                    if not route.override:
                        self._add_plugin_route(app, plugin_name, route)
            except Exception as ex:
                l.error(f'Failed to setup routes for plugin {plugin_name}: {ex}')

        # 覆盖型路由最后处理, 确保它们能盖住前面所有注册
        for plugin_name, plugin in self.plugins.items():
            try:
                for route in plugin.get_routes(override_only=True):
                    self._add_plugin_route(app, plugin_name, route)
            except Exception as ex:
                l.error(f'Failed to setup override routes for plugin {plugin_name}: {ex}')

    def apply_response_modifiers(self, request: Request, response: Response, endpoint: str) -> Response:
        modified = response
        for plugin_name, modifier in self._response_modifiers:
            try:
                modified = modifier(request, modified, endpoint)
            except Exception as ex:
                l.error(f'Plugin {plugin_name} response modifier failed: {ex}')
        return modified

    # endregion routes

    # region api

    def get_plugin(self, plugin_name: str) -> t.Optional[PluginBase]:
        return self.plugins.get(plugin_name)

    def api(self, plugin_name: str) -> t.Dict[str, t.Any]:
        '''
        获取插件对外暴露的 API

        ```python
        device_api = plugin_manager.api('device')
        device_api['set_device'](sess, id='pc-1', ...)
        ```

        插件未加载时返回空字典 —— 调用方应当检查, 以便在依赖插件被禁用时优雅降级。
        '''
        plugin = self.plugins.get(plugin_name)
        if not plugin:
            l.warning(f'Plugin {plugin_name} is not loaded, returning empty API')
            return {}
        return plugin.exports

    def get_loaded_plugins(self) -> t.List[str]:
        return list(self.plugins.keys())

    def get_plugin_info(self, plugin_name: str) -> t.Optional[t.Dict[str, t.Any]]:
        if plugin_name not in self.metadata:
            return None
        meta = self.metadata[plugin_name]
        return {
            'name': meta.name,
            'version': meta.version,
            'description': meta.description,
            'author': meta.author,
            'enabled': meta.enabled,
            'source': meta.source,
            'dependencies': meta.dependencies
        }

    def get_overridden_routes(self) -> t.Dict[str, str]:
        return self._overridden_routes.copy()

    # endregion api

    # region cli

    def setup_cli_commands(self, parser: argparse.ArgumentParser):
        '''
        为所有已加载插件注册 CLI 子命令
        '''
        if not self.plugins:
            return
        subparsers = parser.add_subparsers(dest='command', help='Plugin commands')
        for plugin_name, plugin in self.plugins.items():
            try:
                plugin.on_register_cli(subparsers)
                for cmd in plugin.get_cli_commands():
                    sub = subparsers.add_parser(cmd.name, help=cmd.help)
                    for arg in cmd.arguments:
                        sub.add_argument(*arg.args, **arg.kwargs)
                    sub.set_defaults(func=cmd.handler)
            except Exception as ex:
                l.error(f'Plugin {plugin_name} failed to register CLI commands: {ex}')

    @staticmethod
    def run_cli_handler(handler: t.Callable, args: argparse.Namespace):
        '''
        执行 CLI handler (同步或异步均可)
        '''
        import asyncio
        if inspect.iscoroutinefunction(handler):
            return asyncio.run(handler(args))
        return handler(args)

    # endregion cli


plugin_manager = PluginManager()
'''
全局插件管理器
'''
