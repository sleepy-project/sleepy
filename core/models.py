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
core 数据模型

只包含框架自身需要的表。业务模型 (设备、状态、统计等) 由对应插件通过
`PluginBase.register_model()` 声明, 不属于 core。
'''

import typing as t
from time import time

from sqlalchemy import JSON
from sqlmodel import SQLModel, Field


class AuthSecret(SQLModel, table=True):
    '''
    鉴权密钥 (沿用历史表结构)
    '''
    __tablename__: str = 'userdata'

    username: str = Field(default='__sleepy__', primary_key=True)
    password: bytes = Field()  # 2x hashed (sha256 + bcrypt)
    salt: bytes = Field()


class TokenData(SQLModel, table=True):
    '''
    Token 数据

    `type` 形如 `<prefix>:<login_type>:<device_hash>`, 例如:
    - `auth_access:web:<hash>`   管理面板 access token
    - `auth_refresh:web:<hash>`  管理面板 refresh token
    - `device::<hash>`           设备长期 token (由 device-auth 插件签发)
    '''
    token: str = Field(primary_key=True, index=True)
    type: str = Field(index=True)
    name: str | None = Field(default=None)
    '''token 备注名 (device token 在面板中展示用)'''
    created: float = Field(default_factory=time, index=True)
    last_active: float = Field(default_factory=time, index=True)
    expire: float = Field(default=0.0, index=True)
    '''过期时间戳, 0 表示永不过期'''


class PluginKV(SQLModel, table=True):
    '''
    插件通用键值存储

    供插件保存少量结构化数据 (设置、缓存的远端结果等) 而无需自建表。
    数据量较大或需要查询的场景应当用 `register_model()` 声明专用表。
    '''
    __tablename__: str = 'plugin_kv'

    plugin: str = Field(primary_key=True, index=True)
    key: str = Field(primary_key=True, index=True)
    value: t.Dict[str, t.Any] = Field(default={}, sa_type=JSON)
    updated: float = Field(default_factory=time)
