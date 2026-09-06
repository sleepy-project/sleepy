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
status —— 手动状态与整体状态查询

`GET /api/v1/status` 返回的是**聚合快照**: 本插件只提供 `status` / `last_updated`,
设备列表来自 device 插件注册的 snapshot provider。两个插件因此互不依赖 ——
禁用其中任何一个, 另一个仍然可用。
'''

import typing as t
from time import time

from fastapi import Security, status as hc
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlmodel import Field, Session, SQLModel, select

from core import errors as e
from core.auth import AUTH_ACCESS_PREFIX, SessionDep, TokenDep
from core.broadcast import manager
from core.events import BaseEvent
from core.plugin import PluginBase, PluginMetadata


# region models


class StatusMeta(SQLModel, table=True):
    '''
    手动状态元数据 (单行)
    '''
    __tablename__: str = 'metadata'

    id: int = Field(default=0, primary_key=True, index=True)
    status: int = Field(default=0)
    last_updated: float = Field(default_factory=time)


class StatusPreset(BaseModel):
    '''
    一个状态预设
    '''
    id: int
    name: str
    desc: str = ''
    color: str = 'awake'


class StatusConfig(BaseModel):
    '''
    status 插件配置 (`plugin.status`)
    '''
    presets: list[StatusPreset] = [
        StatusPreset(id=0, name='活着', desc='目前在线，可以联系', color='awake'),
        StatusPreset(id=1, name='似了', desc='睡似了或者在忙别的事情', color='sleeping'),
    ]
    '''状态预设列表'''

    default: int = 0
    '''初始化时使用的状态 id'''


class StatusSetRequest(BaseModel):
    status: int


class StatusResponse(BaseModel):
    time: float
    status: int
    last_updated: float
    devices: list[t.Any] = []
    private: bool = False


# endregion models


class StatusUpdatedEvent(BaseEvent):
    '''手动状态即将变更'''
    id = 'status_updated'

    def __init__(self, status: int, previous: int):
        super().__init__()
        self.status = status
        self.previous = previous


class Plugin(PluginBase):

    def __init__(self, metadata: PluginMetadata):
        super().__init__(metadata)
        self.register_model(StatusMeta)
        self.register_config(StatusConfig)

        self.exports = {
            'get_status': self.get_status,
            'set_status': self.set_status,
            'get_presets': self.get_presets,
            'query': self.query,
            'StatusMeta': StatusMeta,
        }

    @property
    def config(self) -> StatusConfig:
        return t.cast(StatusConfig, self.get_config())

    def on_load(self):
        self.register_snapshot_provider(self._snapshot)

        admin_auth = TokenDep((AUTH_ACCESS_PREFIX,))

        self.add_route('/api/v1/status', self._route_query, ['GET'],
                       tags=['status'], name='Query overall status', response_model=StatusResponse)
        self.add_route('/api/v1/status', self._route_set, ['PUT'],
                       tags=['status'], name='Set manual status',
                       dependencies=[Security(admin_auth)])
        self.add_route('/api/v1/status/presets', self._route_presets, ['GET'],
                       tags=['status'], name='List status presets', response_model=list[StatusPreset])

    # region data-access

    def _meta(self, sess: Session) -> StatusMeta:
        '''
        取出单行元数据, 不存在则创建
        '''
        record = sess.exec(select(StatusMeta)).first()
        if not record:
            record = StatusMeta(status=self.config.default)
            sess.add(record)
            sess.commit()
            sess.refresh(record)
        return record

    def get_status(self, sess: Session) -> int:
        '''
        当前手动状态 id
        '''
        return self._meta(sess).status

    def get_presets(self) -> list[StatusPreset]:
        '''
        状态预设列表
        '''
        return self.config.presets

    def _write_status(self, sess: Session, value: int) -> StatusMeta:
        record = self._meta(sess)
        record.status = value
        record.last_updated = time()
        sess.add(record)
        sess.commit()
        sess.refresh(record)
        return record

    async def set_status(self, sess: Session, value: int) -> StatusMeta:
        '''
        设置手动状态 (会触发 `status_updated` 事件)
        '''
        known = {p.id for p in self.config.presets}
        if known and value not in known:
            raise e.APIUnsuccessful(
                hc.HTTP_400_BAD_REQUEST,
                f'Unknown status id {value}, available: {sorted(known)}'
            )

        previous = self.get_status(sess)
        evt = StatusUpdatedEvent(value, previous)
        await self.emit(evt)
        if evt.intercepted:
            raise e.APIUnsuccessful(evt.interception[1], str(evt.interception[0]))  # type: ignore[index]

        record = await run_in_threadpool(self._write_status, sess, evt.status)
        await self.broadcast('status-changed', {'status': record.status, 'last_updated': record.last_updated})
        return record

    def _snapshot(self) -> dict:
        from core import db
        with db.session() as sess:
            record = self._meta(sess)
            return {'status': record.status, 'last_updated': record.last_updated}

    def query(self, sess: Session) -> dict:
        '''
        整体状态 (聚合所有插件的快照)
        '''
        return {'time': time(), **manager.snapshot()}

    # endregion data-access

    # region routes

    async def _route_query(self, sess: SessionDep):
        return self.query(sess)

    async def _route_set(self, sess: SessionDep, req: StatusSetRequest):
        record = await self.set_status(sess, req.status)
        return {'status': record.status, 'last_updated': record.last_updated}

    async def _route_presets(self):
        return self.get_presets()

    # endregion routes
