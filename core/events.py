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
类型化事件总线

移植自 v5 的事件系统 (`main` 分支 `plugin.py`), 并修掉其中三个问题:

1. v5 的 `BaseEvent.time` 与 `request` 是**类属性**且在 import 时求值,
   所有事件实例因此共享同一个时间戳。这里改为实例属性。
2. v5 的 handler 必须 `return event`, 否则派发循环里的 `event` 会变成 `None`
   并在下一次迭代崩溃。这里改为直接修改传入的事件对象, 返回值被忽略。
3. v6 的 hook 表没有反注册入口, 插件卸载后回调仍然留在表里。
   这里提供 `unsubscribe_plugin()`。

同时支持 async handler, 并允许按事件类或字符串 id 订阅 —— 后者让插件之间不必
互相 import 就能协作。
'''

import inspect
import typing as t
from collections import defaultdict
from time import time
from traceback import format_exc

from loguru import logger as l

if t.TYPE_CHECKING:
    from fastapi import Request

EventLike = t.Union[type['BaseEvent'], str]
'''订阅目标: 事件类或事件 id 字符串'''


class BaseEvent:
    '''
    事件基类

    子类通过类属性 `id` 声明事件 id, 通过 `__init__` 携带数据。
    '''

    id: t.ClassVar[str] = 'base'
    '''事件 id'''

    interceptable: t.ClassVar[bool] = True
    '''事件是否可被拦截'''

    def __init__(self):
        self.time: float = time()
        '''事件生成时间'''

        self.interception: tuple[t.Any, int] | None = None
        '''拦截结果 (响应内容, HTTP 状态码), 未被拦截时为 None'''

        self.request: 't.Optional[Request]' = None
        '''触发该事件的请求 (如有), 由触发方设置'''

    def intercept(self, response: t.Any, code: int = 200) -> bool:
        '''
        拦截事件并提前返回

        :param response: 拦截后返回的内容
        :param code: 拦截后返回的 HTTP 状态码
        :return: 是否成功拦截 (事件不可拦截时返回 False)
        '''
        if not self.interceptable:
            l.warning(f'Event {self.id} is not interceptable, intercept() ignored')
            return False
        self.interception = (response, code)
        return True

    @property
    def intercepted(self) -> bool:
        '''
        事件是否已被拦截
        '''
        return self.interception is not None

    def __repr__(self):
        return f'<{type(self).__name__} id={self.id} intercepted={self.intercepted}>'


# region core-events


class AppStartupEvent(BaseEvent):
    '''应用启动完成 (插件已全部加载)'''
    id = 'app_startup'
    interceptable = False


class AppShutdownEvent(BaseEvent):
    '''应用关闭'''
    id = 'app_shutdown'
    interceptable = False


class APIUnsuccessfulEvent(BaseEvent):
    '''抛出 APIUnsuccessful 异常'''
    id = 'api_unsuccessful'

    def __init__(self, error: Exception):
        super().__init__()
        self.error = error


class UnhandledErrorEvent(BaseEvent):
    '''未捕获的异常'''
    id = 'unhandled_error'

    def __init__(self, error: Exception):
        super().__init__()
        self.error = error


class StreamConnectedEvent(BaseEvent):
    '''SSE / WebSocket 客户端接入'''
    id = 'stream_connected'
    interceptable = False

    def __init__(self, kind: str, online: int):
        super().__init__()
        self.kind = kind
        '''`sse` 或 `ws`'''
        self.online = online
        '''当前在线连接数'''


class StreamDisconnectedEvent(BaseEvent):
    '''SSE / WebSocket 客户端断开'''
    id = 'stream_disconnected'
    interceptable = False

    def __init__(self, kind: str, online: int):
        super().__init__()
        self.kind = kind
        self.online = online


# endregion core-events


class EventBus:
    '''
    事件总线
    '''

    def __init__(self):
        self._listeners: dict[str, list[tuple[str, t.Callable]]] = defaultdict(list)
        '''事件 id -> [(插件名, handler)]'''

    @staticmethod
    def _event_id(event: EventLike) -> str:
        if isinstance(event, str):
            return event
        return event.id

    def subscribe(self, event: EventLike, handler: t.Callable, plugin: str = 'core'):
        '''
        订阅事件

        handler 接收唯一参数 —— 事件实例, 直接修改它即可影响后续处理;
        返回值会被忽略。可以是同步或异步函数。

        :param event: 事件类或事件 id
        :param handler: 处理函数
        :param plugin: 订阅方插件名 (用于卸载时清理)
        '''
        eid = self._event_id(event)
        self._listeners[eid].append((plugin, handler))
        l.debug(f'Plugin {plugin} subscribed to event {eid}: {getattr(handler, "__name__", handler)}')

    def unsubscribe_plugin(self, plugin: str):
        '''
        移除某个插件注册的全部监听器
        '''
        removed = 0
        for eid in list(self._listeners.keys()):
            before = len(self._listeners[eid])
            self._listeners[eid] = [(p, h) for p, h in self._listeners[eid] if p != plugin]
            removed += before - len(self._listeners[eid])
            if not self._listeners[eid]:
                del self._listeners[eid]
        if removed:
            l.debug(f'Removed {removed} event listener(s) of plugin {plugin}')

    def listeners(self, event: EventLike) -> list[str]:
        '''
        列出某事件的订阅方插件名 (诊断用)
        '''
        return [p for p, _ in self._listeners.get(self._event_id(event), [])]

    async def emit(self, event: BaseEvent) -> BaseEvent:
        '''
        触发事件 (异步)

        按注册顺序依次执行监听器; 任一监听器调用 `intercept()` 后停止派发。
        监听器抛出的异常会被记录并跳过, 不影响其余监听器。

        :param event: 事件实例
        :return: 同一个事件实例 (便于 `if (await bus.emit(e)).intercepted:`)
        '''
        handlers = list(self._listeners.get(event.id, []))
        if not handlers:
            return event

        l.debug(f'Emitting event {event.id} to {len(handlers)} listener(s)')
        for plugin, handler in handlers:
            try:
                if inspect.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as ex:
                l.error(f'Plugin {plugin} failed handling event {event.id}: {ex}\n{format_exc()}')
                continue
            if event.intercepted:
                l.debug(f'Event {event.id} intercepted by plugin {plugin}')
                break
        return event

    def emit_sync(self, event: BaseEvent) -> BaseEvent:
        '''
        触发事件 (同步上下文)

        用于没有 event loop 的场景 (如 CLI)。异步监听器会被跳过并给出警告 ——
        需要在同步路径上工作的插件应当注册同步 handler。
        '''
        handlers = list(self._listeners.get(event.id, []))
        if not handlers:
            return event

        for plugin, handler in handlers:
            if inspect.iscoroutinefunction(handler):
                l.warning(f'Skipping async listener of plugin {plugin} for event {event.id} in sync emit')
                continue
            try:
                handler(event)
            except Exception as ex:
                l.error(f'Plugin {plugin} failed handling event {event.id}: {ex}\n{format_exc()}')
                continue
            if event.intercepted:
                break
        return event


bus = EventBus()
'''
全局事件总线
'''
