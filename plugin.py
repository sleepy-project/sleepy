# coding: utf-8

import os
import sys
import importlib.util
from pathlib import Path
from typing import Dict, List, Callable, Any, Optional
from dataclasses import dataclass
from loguru import logger as l
from fastapi import FastAPI, APIRouter, Response, Request
from toml import load as load_toml
import utils as u


@dataclass
class PluginMetadata:
    """插件元数据"""
    name: str
    version: str
    description: str = ""
    author: str = ""
    enabled: bool = True
    dependencies: List[str] = None
    
    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []


class PluginBase:
    """插件基类"""
    
    def __init__(self, metadata: PluginMetadata):
        self.metadata = metadata
        self.router: Optional[APIRouter] = None
    
    def on_load(self):
        """插件加载时调用"""
        pass
    
    def on_unload(self):
        """插件卸载时调用"""
        pass
    
    def setup_routes(self, app: FastAPI):
        """设置路由 - 可选实现"""
        pass
    
    def modify_response(self, request: Request, response: Response, endpoint: str) -> Response:
        """
        修改响应 - 可选实现
        
        :param request: 原始请求
        :param response: 原始响应
        :param endpoint: 端点路径
        :return: 修改后的响应
        """
        return response


class PluginManager:
    """插件管理器"""
    
    def __init__(self, plugin_dir: str = 'plugins'):
        self.plugin_dir = u.get_path(plugin_dir, is_dir=True)
        self.plugins: Dict[str, PluginBase] = {}
        self.metadata: Dict[str, PluginMetadata] = {}
        self._response_modifiers: List[tuple[str, Callable]] = []
    
    def discover_plugins(self) -> List[str]:
        """
        发现插件目录下的所有插件
        
        :return: 插件名称列表
        """
        plugin_names = []
        
        if not os.path.exists(self.plugin_dir):
            l.warning(f'Plugin directory not found: {self.plugin_dir}')
            return plugin_names
        
        for item in os.listdir(self.plugin_dir):
            plugin_path = os.path.join(self.plugin_dir, item)
            
            # 检查是否为目录且包含 .sleepymetadata 文件
            if os.path.isdir(plugin_path):
                metadata_file = os.path.join(plugin_path, '.sleepymetadata')
                init_file = os.path.join(plugin_path, '__init__.py')
                
                if os.path.exists(metadata_file) and os.path.exists(init_file):
                    plugin_names.append(item)
                    l.debug(f'Discovered plugin: {item}')
                else:
                    l.debug(f'Skipping {item}: missing .sleepymetadata or __init__.py')
        
        return plugin_names
    
    def load_metadata(self, plugin_name: str) -> Optional[PluginMetadata]:
        """
        加载插件元数据
        
        :param plugin_name: 插件名称
        :return: 插件元数据
        """
        metadata_file = os.path.join(self.plugin_dir, plugin_name, '.sleepymetadata')
        
        try:
            with open(metadata_file, 'r', encoding='utf-8') as f:
                data = load_toml(f)
                metadata = PluginMetadata(
                    name=data.get('name', plugin_name),
                    version=data.get('version', '0.0.0'),
                    description=data.get('description', ''),
                    author=data.get('author', ''),
                    enabled=data.get('enabled', True),
                    dependencies=data.get('dependencies', [])
                )
                return metadata
        except Exception as e:
            l.error(f'Failed to load metadata for plugin {plugin_name}: {e}')
            return None
    
    def load_plugin(self, plugin_name: str) -> bool:
        """
        加载单个插件
        
        :param plugin_name: 插件名称
        :return: 是否加载成功
        """
        # 加载元数据
        metadata = self.load_metadata(plugin_name)
        if not metadata:
            return False
        
        if not metadata.enabled:
            l.info(f'Plugin {plugin_name} is disabled, skipping')
            return False
        
        # 检查依赖
        for dep in metadata.dependencies:
            if dep not in self.plugins:
                l.error(f'Plugin {plugin_name} depends on {dep}, but it is not loaded')
                return False
        
        # 加载插件模块
        plugin_path = os.path.join(self.plugin_dir, plugin_name)
        init_file = os.path.join(plugin_path, '__init__.py')
        
        try:
            # 动态导入模块
            spec = importlib.util.spec_from_file_location(
                f'plugins.{plugin_name}',
                init_file
            )
            if not spec or not spec.loader:
                l.error(f'Failed to load spec for plugin {plugin_name}')
                return False
            
            module = importlib.util.module_from_spec(spec)
            sys.modules[f'plugins.{plugin_name}'] = module
            spec.loader.exec_module(module)
            
            # 获取插件类
            if not hasattr(module, 'Plugin'):
                l.error(f'Plugin {plugin_name} does not have a Plugin class')
                return False
            
            PluginClass = getattr(module, 'Plugin')
            plugin_instance = PluginClass(metadata)
            
            if not isinstance(plugin_instance, PluginBase):
                l.error(f'Plugin {plugin_name} Plugin class must inherit from PluginBase')
                return False
            
            # 调用加载钩子
            plugin_instance.on_load()
            
            # 注册插件
            self.plugins[plugin_name] = plugin_instance
            self.metadata[plugin_name] = metadata
            
            # 注册响应修改器
            if hasattr(plugin_instance, 'modify_response'):
                self._response_modifiers.append((plugin_name, plugin_instance.modify_response))
            
            l.info(f'Plugin loaded: {plugin_name} v{metadata.version}')
            return True
            
        except Exception as e:
            l.error(f'Failed to load plugin {plugin_name}: {e}\n{u.format_exc() if hasattr(u, "format_exc") else ""}')
            return False
    
    def load_all_plugins(self):
        """加载所有发现的插件"""
        plugin_names = self.discover_plugins()
        
        if not plugin_names:
            l.info('No plugins found')
            return
        
        l.info(f'Found {len(plugin_names)} plugin(s): {", ".join(plugin_names)}')
        
        # 按依赖顺序加载
        loaded = set()
        remaining = set(plugin_names)
        
        while remaining:
            progress = False
            
            for plugin_name in list(remaining):
                metadata = self.load_metadata(plugin_name)
                if not metadata:
                    remaining.remove(plugin_name)
                    continue
                
                # 检查依赖是否已加载
                deps_loaded = all(dep in loaded for dep in metadata.dependencies)
                
                if deps_loaded:
                    if self.load_plugin(plugin_name):
                        loaded.add(plugin_name)
                    remaining.remove(plugin_name)
                    progress = True
            
            # 如果一轮循环没有进展，说明有循环依赖或缺失依赖
            if not progress:
                l.error(f'Cannot load plugins due to unresolved dependencies: {remaining}')
                break
    
    def setup_plugin_routes(self, app: FastAPI):
        """
        为所有插件设置路由
        
        :param app: FastAPI 应用实例
        """
        for plugin_name, plugin in self.plugins.items():
            try:
                # 创建插件专属路由器（如果插件有自己的路由器）
                if plugin.router:
                    app.include_router(
                        plugin.router,
                        prefix=f'/api/plugin/{plugin_name}',
                        tags=[f'plugin:{plugin_name}']
                    )
                    l.info(f'Registered routes for plugin: {plugin_name} at /api/plugin/{plugin_name}')
                
                # 调用插件自定义路由设置
                plugin.setup_routes(app)
                
            except Exception as e:
                l.error(f'Failed to setup routes for plugin {plugin_name}: {e}')
    
    def apply_response_modifiers(self, request: Request, response: Response, endpoint: str) -> Response:
        """
        应用所有插件的响应修改器
        
        :param request: 原始请求
        :param response: 原始响应
        :param endpoint: 端点路径
        :return: 修改后的响应
        """
        modified_response = response
        
        for plugin_name, modifier in self._response_modifiers:
            try:
                modified_response = modifier(request, modified_response, endpoint)
            except Exception as e:
                l.error(f'Plugin {plugin_name} response modifier failed: {e}')
        
        return modified_response
    
    def unload_plugin(self, plugin_name: str) -> bool:
        """
        卸载插件
        
        :param plugin_name: 插件名称
        :return: 是否卸载成功
        """
        if plugin_name not in self.plugins:
            l.warning(f'Plugin {plugin_name} is not loaded')
            return False
        
        try:
            plugin = self.plugins[plugin_name]
            plugin.on_unload()
            
            # 移除响应修改器
            self._response_modifiers = [
                (name, modifier) for name, modifier in self._response_modifiers
                if name != plugin_name
            ]
            
            del self.plugins[plugin_name]
            del self.metadata[plugin_name]
            
            # 移除模块引用
            if f'plugins.{plugin_name}' in sys.modules:
                del sys.modules[f'plugins.{plugin_name}']
            
            l.info(f'Plugin unloaded: {plugin_name}')
            return True
            
        except Exception as e:
            l.error(f'Failed to unload plugin {plugin_name}: {e}')
            return False
    
    def get_plugin(self, plugin_name: str) -> Optional[PluginBase]:
        """获取插件实例"""
        return self.plugins.get(plugin_name)
    
    def get_loaded_plugins(self) -> List[str]:
        """获取已加载插件列表"""
        return list(self.plugins.keys())
    
    def get_plugin_info(self, plugin_name: str) -> Optional[Dict[str, Any]]:
        """获取插件信息"""
        if plugin_name not in self.metadata:
            return None
        
        meta = self.metadata[plugin_name]
        return {
            'name': meta.name,
            'version': meta.version,
            'description': meta.description,
            'author': meta.author,
            'enabled': meta.enabled,
            'dependencies': meta.dependencies
        }


# 全局插件管理器实例
plugin_manager = PluginManager()
