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
SSE + WebSocket 统一广播

core 只负责把事件送到所有连接, 不知道事件内容的业务含义。
「当前状态快照」由插件通过 `register_snapshot_provider()` 提供 ——
这样 core 里不会再出现 `DeviceData` 这类业务模型 (v6 的 ConnManager 直接查了设备表)。
'''

import asyncio
import typing as t

from fastapi import WebSocket
from fastapi.encoders import jsonable_encoder
from loguru import logger as l

from core.events import bus, StreamConnectedEvent, StreamDisconnectedEvent

SnapshotProvider = t.Callable[[], t.Dict[str, t.Any]]


class ConnManager:
    '''
    连接管理器
    '''

    def __init__(self):
        self._sse_queues: set[asyncio.Queue] = set()
        self._ws_clients: set[WebSocket] = set()
        self._snapshot_providers: list[tuple[str, SnapshotProvider]] = []

    # region snapshot

    def register_snapshot_provider(self, provider: SnapshotProvider, plugin: str = 'core'):
        '''
        注册快照提供者

        新连接接入时, 所有 provider 的返回值会被合并成一份初始快照下发。

        :param provider: 无参函数, 返回要合并进快照的字典
        :param plugin: 提供方插件名 (用于卸载时清理)
        '''
        self._snapshot_providers.append((plugin, provider))
        l.debug(f'Plugin {plugin} registered a snapshot provider')

    def unregister_plugin(self, plugin: str):
        '''
        移除某插件注册的 provider
        '''
        before = len(self._snapshot_providers)
        self._snapshot_providers = [(p, f) for p, f in self._snapshot_providers if p != plugin]
        if before != len(self._snapshot_providers):
            l.debug(f'Removed snapshot provider(s) of plugin {plugin}')

    def snapshot(self) -> dict:
        '''
        聚合所有 provider 的当前快照
        '''
        result: dict = {}
        for plugin, provider in self._snapshot_providers:
            try:
                data = provider()
                if data:
                    result.update(data)
            except Exception as ex:
                l.error(f'Snapshot provider of plugin {plugin} failed: {ex}')
        return jsonable_encoder(result)

    # endregion snapshot

    @property
    def online(self) -> int:
        '''
        当前连接总数 (SSE + WS)
        '''
        return len(self._sse_queues) + len(self._ws_clients)

    # region sse

    async def sse_connect(self) -> asyncio.Queue:
        '''
        接入一个 SSE 连接
        '''
        queue: asyncio.Queue = asyncio.Queue()
        self._sse_queues.add(queue)
        l.info(f'EventStream connected, current connections: {self.online}')
        await bus.emit(StreamConnectedEvent('sse', self.online))
        await self.broadcast('online-changed', {'online': self.online})
        return queue

    async def sse_disconnect(self, queue: asyncio.Queue):
        '''
        断开一个 SSE 连接
        '''
        self._sse_queues.discard(queue)
        l.info(f'EventStream disconnected, current connections: {self.online}')
        await bus.emit(StreamDisconnectedEvent('sse', self.online))
        await self.broadcast('online-changed', {'online': self.online})

    # endregion sse

    # region ws

    async def ws_connect(self, ws: WebSocket):
        '''
        接入一个 WebSocket 连接
        '''
        self._ws_clients.add(ws)
        l.info(f'WebSocket connected, current connections: {self.online}')
        await bus.emit(StreamConnectedEvent('ws', self.online))
        await self.broadcast('online-changed', {'online': self.online})

    async def ws_disconnect(self, ws: WebSocket):
        '''
        断开一个 WebSocket 连接
        '''
        self._ws_clients.discard(ws)
        l.info(f'WebSocket disconnected, current connections: {self.online}')
        await bus.emit(StreamDisconnectedEvent('ws', self.online))
        await self.broadcast('online-changed', {'online': self.online})

    # endregion ws

    async def broadcast(self, event: str, data: dict | None = None):
        '''
        向所有连接推送一个事件

        插件在数据变更后调用它, 例如:
        ```python
        await manager.broadcast('device-changed', {'id': 'pc-1', ...})
        ```

        SSE 与 WebSocket 收到的是同一份内容, 两边不会出现语义漂移。
        '''
        payload = jsonable_encoder(data) if data is not None else None
        l.debug(f'Broadcasting event {event} to {self.online} connection(s)')

        # --- SSE ---
        stale_queues: list[asyncio.Queue] = []
        for queue in list(self._sse_queues):
            try:
                queue.put_nowait((event, payload))
            except (asyncio.QueueFull, asyncio.QueueShutDown):
                stale_queues.append(queue)
            except Exception as ex:
                l.debug(f'Error putting to SSE queue: {ex}')
                stale_queues.append(queue)
        for queue in stale_queues:
            self._sse_queues.discard(queue)

        # --- WebSocket ---
        stale_ws: list[WebSocket] = []
        for conn in list(self._ws_clients):
            try:
                await conn.send_json({'event': event, 'data': payload})
            except Exception as ex:
                l.debug(f'Failed to send WS broadcast: {ex}')
                stale_ws.append(conn)
        for conn in stale_ws:
            self._ws_clients.discard(conn)

        if stale_queues or stale_ws:
            l.debug(f'Dropped {len(stale_queues) + len(stale_ws)} stale connection(s)')


manager = ConnManager()
'''
全局连接管理器
'''
