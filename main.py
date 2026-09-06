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
Sleepy 启动入口

    python main.py                启动服务
    python main.py --fresh-start  清空数据库后启动
    python main.py <插件命令>      执行插件注册的 CLI 命令

也可以直接用 ASGI 服务器指向应用对象:

    uvicorn core.app:app --host 0.0.0.0 --port 9010
    fastapi run core/app.py
'''

import argparse
import sys
from traceback import format_exc

from loguru import logger as l

from core import db
from core.config import config as c
from core.logging import setup_logging
from core.plugin import plugin_manager


def build_parser() -> argparse.ArgumentParser:
    '''
    构建参数解析器 (含插件注册的子命令)
    '''
    parser = argparse.ArgumentParser(prog='sleepy', description='Sleepy Backend Runner & CLI')
    parser.add_argument(
        '--fresh-start',
        action='store_true',
        help='Drop and recreate the database before starting'
    )
    parser.add_argument(
        '--host',
        default=None,
        help=f'Override listen address (config: {c.host})'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=None,
        help=f'Override listen port (config: {c.port})'
    )
    # 插件的 CLI 子命令需要插件先加载完成
    plugin_manager.setup_cli_commands(parser)
    return parser


def main() -> int:
    setup_logging()

    # 插件要先加载: 它们既提供 CLI 子命令, 也在 import 时声明自己的数据表
    l.info('Loading plugins')
    plugin_manager.load_all_plugins()

    args = build_parser().parse_args()

    if args.fresh_start:
        db.drop_all_tables()

    # 执行插件 CLI 命令
    handler = getattr(args, 'func', None)
    if handler is not None:
        db.create_db_and_tables()
        command = getattr(args, 'command', 'unknown')
        l.info(f'Executing CLI command: {command}')
        try:
            plugin_manager.run_cli_handler(handler, args)
        except Exception as ex:
            l.error(f'CLI command failed: {ex}\n{format_exc()}')
            return 1
        l.info('CLI command executed successfully')
        return 0

    # 启动服务
    #
    # 延迟到这里才导入 core.app: 该模块在导入期就会组装应用并建表,
    # 提前导入会让 --fresh-start 赶不上。
    #
    # 另外这里把 **app 对象** 交给 uvicorn, 而不是 v6 的 `run('main:app')` 字符串 ——
    # 以字符串形式启动时 uvicorn 会按模块名重新 import 一次入口文件,
    # 而入口此前是以 `__main__` 身份执行的, 于是整套初始化会跑两遍。
    from uvicorn import run
    from core.app import app

    host = args.host or c.host
    port = args.port or c.port
    l.info(f'Starting server: {f"[{host}]" if ":" in host else host}:{port}')
    run(app, host=host, port=port)
    l.info('Bye.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
