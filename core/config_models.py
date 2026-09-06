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

import typing as t

from pydantic import BaseModel, PositiveInt

# region user-config


class _LoggingConfigModel(BaseModel):
    '''
    日志配置 Model
    '''

    level: t.Literal['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] = 'INFO'
    '''
    日志等级
    '''

    file: str | None = 'logs/{time:YYYY-MM-DD}.log'
    '''
    日志文件保存格式 (for Loguru)
    - 设置为 None 以禁用
    '''

    file_level: t.Literal['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] | None = 'INFO'
    '''
    单独设置日志文件中的日志等级, 如设置为 None 则使用 level 设置
    '''

    rotation: str | int = '1 days'
    '''
    配置 Loguru 的 rotation (轮转周期) 设置
    '''

    retention: str | int = '3 days'
    '''
    配置 Loguru 的 retention (轮转保留) 设置
    '''


class _PluginsConfigModel(BaseModel):
    '''
    插件系统配置 Model

    注意与 `ConfigModel.plugin` 区分:
    - `plugins` (本 Model) 控制插件系统本身的行为
    - `plugin` 是各插件自己的配置项命名空间
    '''

    disabled: list[str] = []
    '''
    禁用的插件列表 (按目录名)

    内置插件随仓库分发, 因此需要一个显式关掉它们的开关。
    例如不需要 v5 兼容层时: `disabled: ['compat-v5']`
    '''

    builtin_dir: str = 'builtin'
    '''
    内置插件目录 (随仓库分发, git 跟踪)
    '''

    external_dir: str = 'plugins'
    '''
    外部插件目录 (用户自行安装, 不受 git 跟踪)

    同名时外部插件覆盖内置插件, 以便用户替换内置实现。
    '''


class ConfigModel(BaseModel):
    '''
    配置 Model

    core 只保留「机制」相关的配置项。
    业务配置 (状态列表、设备过期时间等) 由对应插件通过 `register_config()` 自行声明。
    '''

    host: str = '0.0.0.0'
    '''
    服务监听地址
    '''

    port: PositiveInt = 9010
    '''
    服务监听端口
    '''

    dev: bool = False
    '''
    启用 dev Token 登录 (仅用于开发环境)
    '''

    cors_origins: list[str] = ['*']
    '''
    允许跨域的来源列表

    浏览器端客户端 (如 `client/browser-script.user.js`) 从任意页面发起上报请求, 没有 CORS 就会被浏览器拦截。
    v6 遗漏了这一项, 这里补回。
    '''

    log: _LoggingConfigModel = _LoggingConfigModel()
    '''
    日志配置
    '''

    plugins: _PluginsConfigModel = _PluginsConfigModel()
    '''
    插件系统配置
    '''

    database: str = 'sqlite:///data/sleepy.db'
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
    WebSocket 推送刷新间隔 (秒)
    '''

    auth_access_token_expires_minutes: PositiveInt = 60
    '''
    Access Token (管理登录) 过期时间 (分钟)
    '''

    auth_refresh_token_expires_days: PositiveInt = 30
    '''
    Refresh Token (管理登录) 过期时间 (天)
    '''

    token_last_active_throttle_seconds: PositiveInt = 60
    '''
    Token `last_active` 字段的写入节流间隔 (秒)

    v6 每次鉴权都会 update + commit 一次, 在每 30 秒上报一次的设备上造成明显写放大。
    间隔内的重复访问不再落库。
    '''

    plugin: t.Dict[str, t.Any] = {}
    '''
    插件配置命名空间

    各插件的配置项在 `plugin.<插件目录名>` 下设置:
    - TOML: `[plugin.main-status]`
    - YAML: `plugin.main-status.key: value`
    - JSON: `{"plugin": {"main-status": {"key": "value"}}}`
    - Env:  `SLEEPY_PLUGIN_MAIN_STATUS_KEY=value`
    '''


# endregion user-config

env_vaildate_json_keys = [
    'cors_origins',
    'plugins_disabled',
    'plugin'
]
'''
此列表中的键将会尝试解析为 json
(不包含 `sleepy_` 前缀)
'''
