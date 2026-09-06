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
数据库引擎与表注册

表创建的时序很关键: 插件的模型类只有在插件模块被 import 之后才会登记进
`SQLModel.metadata`, 因此 `create_db_and_tables()` 必须在**所有插件加载完成之后**调用。

v6 在 lifespan 中的顺序是「先建表, 再加载插件」, 插件自己声明的表因此永远不会被创建
(除非插件自行调用 `create_all`)。v7 把顺序反过来, 并用 `register_model()` 让这件事显式化。
'''

import typing as t

from loguru import logger as l
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import create_engine, SQLModel, Session

from core.config import config as c
from core import models as m  # noqa: F401  -- 导入以登记 core 自身的表

_registered_models: dict[str, list[str]] = {}
'''插件名 -> 该插件声明的表名列表 (仅用于诊断与日志)'''

_is_sqlite = c.database.startswith('sqlite')

engine = create_engine(
    c.database,
    connect_args={'check_same_thread': False} if _is_sqlite else {},
    echo=False
)


if _is_sqlite:
    @event.listens_for(Engine, 'connect')
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        '''
        SQLite 连接参数

        - WAL: 允许读写并发, 避免上报写入阻塞前端查询
        - synchronous=NORMAL: WAL 下的推荐值, 显著降低小写入的开销
        '''
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute('PRAGMA journal_mode=WAL')
            cursor.execute('PRAGMA synchronous=NORMAL')
            cursor.execute('PRAGMA foreign_keys=ON')
        except Exception as ex:
            l.warning(f'Failed to apply SQLite pragmas: {ex}')
        finally:
            cursor.close()


def register_model(model: type[SQLModel], plugin: str = 'core') -> type[SQLModel]:
    '''
    登记一个插件声明的数据表

    模型类被 import 时就已经进入 `SQLModel.metadata`, 本函数不改变这一点;
    它的作用是记录归属关系, 并在建表前给出可读的日志, 便于排查
    「插件表没建出来」这类问题。

    :param model: SQLModel 表模型 (`table=True`)
    :param plugin: 声明该表的插件名
    :return: 原样返回 model, 便于链式调用
    '''
    table_name = getattr(model, '__tablename__', model.__name__)
    _registered_models.setdefault(plugin, []).append(str(table_name))
    l.debug(f'Registered model {model.__name__} (table: {table_name}) from {plugin}')
    return model


def get_registered_models() -> dict[str, list[str]]:
    '''
    获取表注册情况 (插件名 -> 表名列表)
    '''
    return {k: list(v) for k, v in _registered_models.items()}


def create_db_and_tables():
    '''
    创建所有已登记的表

    必须在全部插件加载完成后调用。
    '''
    known = SQLModel.metadata.tables.keys()
    l.debug(f'Creating tables: {", ".join(sorted(known))}')
    SQLModel.metadata.create_all(engine)


def drop_all_tables():
    '''
    删除所有表 (`--fresh-start`)
    '''
    l.warning('Fresh start requested: dropping all tables')
    SQLModel.metadata.drop_all(engine)


def get_session() -> t.Generator[Session, None, None]:
    '''
    FastAPI 依赖: 提供一个 Session
    '''
    with Session(engine) as sess:
        yield sess


def session() -> Session:
    '''
    在请求上下文之外获取 Session (需自行 `with` 管理)

    ```python
    with db.session() as sess:
        ...
    ```
    '''
    return Session(engine)
