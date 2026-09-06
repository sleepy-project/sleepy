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
core 本体: 鉴权、事件总线、插件边界
'''

import json


from core.events import BaseEvent, EventBus


def test_root_and_health(client):
    body = client.get('/').json()
    assert body['hello'] == 'sleepy'
    assert body['version'][0] == 7
    assert client.get('/api/v1/health').status_code == 204


def test_core_serves_no_business_routes(app):
    '''
    core 是空壳: 业务路径必须来自插件, 而不是写死在 core 里

    v6 的错位就在这 —— DeviceData 模型和 /api/query 留在核心, 业务实现却在外部插件。
    '''
    from core.plugin import plugin_manager

    business_paths = {'/api/v1/status', '/api/v1/devices'}
    owned_by_plugins = {
        getattr(r, 'path', None)
        for routes in plugin_manager._plugin_routes.values()
        for r in routes
    }
    assert business_paths <= owned_by_plugins, '业务路由应当由插件注册'

    import core.models as m
    core_tables = {
        v.__tablename__ for v in vars(m).values()
        # 只看本模块里定义的表, 否则会把导入进来的 SQLModel 基类也算上
        if hasattr(v, '__tablename__') and getattr(v, '__module__', None) == m.__name__
    }
    assert core_tables == {'userdata', 'tokendata', 'plugin_kv'}, f'core 混入了业务表: {core_tables}'


def test_auth_flow(client):
    assert client.get('/api/v1/init').json()['initialized'] is True
    # 重复初始化应当被拒
    assert client.post('/api/v1/init', json={'password': 'x', 'hashed': False}).status_code == 409

    resp = client.post('/api/v1/auth/login', json={'password': 'wrong', 'hashed': False})
    assert resp.status_code == 401


def test_token_check_and_refresh(client):
    tokens = client.post('/api/v1/auth/login', json={'password': 'test-password', 'hashed': False}).json()

    resp = client.get('/api/v1/auth/check', headers={'X-Sleepy-Token': tokens['token']})
    assert resp.status_code == 200
    assert resp.json()['type'] == 'web'

    assert client.get('/api/v1/auth/check', headers={'X-Sleepy-Token': 'nope'}).status_code == 403

    refreshed = client.post('/api/v1/auth/refresh', json={
        'token': tokens['token'], 'refresh_token': tokens['refresh_token']
    })
    assert refreshed.status_code == 200
    assert refreshed.json()['token'] != tokens['token']


def test_bearer_header_accepted(client, device_secret):
    resp = client.put(
        '/api/v1/devices/bearer-test',
        json={'name': 'B', 'status': 's'},
        headers={'Authorization': f'Bearer {device_secret}'}
    )
    assert resp.status_code == 200


def test_device_token_cannot_set_status(client, device_secret):
    '''
    scope 隔离: 设备 token 只能写设备, 不能改全局状态
    '''
    resp = client.put('/api/v1/status', json={'status': 1}, headers={'X-Sleepy-Token': device_secret})
    assert resp.status_code == 401


def test_sse_payload_is_json_not_python_repr():
    '''
    SSE 的 data 必须是 JSON —— 直接把 dict 交给 sse_starlette 会发出
    Python repr (单引号), 客户端 JSON.parse 必然失败。v6 就是这样。

    刻意不通过 HTTP 测: `/api/v1/events` 是无限流, TestClient 会挂在上面。
    '''
    from core.app import json_dumps

    payload = json_dumps({'time': 1.0, 'devices': [{'name': '我的电脑', 'using': True}]})
    assert "'" not in payload, f'输出了 Python repr 而不是 JSON: {payload}'
    parsed = json.loads(payload)          # 解析失败即测试失败
    assert parsed['devices'][0]['name'] == '我的电脑'
    assert parsed['devices'][0]['using'] is True


async def test_broadcast_reaches_sse_queue():
    '''
    广播要真的进到 SSE 连接的队列里
    '''
    from core.broadcast import ConnManager

    mgr = ConnManager()
    queue = await mgr.sse_connect()
    queue.get_nowait()                     # 接入时自带的 online-changed

    await mgr.broadcast('device-changed', {'id': 'pc-1'})
    event, data = queue.get_nowait()
    assert event == 'device-changed'
    assert data == {'id': 'pc-1'}

    await mgr.sse_disconnect(queue)
    assert mgr.online == 0


# region event-bus


async def test_event_bus_interception():
    bus = EventBus()

    class Ping(BaseEvent):
        id = 'ping'

    seen = []
    bus.subscribe(Ping, lambda e: seen.append('first') or e.intercept('stop', 403), plugin='a')
    bus.subscribe(Ping, lambda e: seen.append('second'), plugin='b')

    evt = await bus.emit(Ping())
    assert evt.intercepted
    assert evt.interception == ('stop', 403)
    assert seen == ['first'], '拦截之后不应继续派发'


async def test_event_bus_survives_handler_error():
    bus = EventBus()

    class Ping(BaseEvent):
        id = 'ping'

    def boom(e):
        raise RuntimeError('handler exploded')

    seen = []
    bus.subscribe(Ping, boom, plugin='bad')
    bus.subscribe(Ping, lambda e: seen.append('ok'), plugin='good')

    await bus.emit(Ping())
    assert seen == ['ok'], '一个监听器出错不应影响其余监听器'


async def test_event_bus_handler_need_not_return_event():
    '''
    v5 的派发循环是 `event = handler(...)`, handler 忘记 return 就会让链路崩掉。
    v7 直接改传入的事件对象, 返回值忽略。
    '''
    bus = EventBus()

    class Ping(BaseEvent):
        id = 'ping'
        def __init__(self):
            super().__init__()
            self.value = 0

    bus.subscribe(Ping, lambda e: setattr(e, 'value', 1), plugin='a')
    bus.subscribe(Ping, lambda e: setattr(e, 'value', e.value + 1), plugin='b')

    evt = await bus.emit(Ping())
    assert evt.value == 2


async def test_unsubscribe_plugin():
    bus = EventBus()

    class Ping(BaseEvent):
        id = 'ping'

    seen = []
    bus.subscribe(Ping, lambda e: seen.append(1), plugin='doomed')
    bus.unsubscribe_plugin('doomed')
    await bus.emit(Ping())
    assert seen == [], '插件卸载后其监听器不应再被调用'


def test_event_instances_have_distinct_timestamps():
    '''
    v5 把 time 写成类属性并在 import 时求值, 所有事件共享同一个时间戳
    '''
    class Ping(BaseEvent):
        id = 'ping'

    a, b = Ping(), Ping()
    assert a.time > 0 and b.time > 0
    assert a.interception is None and b.interception is None
    a.intercept('x')
    assert b.interception is None, '拦截状态不应在实例之间泄漏'


# endregion event-bus
