# coding: utf-8

from fastapi import APIRouter, Request, Response
from loguru import logger as l
from plugin import PluginBase, PluginMetadata


class Plugin(PluginBase):
    
    def __init__(self, metadata: PluginMetadata):
        super().__init__(metadata)
        self.router = APIRouter()
        self._setup_routes()
    
    def on_load(self):
        """插件加载时调用"""
        l.info(f'{self.metadata.name} plugin loaded!')
    
    def on_unload(self):
        """插件卸载时调用"""
        l.info(f'{self.metadata.name} plugin unloaded!')
    
    def _setup_routes(self):
        """设置插件专属路由"""
        
        @self.router.get('/hello')
        async def plugin_hello():
            """
            插件端点示例
            """
            return {
                'message': f'Hello from {self.metadata.name}!',
                'version': self.metadata.version
            }
        
        @self.router.get('/info')
        async def plugin_info():
            """
            插件信息
            """
            return {
                'name': self.metadata.name,
                'version': self.metadata.version,
                'description': self.metadata.description,
                'author': self.metadata.author
            }
    
    def setup_routes(self, app):
        """
        设置全局路由
        """
        from fastapi import APIRouter
        
        # 创建全局路由器
        global_router = APIRouter(tags=['example_plugin_global'])
        
        @global_router.get('/api/example/global')
        async def global_endpoint():
            """
            全局端点示例
            """
            return {'message': 'This is a global endpoint from example_plugin'}
        
        # 注册到主应用
        app.include_router(global_router)
        l.info(f'{self.metadata.name}: Registered global routes')
    
    def modify_response(self, request: Request, response: Response, endpoint: str) -> Response:
        """
        修改响应
        
        示例: 为所有 /api/query 响应添加自定义 header
        """
        if endpoint == '/api/query':
            response.headers['X-Modified-By'] = self.metadata.name
            l.debug(f'{self.metadata.name}: Modified response for {endpoint}')
        
        return response
