# coding: utf-8

from time import time
import typing as t
from secrets import token_hex

from sqlalchemy import JSON
from sqlmodel import SQLModel, Field


class AuthData(SQLModel, table=True):
    '''
    认证数据
    '''
    id: int = Field(default=0, primary_key=True, index=True)
    secret_key: str = Field(default=token_hex(32))
    username: str = Field()
    hashed_password: str = Field()


class Metadata(SQLModel, table=True):
    '''
    元数据
    '''
    id: int = Field(default=0, primary_key=True, index=True)
    status: int = Field(default=0)
    private_mode: bool = Field(default=False)
    last_updated: float = Field(default=time())


class DeviceData(SQLModel, table=True):
    '''
    设备数据
    '''
    id: str = Field(primary_key=True, index=True)
    name: str = Field(default='')
    status: str = Field(default='')
    using: bool = Field(default=True)
    fields: t.Dict[str, t.Any] = Field(default={}, sa_type=JSON)
    last_updated: float = Field(default=time())
