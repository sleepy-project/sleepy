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

from fastapi import Request, Response
from loguru import logger as l

from plugin import PluginBase, PluginMetadata


class Plugin(PluginBase):
    """
    Example plugin
    """

    def __init__(self, metadata: PluginMetadata):
        super().__init__(metadata)
        self._register_routes()

    def on_load(self):
        l.info(f'{self.metadata.name} plugin loaded!')

    def on_unload(self):
        l.info(f'{self.metadata.name} plugin unloaded!')

    def _register_routes(self):
        """
        Register plugin routes using add_route()
        These will be mounted directly on the app by PluginManager
        """

        async def root():
            """
            Root endpoint
            """
            return 'Welcome to sleepy!'
        
        self.add_route(
            path='/',
            endpoint=root,
            methods=['GET'],
            tags=['example_plugin'],
            name='example_plugin_root',
            override=True
        )


    def modify_response(
        self,
        request: Request,
        response: Response,
        endpoint: str
    ) -> Response:
        """
        Modify responses globally

        Example: add header to /api/query
        """
        if endpoint == '/api/query':
            response.headers['X-Modified-By'] = self.metadata.name
            l.debug(f'{self.metadata.name}: Modified response for {endpoint}')

        return response
