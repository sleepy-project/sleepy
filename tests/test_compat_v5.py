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
v5 客户端兼容性

这里的请求体是从 main 分支 `client/` 下的真实脚本里逐字抄来的, 不是构造的样例。
v7 的验收判据就是这些用例: 未经修改的旧客户端, 只把 SECRET 换成面板签发的
device token, 就应当能正常上报。
'''


def test_powershell_client(client, device_secret):
    '''
    `client/Sleepy.Powershell.ps1` —— Send-DeviceStatus 的请求体
    '''
    resp = client.post('/api/device/set', json={
        'secret': device_secret,
        'id': 'windows-pc',
        'show_name': '我的 Windows',
        'using': True,
        'status': 'JetBrains Rider'
    })
    assert resp.status_code == 200
    assert resp.json() == {'success': True}

    devices = client.get('/api/v1/devices').json()
    assert len(devices) == 1
    assert devices[0]['id'] == 'windows-pc'
    # v5 的 show_name 要映射成 v7 的 name
    assert devices[0]['name'] == '我的 Windows'
    assert devices[0]['status'] == 'JetBrains Rider'
    assert devices[0]['using'] is True


def test_hyprland_shell_client(client, device_secret):
    '''
    `client/linux_device_hyprland.sh` —— curl -X POST 的 json_data
    '''
    resp = client.post('/api/device/set', json={
        'secret': device_secret,
        'id': 'linux-hypr',
        'show_name': 'Arch 台式',
        'using': True,
        'status': 'firefox'
    })
    assert resp.status_code == 200
    assert resp.json()['success'] is True


def test_get_form_with_extra_fields(client, device_secret):
    '''
    GET 形态, 并且额外的 query 参数要落进 fields
    '''
    resp = client.get('/api/device/set', params={
        'secret': device_secret,
        'id': 'phone',
        'show_name': 'Pixel',
        'using': 'true',
        'app_name': 'Chrome',   # v5 更旧的字段名
        'battery': '88'
    })
    assert resp.status_code == 200

    device = next(d for d in client.get('/api/v1/devices').json() if d['id'] == 'phone')
    # app_name 应当映射成 status
    assert device['status'] == 'Chrome'
    # 未被识别的参数进 fields, 且不含 secret
    assert device['fields'] == {'battery': '88'}
    assert 'secret' not in device['fields']


def test_using_accepts_v5_string_forms(client, device_secret):
    '''
    v5 客户端的 using 可能是字符串 —— shell 脚本传的是裸 true/false
    '''
    for raw, expected in (('true', True), ('false', False), ('1', True), ('0', False)):
        client.get('/api/device/set', params={
            'secret': device_secret, 'id': 'boolcheck', 'show_name': 'B', 'using': raw, 'status': 's'
        })
        device = next(d for d in client.get('/api/v1/devices').json() if d['id'] == 'boolcheck')
        assert device['using'] is expected, f'using={raw!r} should map to {expected}'


def test_wrong_secret_rejected(client):
    resp = client.post('/api/device/set', json={
        'secret': 'definitely-not-a-token',
        'id': 'evil', 'show_name': 'x', 'using': True, 'status': 'y'
    })
    assert resp.status_code == 401


def test_missing_secret_rejected(client):
    resp = client.post('/api/device/set', json={'id': 'x', 'show_name': 'x'})
    assert resp.status_code == 401


def test_malformed_json_is_not_masked(client):
    '''
    body 有内容但不是合法 JSON 时, 必须报 400 而不是回退成「Missing secret」——
    静默回退会把真正的原因藏起来, 让人以为是鉴权问题。
    '''
    resp = client.post(
        '/api/device/set',
        content=b'{"secret": "abc", broken',
        headers={'Content-Type': 'application/json'}
    )
    assert resp.status_code == 400
    assert 'JSON' in resp.json()['detail']


def test_status_query_returns_v5_shape(client, device_secret):
    '''
    v5 的 /api/status/query 返回的 status 是完整对象, device 是以 id 为键的字典
    '''
    client.post('/api/device/set', json={
        'secret': device_secret, 'id': 'pc-1', 'show_name': 'PC', 'using': True, 'status': 'VSCode'
    })
    body = client.get('/api/status/query').json()

    assert body['success'] is True
    assert isinstance(body['status'], int)
    assert body['info']['name']          # 展示文案要还原出来
    assert 'pc-1' in body['device']
    assert body['device']['pc-1']['show_name'] == 'PC'
    assert body['device']['pc-1']['status'] == 'VSCode'


def test_status_list_and_set(client, admin_headers, device_secret):
    presets = client.get('/api/status/list').json()
    assert len(presets) >= 2

    resp = client.get('/api/status/set', params={'secret': admin_headers['X-Sleepy-Token'], 'status': 1})
    assert resp.status_code == 200
    assert client.get('/api/status/query').json()['status'] == 1

    # 设备 token 不能改全局状态
    resp = client.get('/api/status/set', params={'secret': device_secret, 'status': 0})
    assert resp.status_code == 401


def test_device_remove_and_clear(client, admin_headers, device_secret):
    client.post('/api/device/set', json={
        'secret': device_secret, 'id': 'tmp-1', 'show_name': 'T', 'using': True, 'status': 's'
    })
    resp = client.get('/api/device/remove', params={'secret': device_secret, 'id': 'tmp-1'})
    assert resp.status_code == 200

    # v5 行为: 设备不存在也返回成功
    resp = client.get('/api/device/remove', params={'secret': device_secret, 'id': 'never-existed'})
    assert resp.status_code == 200

    resp = client.get('/api/device/clear', params={'secret': admin_headers['X-Sleepy-Token']})
    assert resp.status_code == 200
    assert client.get('/api/v1/devices').json() == []


def test_private_mode_restored(client, admin_headers, device_secret):
    '''
    隐私模式是 v5 有、v6 删掉 (d54d0c5) 的功能; issue #143 说明仍有人在用
    '''
    client.post('/api/device/set', json={
        'secret': device_secret, 'id': 'pc-1', 'show_name': 'PC', 'using': True, 'status': 'x'
    })
    assert client.get('/api/status/query').json()['device']

    client.get('/api/device/private', params={'secret': admin_headers['X-Sleepy-Token'], 'private': 'true'})
    assert client.get('/api/status/query').json()['device'] == {}

    client.get('/api/device/private', params={'secret': admin_headers['X-Sleepy-Token'], 'private': 'false'})
    assert client.get('/api/status/query').json()['device']
