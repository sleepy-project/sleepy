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
测试夹具

必须在任何 `core.*` 被 import 之前设置好数据库路径 —— `core.config` 在导入期
就完成配置解析, 之后再改环境变量已经来不及。
'''

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_db_fd, _db_path = tempfile.mkstemp(suffix='.db', prefix='sleepy-test-')
os.close(_db_fd)
os.environ['SLEEPY_DATABASE'] = f'sqlite:///{_db_path}'
os.environ['SLEEPY_LOG_LEVEL'] = 'WARNING'
os.environ['SLEEPY_LOG_FILE'] = ''

import pytest  # noqa: E402

TEST_PASSWORD = 'test-password'


@pytest.fixture(scope='session')
def app():
    from core.app import app as fastapi_app
    return fastapi_app


@pytest.fixture(scope='session')
def client(app):
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope='session')
def admin_headers(client) -> dict:
    '''
    完成初始化并登录, 返回带管理 token 的请求头
    '''
    client.post('/api/v1/init', json={'password': TEST_PASSWORD, 'hashed': False})
    resp = client.post('/api/v1/auth/login', json={'password': TEST_PASSWORD, 'hashed': False})
    assert resp.status_code == 200, resp.text
    return {'X-Sleepy-Token': resp.json()['token']}


@pytest.fixture(scope='session')
def device_secret(client, admin_headers) -> str:
    '''
    签发一个设备 token —— 这就是要填进 v5 客户端 SECRET 变量的值
    '''
    resp = client.post('/api/v1/tokens', json={'name': 'pytest-device'}, headers=admin_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()['token']


@pytest.fixture(autouse=True)
def clean_devices(client, admin_headers):
    '''
    每个用例开始前清空设备表, 避免用例之间互相影响
    '''
    client.delete('/api/v1/devices', headers=admin_headers)
    yield


def pytest_sessionfinish(session, exitstatus):
    try:
        os.unlink(_db_path)
    except OSError:
        pass
