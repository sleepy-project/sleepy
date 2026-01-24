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
    # show_name: str = Field()
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
