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
device —— 设备状态上报与查询

对外暴露的事件 (其他插件可按字符串 id 订阅, 无需 import 本模块):

- `device_set`      设备信息即将写入, 可拦截、可改写字段
- `device_removed`  设备已被移除
- `device_cleared`  设备已被清空
'''

import typing as t
from time import time

from fastapi import Security
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy import JSON
from sqlmodel import Field, Session, SQLModel, select

from core import db
from core import errors as e
from core.auth import AUTH_ACCESS_PREFIX, DEVICE_PREFIX, SessionDep, TokenDep
from core.events import BaseEvent
from core.plugin import PluginBase, PluginMetadata

PLUGIN_KEY = 'device'
PRIVATE_KV_KEY = 'private_mode'


# region models


class DeviceData(SQLModel, table=True):
    '''
    设备数据
    '''
    __tablename__: str = 'devicedata'

    id: str = Field(primary_key=True, index=True)
    name: str = Field()
    status: str = Field(default='')
    using: bool = Field(default=True)
    fields: t.Dict[str, t.Any] = Field(default={}, sa_type=JSON)
    last_updated: float = Field(default_factory=time)


class DeviceSetRequest(BaseModel):
    name: str | None = None
    status: str | None = None
    using: bool | None = None
    fields: t.Dict[str, t.Any] | None = None


class DeviceResponse(BaseModel):
    id: str
    name: str
    status: str
    using: bool
    fields: t.Dict[str, t.Any]
    last_updated: float


class PrivateModeRequest(BaseModel):
    private: bool


# endregion models

# region events


class DeviceSetEvent(BaseEvent):
    '''
    设备信息即将写入

    监听器可以直接修改 `name` / `status` / `using` / `fields`,
    也可以 `intercept()` 阻止写入。
    '''
    id = 'device_set'

    def __init__(self, device_id: str, name: str, status: str, using: bool, fields: dict):
        super().__init__()
        self.device_id = device_id
        self.name = name
        self.status = status
        self.using = using
        self.fields = fields


class DeviceRemovedEvent(BaseEvent):
    '''设备已被移除'''
    id = 'device_removed'
    interceptable = False

    def __init__(self, device_id: str):
        super().__init__()
        self.device_id = device_id


class DeviceClearedEvent(BaseEvent):
    '''设备已被清空'''
    id = 'device_cleared'
    interceptable = False

    def __init__(self, count: int):
        super().__init__()
        self.count = count


# endregion events


class Plugin(PluginBase):

    def __init__(self, metadata: PluginMetadata):
        super().__init__(metadata)
        self.register_model(DeviceData)

        self.exports = {
            'set_device': self.set_device,
            'remove_device': self.remove_device,
            'clear_devices': self.clear_devices,
            'list_devices': self.list_devices,
            'set_private': self.set_private,
            'is_private': self.is_private,
            'DeviceData': DeviceData,
            'DeviceSetEvent': DeviceSetEvent,
        }

    def on_load(self):
        self.register_snapshot_provider(self._snapshot)

        write_auth = TokenDep((DEVICE_PREFIX, AUTH_ACCESS_PREFIX))
        admin_auth = TokenDep((AUTH_ACCESS_PREFIX,))

        self.add_route('/api/v1/devices', self._route_list, ['GET'],
                       tags=['device'], name='List devices', response_model=list[DeviceResponse])
        self.add_route('/api/v1/devices/{device_id}', self._route_set, ['PUT'],
                       tags=['device'], name='Report device status',
                       dependencies=[Security(write_auth)])
        self.add_route('/api/v1/devices/{device_id}', self._route_remove, ['DELETE'],
                       tags=['device'], name='Remove a device',
                       dependencies=[Security(write_auth)])
        self.add_route('/api/v1/devices', self._route_clear, ['DELETE'],
                       tags=['device'], name='Remove all devices',
                       dependencies=[Security(admin_auth)])
        # 隐私模式刻意不放在 /api/v1/devices/ 下: 那样会被 `{device_id}` 抢先匹配,
        # 变成给一台叫 "private" 的设备上报。
        self.add_route('/api/v1/privacy', self._route_private, ['PUT'],
                       tags=['device'], name='Set private mode',
                       dependencies=[Security(admin_auth)])
        self.add_route('/api/v1/privacy', self._route_privacy_get, ['GET'],
                       tags=['device'], name='Get private mode')

    # region snapshot

    def _snapshot(self) -> dict:
        '''
        广播快照: 隐私模式下不暴露设备列表
        '''
        with db.session() as sess:
            if self.is_private(sess):
                return {'devices': [], 'private': True}
            devices = self.list_devices(sess)
            return {
                'devices': [d.model_dump() for d in devices],
                'private': False
            }

    # endregion snapshot

    # region private-mode

    def is_private(self, sess: Session) -> bool:
        '''
        查询隐私模式是否开启
        '''
        from core.models import PluginKV
        record = sess.get(PluginKV, (PLUGIN_KEY, PRIVATE_KV_KEY))
        if not record:
            return False
        return bool(record.value.get('enabled', False))

    def set_private(self, sess: Session, enabled: bool) -> bool:
        '''
        设置隐私模式

        v5 有这个功能, v6 在 d54d0c5 里把它删掉了 —— 但 issue #143 说明仍有人在用。
        '''
        from core.models import PluginKV
        record = sess.get(PluginKV, (PLUGIN_KEY, PRIVATE_KV_KEY))
        if record:
            record.value = {'enabled': enabled}
            record.updated = time()
        else:
            record = PluginKV(plugin=PLUGIN_KEY, key=PRIVATE_KV_KEY, value={'enabled': enabled})
        sess.add(record)
        sess.commit()
        return enabled

    # endregion private-mode

    # region data-access

    def list_devices(self, sess: Session) -> list[DeviceData]:
        '''
        列出所有设备 (按最后更新时间倒序)
        '''
        return list(sess.exec(select(DeviceData).order_by(DeviceData.last_updated.desc())).all())  # type: ignore[attr-defined]

    def _write_device(
        self,
        sess: Session,
        device_id: str,
        name: str,
        status: str,
        using: bool,
        fields: dict
    ) -> DeviceData:
        record = sess.get(DeviceData, device_id)
        if record:
            record.name = name
            record.status = status
            record.using = using
            record.fields = fields
            record.last_updated = time()
        else:
            record = DeviceData(
                id=device_id, name=name, status=status,
                using=using, fields=fields, last_updated=time()
            )
        sess.add(record)
        sess.commit()
        sess.refresh(record)
        return record

    async def set_device(
        self,
        sess: Session,
        device_id: str,
        name: str | None = None,
        status: str | None = None,
        using: bool | None = None,
        fields: dict | None = None
    ) -> DeviceData:
        '''
        写入设备状态 (会触发 `device_set` 事件)

        未提供的字段沿用已有记录的值, 便于客户端只上报变化的部分。
        '''
        existing = sess.get(DeviceData, device_id)
        evt = DeviceSetEvent(
            device_id=device_id,
            name=name if name is not None else (existing.name if existing else device_id),
            status=status if status is not None else (existing.status if existing else ''),
            using=using if using is not None else (existing.using if existing else True),
            fields=fields if fields is not None else (dict(existing.fields) if existing else {})
        )
        await self.emit(evt)
        if evt.intercepted:
            raise e.APIUnsuccessful(evt.interception[1], str(evt.interception[0]))  # type: ignore[index]

        record = await run_in_threadpool(
            self._write_device, sess, evt.device_id, evt.name, evt.status, evt.using, evt.fields
        )
        await self.broadcast('device-changed', {'id': record.id, **self._snapshot()})
        return record

    async def remove_device(self, sess: Session, device_id: str) -> bool:
        '''
        移除设备

        与 v5 行为一致: 设备不存在也算成功, 避免客户端反复重试。
        '''
        record = sess.get(DeviceData, device_id)
        if record:
            sess.delete(record)
            sess.commit()
        await self.emit(DeviceRemovedEvent(device_id))
        await self.broadcast('device-changed', self._snapshot())
        return record is not None

    async def clear_devices(self, sess: Session) -> int:
        '''
        清空所有设备
        '''
        devices = self.list_devices(sess)
        for record in devices:
            sess.delete(record)
        sess.commit()
        await self.emit(DeviceClearedEvent(len(devices)))
        await self.broadcast('device-changed', self._snapshot())
        return len(devices)

    # endregion data-access

    # region routes

    async def _route_list(self, sess: SessionDep):
        if self.is_private(sess):
            return []
        return self.list_devices(sess)

    async def _route_set(self, sess: SessionDep, device_id: str, req: DeviceSetRequest):
        record = await self.set_device(
            sess, device_id,
            name=req.name, status=req.status, using=req.using, fields=req.fields
        )
        return record

    async def _route_remove(self, sess: SessionDep, device_id: str):
        removed = await self.remove_device(sess, device_id)
        return {'removed': removed}

    async def _route_clear(self, sess: SessionDep):
        count = await self.clear_devices(sess)
        return {'removed': count}

    async def _route_private(self, sess: SessionDep, req: PrivateModeRequest):
        enabled = await run_in_threadpool(self.set_private, sess, req.private)
        await self.broadcast('device-changed', self._snapshot())
        return {'private': enabled}

    async def _route_privacy_get(self, sess: SessionDep):
        return {'private': self.is_private(sess)}

    # endregion routes
