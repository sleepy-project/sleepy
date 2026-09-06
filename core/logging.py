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
日志初始化 (loguru + 请求 ID)
'''

from contextvars import ContextVar
from logging import getLogger as logging_getLogger, WARNING, Handler as LoggingHandler
from sys import stderr

from loguru import logger as l

from core.config import config as c

reqid: ContextVar[str] = ContextVar('sleepy_reqid', default='not-in-request')
'''当前请求 ID'''

_configured = False


def _log_format(record) -> str:
    request_id = record['extra'].get('reqid', 'fallback-logid')
    return (
        '<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | '
        f'<yellow>{request_id}</yellow> | '
        '<cyan>{name}</cyan>:<cyan>{line}</cyan> | <level>{message}</level>\n'
    )


class InterceptHandler(LoggingHandler):
    '''
    将标准库 logging 的输出转发到 loguru
    '''

    def emit(self, record):
        logger_opt = l.opt(depth=6, exception=record.exc_info)
        logger_opt.log(record.levelname, record.getMessage())


def setup_logging():
    '''
    配置 loguru 与标准库 logging

    重复调用是安全的 —— v6 因为 `run('main:app')` 造成模块二次执行,
    日志 handler 被装了两遍, 每条日志输出两次。这里显式做幂等保护。
    '''
    global _configured
    if _configured:
        return
    _configured = True

    l.remove()
    l.add(
        stderr,
        level=c.log.level,
        format=_log_format,
        backtrace=True,
        diagnose=True
    )
    if c.log.file:
        l.add(
            c.log.file,
            level=c.log.file_level or c.log.level,
            format=_log_format,
            colorize=False,
            rotation=c.log.rotation,
            retention=c.log.retention,
            enqueue=True
        )
    l.configure(extra={'reqid': 'not-in-request'})

    for name in ('uvicorn', 'uvicorn.access', 'uvicorn.error'):
        logging_getLogger(name).handlers.clear()
    logging_getLogger().handlers = [InterceptHandler()]
    logging_getLogger().setLevel(c.log.level)
    logging_getLogger('watchfiles').setLevel(WARNING)
