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
访问统计
'''

import sys
import threading

import pytest
from sqlmodel import select

from core import db
from core.plugin import plugin_manager


@pytest.fixture
def metrics(client):
    '''
    metrics 插件实例 (依赖 client 以确保应用已完成加载)
    '''
    plugin = plugin_manager.get_plugin('metrics')
    assert plugin is not None, 'metrics 插件未加载'
    return plugin


@pytest.fixture
def models():
    '''
    插件内部的表模型

    插件是按文件路径动态加载的, 没有稳定的 import 路径, 从 sys.modules 取。
    '''
    module = sys.modules['sleepy_plugin.metrics']
    return module.MetricsData, module.MetricsMeta


@pytest.fixture(autouse=True)
def reset_metrics(metrics, models):
    '''
    每个用例前清空计数, 否则用例之间会看到彼此的请求
    '''
    MetricsData, _ = models
    metrics._pending.clear()
    with db.session() as sess:
        for record in sess.exec(select(MetricsData)).all():
            sess.delete(record)
        sess.commit()
    yield


def test_counts_whitelisted_paths(client):
    for _ in range(3):
        client.get('/')
    assert client.get('/api/v1/metrics').json()['total'].get('/') == 3


def test_ignores_paths_outside_allow_list(client):
    client.get('/definitely-not-in-allow-list')
    total = client.get('/api/v1/metrics').json()['total']
    assert '/definitely-not-in-allow-list' not in total


def test_v5_response_shape(client):
    '''
    v5 的 /api/metrics 形状: success/enabled/time/time_local/timezone + 五档计数
    '''
    body = client.get('/api/metrics').json()
    assert body['success'] is True
    assert body['enabled'] is True
    assert set(body) >= {
        'time', 'time_local', 'timezone',
        'daily', 'weekly', 'monthly', 'yearly', 'total'
    }


def test_counts_are_buffered_in_memory(client, metrics):
    '''
    计数先进内存再批量落库 —— 这正是相对 v5「每请求一次 UPDATE」的改动
    '''
    metrics._pending.clear()
    client.get('/')
    assert metrics._pending.get('/') == 1, '请求应当先累加在内存里'

    metrics.flush()
    assert not metrics._pending, 'flush 之后内存计数应当清空'


def test_flush_requeues_on_failure(metrics, monkeypatch):
    '''
    落库失败时计数退回内存等下一轮, 不能静默丢掉
    '''
    metrics._pending.clear()
    metrics.record('/')
    metrics.record('/')

    def boom(*args, **kwargs):
        raise RuntimeError('db is down')

    monkeypatch.setattr(db, 'session', boom)
    metrics.flush()

    assert metrics._pending.get('/') == 2, '落库失败的计数应当被退回'


def test_concurrent_recording_is_not_lost(metrics):
    threads = [threading.Thread(target=lambda: [metrics.record('/') for _ in range(100)]) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert metrics._pending.get('/') == 800


def test_rollover_resets_daily_but_keeps_total(client, models):
    '''
    跨天时 daily 清零、total 保留

    靠标记字符串比对实现, 不依赖定时任务 —— 服务停机期间跨天也能正确滚动。
    '''
    _, MetricsMeta = models

    for _ in range(2):
        client.get('/')
    client.get('/api/v1/metrics')          # 触发 flush 落库

    with db.session() as sess:
        meta = sess.exec(select(MetricsMeta)).first()
        meta.today = '1970-1-1'            # 伪造成「上次计数发生在很久以前」
        sess.add(meta)
        sess.commit()

    body = client.get('/api/v1/metrics').json()
    assert body['daily'].get('/', 0) == 0, '跨天后 daily 应当清零'
    assert body['total'].get('/') == 2, 'total 不应被清零'


def test_disabled_reports_v5_not_enabled_shape(client, metrics):
    '''
    统计关闭时, v5 客户端要收到它认得的「未启用」响应而不是错误
    '''
    original = metrics._config_instance.enabled
    metrics._config_instance.enabled = False
    try:
        assert client.get('/api/metrics').json() == {'success': True, 'enabled': False}
        assert client.get('/api/v1/metrics').json() == {'success': True, 'enabled': False}
    finally:
        metrics._config_instance.enabled = original


def test_timezone_fallback_survives_missing_tzdata(metrics):
    '''
    时区不可用时要退回 timezone.utc

    不能退回 ZoneInfo('UTC'): Windows 没有系统级 IANA 时区库, 缺 tzdata 时
    连 ZoneInfo('UTC') 都会抛异常, 兜底本身会把服务打成 500。
    '''
    from datetime import datetime

    original_tz, original_name = metrics._tz, metrics._config_instance.timezone
    metrics._tz = None
    metrics._config_instance.timezone = 'Not/AZone'
    try:
        assert datetime.now(metrics.tz).utcoffset().total_seconds() == 0
    finally:
        metrics._tz, metrics._config_instance.timezone = original_tz, original_name
