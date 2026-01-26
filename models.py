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

from time import time
import typing as t

from sqlalchemy import JSON
from sqlmodel import SQLModel, Field

class Metadata(SQLModel, table=True):
    '''
    元数据
    '''
    id: int = Field(default=0, primary_key=True, index=True)
    status: int = Field(default=0)
    last_updated: float = Field(default_factory=time)


class DeviceData(SQLModel, table=True):
    '''
    设备数据
    '''
    id: str = Field(primary_key=True, index=True)
    name: str = Field()
    status: str = Field()
    using: bool = Field(default=True)
    fields: t.Dict[str, t.Any] = Field(default={}, sa_type=JSON)
    last_updated: float = Field(default_factory=time)


class AuthSecret(SQLModel, table=True):
    '''
    鉴权密钥（沿用历史表结构）
    '''
    __tablename__: str = 'userdata'
    username: str = Field(default='__sleepy__', primary_key=True)
    password: bytes = Field()  # 2x hashed (sha256 + salt)
    salt: bytes = Field()


class TokenData(SQLModel, table=True):
    '''
    Token 数据
    '''
    token: str = Field(primary_key=True, index=True)
    type: str = Field(index=True)  # auth_access / auth_refresh
    created: float = Field(default_factory=time, index=True)
    last_active: float = Field(default_factory=time, index=True)
    expire: float = Field(default=0.0, index=True)   # 0 -> never expires
