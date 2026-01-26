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

import os
import sys
import importlib.util
from typing import Dict, List, Callable, Any, Optional, Union
from dataclasses import dataclass, field

from loguru import logger as l
from fastapi import FastAPI, APIRouter, Response, Request
from pyproject_parser import PyProject
from packaging.specifiers import SpecifierSet
from packaging.version import Version, InvalidVersion
import argparse
import asyncio
import inspect

import utils as u


@dataclass
class PluginMetadata:
    """插件元数据"""
    name: str
    version: str
    description: str = ""
    author: str = ""
    enabled: bool = True
    # 变更: 依赖统一存储为字典 { "plugin_name": "version_spec" }
    # 如果没有版本限制，值为 "*"
    dependencies: Dict[str, str] = field(default_factory=dict)


class PluginRoute:
    """插件路由包装器"""
    def __init__(self, path: str, endpoint: Callable, methods: List[str], override: bool = False, **kwargs):
        self.path = path
        self.endpoint = endpoint
        self.methods = methods
        self.override = override
        self.kwargs = kwargs


class PluginMount:
    """插件挂载包装器 (用于 StaticFiles 或其他 ASGI App)"""

    def __init__(self, path: str, app: Any, name: str | None = None):
        self.path = path
        self.app = app
        self.name = name

@dataclass
class CliArgument:
    args: List[str]          # 例如 ["--name", "-n"]
    kwargs: Dict[str, Any]   # 例如 {"help": "姓名", "type": str}

@dataclass
class CliCommand:
    name: str
    handler: Callable[[argparse.Namespace], Any]
    help: str
    arguments: List[CliArgument] = field(default_factory=list)

class PluginBase:
    """插件基类"""

    def __init__(self, metadata: PluginMetadata):
        self.metadata = metadata
        self.router: Optional[APIRouter] = None
        self._routes: List[PluginRoute] = []
        self._mounts: List[PluginMount] = []
        self._cli_commands: List[CliCommand] = [] 

    def add_route(
        self,
        path: str,
        endpoint: Callable,
        methods: List[str] | None = None,
        override: bool = False,
        **kwargs
    ):
        """
        添加路由到插件
        """
        if methods is None:
            methods = ["GET"]
        route = PluginRoute(path=path, endpoint=endpoint, methods=methods, override=override, **kwargs)
        self._routes.append(route)
        l.debug(f'Plugin {self.metadata.name} registered route: {path} {methods} (override={override})')

    def mount(self, path: str, app: Any, name: str | None = None):
        """
        挂载 ASGI 应用 (如 StaticFiles) 到指定路径

        :param path: 挂载路径 (例如 "/static")
        :param app: ASGI 应用实例 (例如 StaticFiles(directory="dist"))
        :param name: 挂载名称
        """
        mount = PluginMount(path=path, app=app, name=name)
        self._mounts.append(mount)
        l.debug(f'Plugin {self.metadata.name} registered mount: {path} -> {name}')

    def get_routes(self, override_only: bool = False) -> List[PluginRoute]:
        """获取插件的路由列表"""
        if override_only:
            return [r for r in self._routes if r.override]
        return self._routes

    def get_mounts(self) -> List[PluginMount]:
        """获取插件的挂载列表"""
        return self._mounts
    
    def add_cli_command(
        self,
        command: str,
        handler: Callable[[argparse.Namespace], Any],
        help: str = "",
        arguments: List[tuple[List[str], Dict[str, Any]]] | None = None
    ):
        """
        注册一个 CLI 子命令
        :param command: 命令名称 (例如 "sync")
        :param handler: 处理函数，接收 argparse.Namespace 参数
        :param help: 帮助信息
        :param arguments: 参数列表，每个元素为 (args_list, kwargs_dict)
                          例如: ([['--force'], {'action': 'store_true'}])
        """
        cmd_args = []
        if arguments:
            for arg_names, arg_opts in arguments:
                cmd_args.append(CliArgument(args=arg_names, kwargs=arg_opts))
        
        self._cli_commands.append(CliCommand(
            name=command,
            handler=handler,
            help=help,
            arguments=cmd_args
        ))
        l.debug(f'Plugin {self.metadata.name} registered CLI command: {command}')

    def get_cli_commands(self) -> List[CliCommand]:
        return self._cli_commands

    def on_load(self):
        """插件加载时调用"""
        pass

    def on_unload(self):
        """插件卸载时调用"""
        pass

    def setup_routes(self, app: FastAPI):
        """设置路由（推荐使用 add_route 方法）"""
        pass

    def modify_response(self, request: Request, response: Response, endpoint: str) -> Response:
        """修改响应"""
        return response


class PluginManager:
    """插件管理器"""

    def __init__(self, plugin_dir: str = 'plugins'):
        self.plugin_dir = u.get_path(plugin_dir, is_dir=True)
        self.plugins: Dict[str, PluginBase] = {}
        self.metadata: Dict[str, PluginMetadata] = {}
        self._response_modifiers: List[tuple[str, Callable]] = []
        self._overridden_routes: Dict[str, str] = {}  # path:method -> plugin_name

    def discover_plugins(self) -> List[str]:
        plugin_names = []
        if not os.path.exists(self.plugin_dir):
            l.warning(f'Plugin directory not found: {self.plugin_dir}')
            return plugin_names
        for item in os.listdir(self.plugin_dir):
            plugin_path = os.path.join(self.plugin_dir, item)
            if os.path.isdir(plugin_path):
                metadata_file = os.path.join(plugin_path, 'pyproject.toml')
                init_file = os.path.join(plugin_path, '__init__.py')
                if os.path.exists(metadata_file) and os.path.exists(init_file):
                    plugin_names.append(item)
                    l.debug(f'Discovered plugin: {item}')
                else:
                    l.debug(f'Skipping {item}: missing pyproject.toml or __init__.py')
        return plugin_names

    def load_metadata(self, plugin_name: str) -> Optional[PluginMetadata]:
        pyproject_path = os.path.join(self.plugin_dir, plugin_name, "pyproject.toml")
        if not os.path.exists(pyproject_path):
            l.error(f"Missing pyproject.toml for plugin {plugin_name}")
            return None
        try:
            pyproject = PyProject.load(pyproject_path)
            project = pyproject.project
            if project is None:
                l.error("Missing [project] table")
                return None
            
            tool_sleepy = pyproject.tool.get("sleepy", {}) if pyproject.tool else {}
            authors = project.get('authors')
            
            raw_deps = tool_sleepy.get("dependencies", [])
            normalized_deps: Dict[str, str] = {}

            if isinstance(raw_deps, list):
                # 兼容旧格式: ["plugin_a", "plugin_b"] -> {"plugin_a": "*", "plugin_b": "*"}
                for dep in raw_deps:
                    if isinstance(dep, str):
                        normalized_deps[dep] = "*"
            elif isinstance(raw_deps, dict):
                # 新格式: { "plugin_a": ">=1.0.0" }
                normalized_deps = {k: str(v) for k, v in raw_deps.items()}

            return PluginMetadata(
                name=project.get('name') or plugin_name,
                version=str(project.get('version')) or "0.0.0",
                description=project.get('description') or "",
                author=authors[0].get('name') or "" if authors else "",
                enabled=tool_sleepy.get("enabled", True),
                dependencies=normalized_deps
            )
        except Exception as e:
            l.error(f'Failed to parse pyproject.toml for {plugin_name}: {e}')
            return None

    def _check_dependencies_met(self, plugin_name: str, dependencies: Dict[str, str]) -> bool:
        """检查依赖是否存在且版本符合要求"""
        for dep_name, spec_str in dependencies.items():
            # 1. 检查依赖是否已加载
            if dep_name not in self.plugins:
                l.debug(f'Plugin {plugin_name} missing dependency: {dep_name}')
                return False
            
            # 2. 检查版本
            if spec_str == "*":
                continue

            target_plugin = self.plugins[dep_name]
            target_version_str = target_plugin.metadata.version
            
            try:
                target_version = Version(target_version_str)
                spec = SpecifierSet(spec_str)
                
                if not spec.contains(target_version):
                    l.error(f'Plugin {plugin_name} requires {dep_name} {spec_str}, but found {target_version_str}')
                    return False
            except InvalidVersion:
                l.warning(f'Could not parse version for dependency check: {dep_name}={target_version_str} (req: {spec_str})')
                return False

        return True

    def load_plugin(self, plugin_name: str) -> bool:
        metadata = self.load_metadata(plugin_name)
        if not metadata: return False
        if not metadata.enabled:
            l.info(f'Plugin {plugin_name} is disabled, skipping')
            return False

        # 在加载时进行最终依赖检查
        if not self._check_dependencies_met(plugin_name, metadata.dependencies):
             l.error(f'Plugin {plugin_name} cannot be loaded due to missing or incompatible dependencies')
             return False

        plugin_path = os.path.join(self.plugin_dir, plugin_name)
        init_file = os.path.join(plugin_path, '__init__.py')
        try:
            spec = importlib.util.spec_from_file_location(f'plugins.{plugin_name}', init_file)
            if not spec or not spec.loader:
                l.error(f'Failed to load spec for plugin {plugin_name}')
                return False
            module = importlib.util.module_from_spec(spec)
            sys.modules[f'plugins.{plugin_name}'] = module
            spec.loader.exec_module(module)
            if not hasattr(module, 'Plugin'):
                l.error(f'Plugin {plugin_name} does not have a Plugin class')
                return False
            PluginClass = getattr(module, 'Plugin')
            plugin_instance = PluginClass(metadata)
            if not isinstance(plugin_instance, PluginBase):
                l.error(f'Plugin {plugin_name} Plugin class must inherit from PluginBase')
                return False
            plugin_instance.on_load()
            self.plugins[plugin_name] = plugin_instance
            self.metadata[plugin_name] = metadata
            if hasattr(plugin_instance, 'modify_response'):
                self._response_modifiers.append((plugin_name, plugin_instance.modify_response))
            l.info(f'Plugin loaded: {plugin_name} v{metadata.version}')
            return True
        except Exception as e:
            l.error(f'Failed to load plugin {plugin_name}: {e}')
            return False

    def load_all_plugins(self):
        plugin_names = self.discover_plugins()
        if not plugin_names:
            l.info('No plugins found')
            return
        
        l.info(f'Found {len(plugin_names)} plugin(s): {", ".join(plugin_names)}')
        
        loaded = set()
        remaining = set(plugin_names)
        
        # 拓扑排序加载
        while remaining:
            progress = False
            for plugin_name in list(remaining):
                metadata = self.load_metadata(plugin_name)
                if not metadata:
                    remaining.remove(plugin_name)
                    continue
                
                # 检查所有依赖是否已经存在于 'loaded' 集合中
                # 注意：这里我们只检查依赖的名称是否已加载，详细的版本检查在 load_plugin 内部进行
                # 这样可以确保如果 A 依赖 B>=2.0，而 B(1.0) 已加载，则 A 会尝试加载然后在 load_plugin 中报错失败
                deps_names = metadata.dependencies.keys()
                deps_ready = all(dep in loaded for dep in deps_names)
                
                if deps_ready:
                    if self.load_plugin(plugin_name):
                        loaded.add(plugin_name)
                    # 即使加载失败，也从 remaining 中移除，避免死循环
                    remaining.remove(plugin_name)
                    progress = True
            
            if not progress:
                l.error(f'Cannot load plugins due to unresolved dependencies or cycles: {remaining}')
                break

    def _remove_existing_route(self, app: FastAPI, path: str, methods: List[str]):
        """移除已存在的路由"""
        routes_to_remove = []
        for route in app.routes:
            if hasattr(route, 'path') and route.path == path:  # pyright: ignore[reportAttributeAccessIssue]
                if hasattr(route, 'methods'):
                    if any(method in route.methods for method in methods):  # pyright: ignore[reportAttributeAccessIssue]
                        routes_to_remove.append(route)
                        l.debug(f'Marking route for removal: {route.path} {route.methods}')  # pyright: ignore[reportAttributeAccessIssue]
        for route in routes_to_remove:
            app.routes.remove(route)
            l.info(f'Removed existing route: {route.path} {getattr(route, "methods", [])}')

    def _add_plugin_route(self, app: FastAPI, plugin_name: str, route: PluginRoute):
        """
        添加插件路由到应用

        :param app: FastAPI 应用实例
        :param plugin_name: 插件名称
        :param route: 插件路由对象
        """
        # 如果需要覆盖，先移除已存在的路由
        if route.override:
            self._remove_existing_route(app, route.path, route.methods)
            for method in route.methods:
                route_key = f'{route.path}:{method}'
                self._overridden_routes[route_key] = plugin_name
            l.info(f'Plugin {plugin_name} overriding route: {route.path} {route.methods}')

        for method in route.methods:
            app.add_api_route(
                route.path,
                route.endpoint,
                methods=[method],
                **route.kwargs
            )
        l.debug(f'Added plugin route: {route.path} {route.methods}')

    def setup_plugin_routes(self, app: FastAPI):
        """
        为所有插件设置路由和挂载
        """

        async def get_plugin_metadata_endpoint(plugin_id: str):
            """获取指定插件的元数据 (Name, Version, Description, Author)"""
            info = self.get_plugin_info(plugin_id)
            if not info:
                return Response(status_code=404, content="Plugin not found")
            return {
                "name": info["name"],
                "version": info["version"],
                "description": info["description"],
                "author": info["author"]
            }

        async def list_plugins_endpoint():
            """获取所有已加载插件的列表"""
            plugins_list = []
            for name in self.get_loaded_plugins():
                info = self.get_plugin_info(name)
                if info:
                    plugins_list.append(info)
            return plugins_list

        app.add_api_route(
            "/api/plugin/{plugin_id}/info",
            get_plugin_metadata_endpoint,
            methods=["GET"],
            tags=["System"]
        )
        l.info("Registered system route: /api/plugin/{plugin_id}/info")

        app.add_api_route(
            "/api/plugin/list",
            list_plugins_endpoint,
            methods=["GET"],
            tags=["System"]
        )
        l.info("Registered system route: /api/plugin/list")

        for plugin_name, plugin in self.plugins.items():
            try:
                if plugin.router:
                    app.include_router(
                        plugin.router,
                        prefix=f'/api/plugin/{plugin_name}',
                        tags=[f'plugin:{plugin_name}']
                    )
                    l.info(f'Registered router for plugin: {plugin_name} at /api/plugin/{plugin_name}')

                # 这允许插件挂载静态文件目录或其他 ASGI 应用
                for mount in plugin.get_mounts():
                    app.mount(path=mount.path, app=mount.app, name=mount.name)
                    l.info(f'Plugin {plugin_name} mounted app at {mount.path}')

                plugin.setup_routes(app)

                for route in plugin.get_routes(override_only=False):
                    if not route.override:
                        self._add_plugin_route(app, plugin_name, route)

            except Exception as e:
                l.error(f'Failed to setup routes/mounts for plugin {plugin_name}: {e}')

        for plugin_name, plugin in self.plugins.items():
            try:
                for route in plugin.get_routes(override_only=True):
                    self._add_plugin_route(app, plugin_name, route)

            except Exception as e:
                l.error(f'Failed to setup override routes for plugin {plugin_name}: {e}')

    def apply_response_modifiers(self, request: Request, response: Response, endpoint: str) -> Response:
        """应用所有插件的响应修改器"""
        modified_response = response
        for plugin_name, modifier in self._response_modifiers:
            try:
                modified_response = modifier(request, modified_response, endpoint)
            except Exception as e:
                l.error(f'Plugin {plugin_name} response modifier failed: {e}')
        return modified_response
    
    def setup_cli_commands(self, parser: argparse.ArgumentParser):
        """
        将所有插件的命令注册到 argparse
        结构: main.py <plugin_name> <command> [args]
        """
        if not self.plugins:
            return

        subparsers = parser.add_subparsers(dest='plugin_name', title='Plugin Commands')
        
        for name, plugin in self.plugins.items():
            commands = plugin.get_cli_commands()
            if not commands:
                continue
            
            # 创建插件级解析器 (例如: main.py example_plugin ...)
            plugin_parser = subparsers.add_parser(name, help=plugin.metadata.description)
            plugin_subparsers = plugin_parser.add_subparsers(dest='plugin_command', required=True)
            
            for cmd in commands:
                # 创建动作级解析器 (例如: main.py example_plugin sync ...)
                cmd_parser = plugin_subparsers.add_parser(cmd.name, help=cmd.help)
                for arg in cmd.arguments:
                    cmd_parser.add_argument(*arg.args, **arg.kwargs)
                
                # 绑定处理函数
                cmd_parser.set_defaults(func=cmd.handler)

    def unload_plugin(self, plugin_name: str) -> bool:
        """卸载插件"""
        if plugin_name not in self.plugins:
            l.warning(f'Plugin {plugin_name} is not loaded')
            return False
        try:
            plugin = self.plugins[plugin_name]
            plugin.on_unload()

            self._response_modifiers = [
                (name, modifier) for name, modifier in self._response_modifiers
                if name != plugin_name
            ]
            self._overridden_routes = {
                route_key: pname for route_key, pname in self._overridden_routes.items()
                if pname != plugin_name
            }

            del self.plugins[plugin_name]
            del self.metadata[plugin_name]
            if f'plugins.{plugin_name}' in sys.modules:
                del sys.modules[f'plugins.{plugin_name}']
            l.info(f'Plugin unloaded: {plugin_name}')
            return True
        except Exception as e:
            l.error(f'Failed to unload plugin {plugin_name}: {e}')
            return False

    def get_plugin(self, plugin_name: str) -> Optional[PluginBase]:
        return self.plugins.get(plugin_name)

    def get_loaded_plugins(self) -> List[str]:
        return list(self.plugins.keys())

    def get_plugin_info(self, plugin_name: str) -> Optional[Dict[str, Any]]:
        if plugin_name not in self.metadata: return None
        meta = self.metadata[plugin_name]
        return {
            'name': meta.name,
            'version': meta.version,
            'description': meta.description,
            'author': meta.author,
            'enabled': meta.enabled,
            'dependencies': meta.dependencies
        }

    def get_overridden_routes(self) -> Dict[str, str]:
        return self._overridden_routes.copy()


plugin_manager = PluginManager()
