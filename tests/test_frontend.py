# Copyright (C) 2026 sleepy-project
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
前端静态资源服务与 SPA 回落
'''

import pytest

from core.plugin import plugin_manager


@pytest.fixture
def frontend(client):
    plugin = plugin_manager.get_plugin('frontend')
    assert plugin is not None, 'frontend 插件未加载'
    return plugin


def test_index_is_served(client, frontend):
    resp = client.get('/')
    assert resp.status_code == 200
    assert 'FRONTEND-INDEX' in resp.text, '前端应当接管首页'


def test_spa_fallback(client, frontend):
    '''
    前端路由在服务端没有对应文件, 应回落到 index.html 交给前端路由器
    '''
    resp = client.get('/login')
    assert resp.status_code == 200
    assert 'FRONTEND-INDEX' in resp.text


def test_real_files_are_served(client, frontend):
    assert client.get('/assets/app.css').status_code == 200
    resp = client.get('/robots.txt')
    assert resp.status_code == 200
    assert 'User-agent' in resp.text


@pytest.mark.parametrize('path', [
    '/api/v1/status',
    '/api/v1/metrics',
    '/api/v1/plugins',
    '/api/status/query',
    '/api/meta',
    '/docs',
])
def test_catch_all_yields_to_real_routes(client, frontend, path):
    '''
    catch-all 绝不能吃掉真实接口

    插件按名称排序加载, frontend 排在 metrics / status 之前。若 SPA 回落
    按常规顺序注册, 这些接口会全部变成返回 HTML 的 200。
    '''
    assert client.get(path).status_code in (200, 204), f'{path} 被 catch-all 抢走了'


def test_unknown_api_path_is_json_404(client, frontend):
    '''
    拼错的 API 路径要返回 404 JSON, 而不是一个 200 的 HTML 页面 ——
    后者会让客户端极难排查。
    '''
    resp = client.get('/api/v1/definitely-not-a-route')
    assert resp.status_code == 404
    assert resp.headers['content-type'].startswith('application/json')


def test_plugin_reports_availability(frontend):
    assert frontend.is_available() is True
    assert (frontend.dist_path() / 'index.html').is_file()


def test_config_is_available_during_on_load():
    '''
    配置必须在 on_load 之前解析好

    frontend 正是靠 on_load 里读配置来决定要不要注册路由的; upstream 的
    da439e5 把配置解析放在 on_load 之后, 会让这个插件直接加载失败。
    '''
    for name in plugin_manager.get_loaded_plugins():
        plugin = plugin_manager.get_plugin(name)
        if plugin and plugin._config_schema is not None:
            assert plugin._config_instance is not None, f'{name} 的配置未解析'
