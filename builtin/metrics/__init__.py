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
metrics —— 访问统计

补回 v5 有、v6 整个丢掉的功能, 计数口径与 v5 保持一致 (daily / weekly /
monthly / yearly / total)。

与 v5 的两点不同:

1. **时区用标准库 zoneinfo**, 不再依赖 pytz。
2. **计数先累加在内存里, 定期批量落库**。v5 每个请求都要 UPDATE + commit 一次,
   在设备每 30 秒上报一次、多设备并发的情况下, 写盘量远超实际数据量。
   进程退出前会 flush, 所以正常关闭不丢数据; 崩溃时最多丢一个 flush 周期。

统计口径沿用 v5 的白名单: 只记录 allow_list 里的路径。没有白名单的话,
任意 404 路径都会在表里建一行, 很容易被刷爆。
'''

import asyncio
import threading
import typing as t
from datetime import datetime, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Request, Response
from loguru import logger as l
from pydantic import BaseModel
from sqlmodel import Field, Session, SQLModel, select

from core import db
from core.auth import SessionDep
from core.plugin import PluginBase, PluginMetadata

# region models


class MetricsData(SQLModel, table=True):
    '''
    每个路径的访问计数
    '''
    __tablename__: str = 'metrics'

    path: str = Field(primary_key=True, index=True)
    daily: int = Field(default=0)
    weekly: int = Field(default=0)
    monthly: int = Field(default=0)
    yearly: int = Field(default=0)
    total: int = Field(default=0)


class MetricsMeta(SQLModel, table=True):
    '''
    滚动标记 (单行)

    记录「上一次计数属于哪一天/周/月/年」。请求进来时对比标记, 不一致就把对应
    的计数清零 —— 这样不需要定时任务, 服务停机期间跨天也能正确滚动。
    '''
    __tablename__: str = 'metrics_meta'

    id: int = Field(default=0, primary_key=True)
    today: str = Field(default='')
    week: str = Field(default='')
    month: str = Field(default='')
    year: str = Field(default='')


class MetricsConfig(BaseModel):
    '''
    metrics 插件配置 (`plugin.metrics`)
    '''

    enabled: bool = True
    '''是否启用统计'''

    timezone: str = 'Asia/Shanghai'
    '''计算「今天」用的时区'''

    flush_interval: int = 30
    '''内存计数落库的间隔 (秒)'''

    allow_list: list[str] = [
        '/',
        '/api/v1/status',
        '/api/v1/status/presets',
        '/api/v1/devices',
        '/api/v1/events',
        '/api/v1/ws',
        '/api/v1/metrics',
        '/api/status/query',
        '/api/status/list',
        '/api/status/set',
        '/api/device/set',
        '/api/device/remove',
        '/api/device/clear',
        '/api/device/private',
        '/api/metrics',
        '/api/meta',
        '/robots.txt',
        '/favicon.ico',
    ]
    '''
    计入统计的路径白名单

    不做白名单的话, 任意 404 路径都会在表里建一行。
    '''


# endregion models


class Plugin(PluginBase):

    def __init__(self, metadata: PluginMetadata):
        super().__init__(metadata)
        self.register_model(MetricsData)
        self.register_model(MetricsMeta)
        self.register_config(MetricsConfig)

        self._pending: dict[str, int] = {}
        '''尚未落库的计数增量'''
        self._pending_lock = threading.Lock()

        self._flush_task: asyncio.Task | None = None
        self._tz: tzinfo | None = None

        self.exports = {
            'summary': self.summary,
            'record': self.record,
            'flush': self.flush,
            'MetricsData': MetricsData,
        }

    @property
    def config(self) -> MetricsConfig:
        return t.cast(MetricsConfig, self.get_config())

    @property
    def tz(self) -> tzinfo:
        '''
        统计用时区

        兜底用 `timezone.utc` 而不是 `ZoneInfo('UTC')`: Windows 没有系统级的
        IANA 时区库, 缺少 tzdata 包时连 `ZoneInfo('UTC')` 都会抛
        ZoneInfoNotFoundError, 兜底本身把服务打成 500。
        tzdata 已列入依赖, 这条分支只在依赖缺失或时区名写错时生效。
        '''
        if self._tz is None:
            try:
                self._tz = ZoneInfo(self.config.timezone)
            except (ZoneInfoNotFoundError, ValueError) as ex:
                l.warning(f'Timezone {self.config.timezone!r} unavailable ({ex}), falling back to UTC')
                self._tz = timezone.utc
        return self._tz

    def on_load(self):
        self.add_route('/api/v1/metrics', self._route_metrics, ['GET'],
                       tags=['metrics'], name='Access metrics')

    async def on_startup(self):
        if self.config.enabled:
            self._flush_task = asyncio.create_task(self._flush_loop())

    async def on_shutdown(self):
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None
        # 退出前把内存里剩下的计数写掉
        self.flush()

    # region recording

    def modify_response(self, request: Request, response: Response, endpoint: str) -> Response:
        '''
        每个请求经过这里 —— 只做内存累加, 不碰数据库

        这个钩子跑在请求路径上, 任何阻塞操作都会直接反映成响应延迟。
        '''
        if self.config.enabled:
            self.record(endpoint)
        return response

    def record(self, path: str, count: int = 1):
        '''
        累加一次访问 (仅内存)
        '''
        if path not in self.config.allow_list:
            return
        with self._pending_lock:
            self._pending[path] = self._pending.get(path, 0) + count

    async def _flush_loop(self):
        interval = max(self.config.flush_interval, 1)
        try:
            while True:
                await asyncio.sleep(interval)
                try:
                    await asyncio.to_thread(self.flush)
                except Exception as ex:
                    l.error(f'[metrics] flush failed: {ex}')
        except asyncio.CancelledError:
            raise

    def flush(self):
        '''
        把内存计数写入数据库
        '''
        with self._pending_lock:
            if not self._pending:
                return
            # 先取走再写, 避免落库期间新来的请求被这一轮清掉
            pending, self._pending = self._pending, {}
        try:
            with db.session() as sess:
                self._roll_over(sess)
                for path, count in pending.items():
                    record = sess.get(MetricsData, path)
                    if not record:
                        record = MetricsData(path=path)
                    record.daily += count
                    record.weekly += count
                    record.monthly += count
                    record.yearly += count
                    record.total += count
                    sess.add(record)
                sess.commit()
            l.debug(f'[metrics] flushed {sum(pending.values())} hit(s) across {len(pending)} path(s)')
        except Exception as ex:
            # 落库失败就把计数还回去, 下一轮重试, 不要静默丢掉
            with self._pending_lock:
                for path, count in pending.items():
                    self._pending[path] = self._pending.get(path, 0) + count
            l.error(f'[metrics] flush failed, {sum(pending.values())} hit(s) requeued: {ex}')

    # endregion recording

    # region rollover

    def _period_keys(self) -> tuple[str, str, str, str]:
        '''
        当前时刻所属的 (日, 周, 月, 年) 标记
        '''
        now = datetime.now(self.tz)
        return (
            f'{now.year}-{now.month}-{now.day}',
            f'{now.year}-{now.isocalendar().week}',
            f'{now.year}-{now.month}',
            f'{now.year}'
        )

    def _roll_over(self, sess: Session):
        '''
        跨天/周/月/年时清零对应的计数
        '''
        meta = sess.exec(select(MetricsMeta)).first()
        if not meta:
            meta = MetricsMeta()
            sess.add(meta)

        today, week, month, year = self._period_keys()
        records: list[MetricsData] | None = None

        def _all() -> list[MetricsData]:
            nonlocal records
            if records is None:
                records = list(sess.exec(select(MetricsData)).all())
            return records

        if meta.today != today:
            l.debug(f'[metrics] day changed: {meta.today} -> {today}')
            meta.today = today
            for r in _all():
                r.daily = 0
        if meta.week != week:
            l.debug(f'[metrics] week changed: {meta.week} -> {week}')
            meta.week = week
            for r in _all():
                r.weekly = 0
        if meta.month != month:
            l.debug(f'[metrics] month changed: {meta.month} -> {month}')
            meta.month = month
            for r in _all():
                r.monthly = 0
        if meta.year != year:
            l.debug(f'[metrics] year changed: {meta.year} -> {year}')
            meta.year = year
            for r in _all():
                r.yearly = 0

        for r in (records or []):
            sess.add(r)
        sess.add(meta)

    # endregion rollover

    # region query

    def summary(self, sess: Session | None = None) -> dict:
        '''
        统计结果 (v5 `/api/metrics` 的返回格式)
        '''
        if not self.config.enabled:
            return {'success': True, 'enabled': False}

        # 先落库, 否则刚发生的访问不会出现在结果里
        self.flush()

        own_session = sess is None
        sess = sess or db.session()
        try:
            self._roll_over(sess)
            sess.commit()
            records = list(sess.exec(select(MetricsData)).all())
        finally:
            if own_session:
                sess.close()

        now = datetime.now(self.tz)
        return {
            'success': True,
            'enabled': True,
            'time': now.timestamp(),
            'time_local': now.strftime('%Y-%m-%d %H:%M:%S'),
            'timezone': self.config.timezone,
            'daily': {r.path: r.daily for r in records},
            'weekly': {r.path: r.weekly for r in records},
            'monthly': {r.path: r.monthly for r in records},
            'yearly': {r.path: r.yearly for r in records},
            'total': {r.path: r.total for r in records},
        }

    async def _route_metrics(self, sess: SessionDep):
        # SQLModel/SQLite work is synchronous; do not block the ASGI event loop.
        # Use a thread-owned session rather than sharing FastAPI's request session across threads.
        return await asyncio.to_thread(self.summary)

    # endregion query
