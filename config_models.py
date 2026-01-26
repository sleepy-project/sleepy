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

from pydantic import BaseModel, PositiveInt
import typing as t

# region user-config


class _LoggingConfigModel(BaseModel):
    '''
    日志配置 Model
    '''

    level: t.Literal['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] = 'INFO'
    '''
    日志等级
    - DEBUG
    - INFO
    - WARNING
    - ERROR
    - CRITICAL
    '''

    file: str | None = 'logs/{time:YYYY-MM-DD}.log'
    '''
    日志文件保存格式 (for Loguru)
    - 设置为 None 以禁用
    '''

    file_level: t.Literal['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] | None = 'INFO'
    '''
    单独设置日志文件中的日志等级, 如设置为 None 则使用 level 设置
    - DEBUG
    - INFO
    - WARNING
    - ERROR
    - CRITICAL
    '''

    rotation: str | int = '1 days'
    '''
    配置 Loguru 的 rotation (轮转周期) 设置
    '''

    retention: str | int = '3 days'
    '''
    配置 Loguru 的 retention (轮转保留) 设置
    '''


class ConfigModel(BaseModel):
    '''
    配置 Model
    '''

    host: str = '0.0.0.0'
    '''
    服务监听地址 (仅在直接启动 main.py 时有效)
    '''

    port: PositiveInt = 9010
    '''
    服务监听端口 (仅在直接启动 main.py 时有效)
    '''

    dev: bool = False
    '''
    启用 dev Token 登录 (仅用于开发环境)
    '''

    # workers: PositiveInt = 2
    # '''
    # 服务 Worker 数 (仅在直接启动 main.py 时有效)
    # '''

    log: _LoggingConfigModel = _LoggingConfigModel()

    database: str = 'sqlite:///data.db'
    '''
    数据库 url
    - SQLite: `sqlite:///文件名.db`
    - MySQL: `mysql://用户名:密码@主机:端口号/数据库名`
    - 更多: https://docs.sqlalchemy.org.cn/en/20/core/engines.html#backend-specific-urls
    '''

    ping_interval: int = 20
    '''
    Event-Stream Ping 间隔 (单位: 秒, 设置为 0 禁用)
    '''

    ws_refresh_interval: PositiveInt = 5
    '''
    /api/ws 推送刷新间隔 (秒)
    '''

    auth_access_token_expires_minutes: PositiveInt = 60
    '''
    Auth Token (管理登录) 过期时间 (分钟)
    '''

    auth_refresh_token_expires_days: PositiveInt = 30
    '''
    Refresh Token (管理登录) 过期时间 (天)
    '''

    device_token_expires_days: PositiveInt = 365
    '''
    (默认) Device Token (设备更新状态密钥) 过期时间 (天)
    '''


# endregion user-config
env_vaildate_json_keys = [
    'status_status_list',
    'metrics_allow_list',
    'plugins_enabled',
    'plugin'
]
'''
此列表中的键将会尝试解析为 json
(不包含 `sleepy_`)
'''
