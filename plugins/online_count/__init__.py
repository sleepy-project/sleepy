# coding: utf-8

from logging import getLogger
from datetime import datetime

import pytz
from pydantic import BaseModel

from utils import get_path
import plugin as pl

l = getLogger(__name__)


class CountConfig(BaseModel):
    refresh: int = 150000
    '''前端刷新秒数'''


p = pl.Plugin(
    name='online_count',
    require_version_min=(5, 0, 0),
    require_version_max=(6, 0, 0),
    config=CountConfig
)

c: CountConfig = p.config

# 时区处理
tz = pytz.timezone(p.global_config.main.timezone)


def get_today():
    return datetime.now(tz).date().isoformat()  # '2025-12-21'


class Stats:
    current: int = 0      # 主程序 SSE 连接数（访问主页的人）

    peak_all_time: int = 0

    peak_today: int = 0
    today_is: str = get_today()


stats = Stats()

# ==================== 初始化 & 数据持久化 ====================


def init():
    global stats

    # 加载前端 JS（负责点击刷新）
    try:
        path = get_path('plugins/online_count/inject.js')
        with open(path, 'r', encoding='utf-8') as f:
            js_content = f.read()
        p.add_index_inject(f'<script>{
            js_content.replace('114514', str(c.refresh))
        }</script>')
        l.info('Online Count plugin: inject.js loaded')
    except Exception as e:
        l.error(f'无法加载 inject.js: {e}')

    # 恢复持久化数据
    data = p.data
    stats.peak_all_time = data.get('peak_all_time', 0)

    today = get_today()
    if data.get('today_date') != today:
        stats.peak_today = stats.current
        stats.today_is = today
    else:
        stats.peak_today = data.get('peak_today', 0)
        stats.today_is = today

    save_stats()
    l.info('Online Count plugin loaded!')


p.init = init


def save_stats():
    with p.data_context() as data:
        data['peak_all_time'] = stats.peak_all_time
        data['peak_today'] = stats.peak_today
        data['today_date'] = stats.today_is


def update_peak(global_new: int | None = None, plugin_new: int | None = None):
    global stats
    today = get_today()

    if stats.today_is != today:  # 新的一天
        stats.peak_today = stats.current
        stats.today_is = today

    if global_new is not None:
        stats.peak_today = max(stats.peak_today, global_new)
        stats.peak_all_time = max(stats.peak_all_time, global_new)


    save_stats()

# ==================== 全局在线人数统计（主程序 SSE） ====================


@p.event_handler(pl.StreamConnectedEvent)
def on_global_connect(event: pl.StreamConnectedEvent, request):
    stats.current += 1
    l.info(f'全局在线 +1 → {stats.current}')
    update_peak(global_new=stats.current)
    return event


@p.event_handler(pl.StreamDisconnectedEvent)
def on_global_disconnect(event: pl.StreamDisconnectedEvent, request):
    stats.current = max(0, stats.current - 1)
    l.info(f'全局在线 -1 → {stats.current}')
    update_peak(global_new=stats.current)
    return event

# ==================== 前端卡片 ====================


@p.index_card('online-count')
def index_card():
    today = get_today()
    return f'''
<div style="line-height:1.8; font-family: system-ui, sans-serif;">
    <strong>当前在线</strong>: <b id="count-global">{stats.current}</b> 人<br/>

    <strong>今日最高 ({today})</strong>: <b id="peak-today-global">{stats.peak_today}</b> 人<br/>

    <strong>历史最高</strong>: <b id="peak-all-global">{stats.peak_all_time}</b> 人<br/>

    <a href="javascript:refreshOnlineCount()" style="font-size:0.9em; color:#0066cc; cursor:pointer;">
        🔄 刷新数据
    </a>
    <span id="update-status" style="margin-left:10px; font-size:0.8em; color:#666;"></span>
</div>
'''[1:-1]

# ==================== 手动刷新 API ====================


@p.route('/')
def get_count_api():
    """供前端 JS 调用的 JSON 接口"""
    return {
        'current': stats.current,
        'peak_today': stats.peak_today,
        'peak_all_time': stats.peak_all_time,
        'today': stats.today_is
    }
