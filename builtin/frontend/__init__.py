# Copyright (C) 2026 sleepy-project
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
frontend —— 前端静态资源服务

**这个插件不下载任何东西。**

v6 的同名插件会在启动时从 44 个 GitHub 代理镜像里挑一个, 下载前端 zip 并
用 pnpm 构建。那正是 v7 要摆脱的模式: 启动依赖外部网络、内容没有校验、
断网即失败。

v7 的做法是只 serve 本地已有的构建产物 (`frontend/dist/`):

- Docker 镜像与 release 包里已经打包好 dist, 开箱即用
- 从源码运行时, 用 `python main.py frontend build` 自行构建 (需要 pnpm)
- dist 不存在时插件不注册任何路由, 只在日志里说明怎么办 ——
  后端 API 完全不受影响
'''

import argparse
import shutil
import subprocess
import typing as t
from pathlib import Path

from fastapi import Request, status as hc
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger as l
from pydantic import BaseModel

from core import errors as e
from core import utils as u
from core.plugin import PluginBase, PluginMetadata

API_PREFIXES = ('/api', '/docs', '/redoc', '/openapi.json', '/favicon.ico')
'''这些前缀属于后端, 不能被 SPA 的 catch-all 吃掉'''


class FrontendConfig(BaseModel):
    '''
    frontend 插件配置 (`plugin.frontend`)
    '''

    dist_dir: str = 'frontend/dist'
    '''构建产物目录 (相对项目根目录)'''

    source_dir: str = 'frontend'
    '''前端源码目录, `frontend build` 命令在这里执行 pnpm'''

    spa_fallback: bool = True
    '''
    未匹配的路径是否回落到 index.html

    单页应用的前端路由 (如 /login) 需要它; 关掉则只按真实文件路径提供服务。
    '''


class Plugin(PluginBase):

    def __init__(self, metadata: PluginMetadata):
        super().__init__(metadata)
        self.register_config(FrontendConfig)

        self.add_cli_command(
            command='frontend',
            handler=self.cli_build,
            help='Build the frontend from source (requires pnpm)',
            arguments=[
                (['action'], {'choices': ['build'], 'help': 'Action to perform'}),
                (['--install'], {'action': 'store_true', 'help': 'Run `pnpm install` first'}),
            ]
        )

        self.exports = {
            'dist_path': self.dist_path,
            'is_available': self.is_available,
        }

    @property
    def config(self) -> FrontendConfig:
        return t.cast(FrontendConfig, self.get_config())

    def dist_path(self) -> Path:
        return Path(u.get_path(self.config.dist_dir, create_dirs=False))

    def source_path(self) -> Path:
        return Path(u.get_path(self.config.source_dir, create_dirs=False))

    def is_available(self) -> bool:
        '''
        构建产物是否就绪
        '''
        return (self.dist_path() / 'index.html').is_file()

    def on_load(self):
        dist = self.dist_path()
        if not self.is_available():
            l.warning(
                f'Frontend assets not found at {dist} — serving API only. '
                f'Build them with `python main.py frontend build` (requires pnpm), '
                f'or use the Docker image / release archive which ships them prebuilt.'
            )
            return

        # 静态资源目录整体挂上去; 具体子目录名由前端构建工具决定, 这里不做假设
        for sub in ('assets', 'static'):
            if (dist / sub).is_dir():
                self.mount(f'/{sub}', StaticFiles(directory=str(dist / sub)), name=f'frontend-{sub}')

        self.add_route('/', self._index, ['GET'], tags=['frontend'],
                       name='Frontend index', include_in_schema=False, override=True)

        if self.config.spa_fallback:
            # low_priority 是必须的: 插件按名称排序加载, frontend 排在 metrics /
            # status 之前, 这个 catch-all 若按常规顺序注册会抢先匹配掉它们的接口。
            self.add_route('/{spa_path:path}', self._spa, ['GET'], tags=['frontend'],
                           name='Frontend SPA fallback', include_in_schema=False,
                           low_priority=True)

        l.info(f'Serving frontend from {dist}')

    # region routes

    async def _index(self):
        return FileResponse(self.dist_path() / 'index.html')

    async def _spa(self, request: Request, spa_path: str):
        '''
        SPA 回落

        前端路由 (/login 之类) 在服务端没有对应文件, 一律返回 index.html
        交给前端路由器处理。属于后端的前缀必须排除掉, 否则一个拼错的
        /api/xxx 会返回一个 200 的 HTML 页面, 让客户端极难排查。
        '''
        path = '/' + spa_path
        if path.startswith(API_PREFIXES):
            raise e.APIUnsuccessful(hc.HTTP_404_NOT_FOUND, f'No such endpoint: {path}')

        # 真实存在的文件直接给出去 (favicon、manifest 之类散落在 dist 根部的文件)
        candidate = (self.dist_path() / spa_path).resolve()
        dist_root = self.dist_path().resolve()
        if candidate.is_file() and candidate.is_relative_to(dist_root):
            return FileResponse(candidate)

        return FileResponse(dist_root / 'index.html')

    # endregion routes

    # region cli

    def cli_build(self, args: argparse.Namespace):
        '''
        `python main.py frontend build`
        '''
        source = self.source_path()
        if not (source / 'package.json').is_file():
            l.error(f'No package.json under {source} — nothing to build.')
            return

        pnpm = shutil.which('pnpm')
        if not pnpm:
            l.error('pnpm not found. Install it (https://pnpm.io) or use the prebuilt release archive.')
            return

        if args.install:
            l.info('Running pnpm install...')
            subprocess.run([pnpm, 'install'], cwd=source, check=True)

        l.info('Running pnpm build...')
        subprocess.run([pnpm, 'build'], cwd=source, check=True)
        l.success(f'Frontend built into {self.dist_path()}')

    # endregion cli
