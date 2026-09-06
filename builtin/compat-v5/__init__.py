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
compat-v5 —— 旧版 API 兼容层

存在的理由很具体: main 分支 `client/` 下 11 个客户端里, 有 9 个只调用
`/api/device/set` 这一个接口, 且形态完全一致 —— POST, JSON body 里带 `secret`。
只要保留这一条路径, 那 9 个脚本就能一行不改地连上 v7。

核心约定: **v5 的 `secret` 就是 v7 的 device token**。
用户在面板里生成一个长期 token, 填进客户端原有的 `SECRET` 变量即可。
这比 v5 的全局共享 secret 更好 —— token 可命名、可撤销、可按设备区分。

字段映射:
- `show_name` -> `name`
- `app_name`  -> `status` (v5 自己也在兼容的更旧的名字)
- 其余 query 参数 -> `fields`

不需要兼容层时, 在配置里关掉即可: `plugins.disabled = ['compat-v5']`
'''

import typing as t
from json import loads
from time import time

from fastapi import Request, status as hc
from sqlmodel import Session

from core import errors as e
from core.auth import AUTH_ACCESS_PREFIX, DEVICE_PREFIX, SessionDep, TokenDep
from core.plugin import PluginBase, PluginMetadata, plugin_manager

RESERVED_FIELDS = {'id', 'show_name', 'using', 'status', 'app_name', 'secret', 'token'}
'''这些键有明确语义, 不进 fields'''


class Plugin(PluginBase):

    def __init__(self, metadata: PluginMetadata):
        super().__init__(metadata)
        # 设备上报接受 device token; 面板 token 也放行, 便于管理工具类客户端复用登录态
        self._auth = TokenDep((DEVICE_PREFIX, AUTH_ACCESS_PREFIX), throw=False)
        self._admin_auth = TokenDep((AUTH_ACCESS_PREFIX,), throw=False)

    def on_load(self):
        # --- 设备 (9 个客户端只用这一条) ---
        self.add_route('/api/device/set', self._device_set, ['GET', 'POST'], tags=['compat-v5'])
        self.add_route('/api/device/remove', self._device_remove, ['GET'], tags=['compat-v5'])
        self.add_route('/api/device/clear', self._device_clear, ['GET'], tags=['compat-v5'])
        self.add_route('/api/device/private', self._device_private, ['GET'], tags=['compat-v5'])

        # --- 状态 (管理工具类客户端) ---
        self.add_route('/api/status/query', self._status_query, ['GET'], tags=['compat-v5'])
        self.add_route('/api/status/set', self._status_set, ['GET'], tags=['compat-v5'])
        self.add_route('/api/status/list', self._status_list, ['GET'], tags=['compat-v5'])

        # --- 元信息 ---
        self.add_route('/api/meta', self._meta, ['GET'], tags=['compat-v5'])

    # region helpers

    @property
    def _device_api(self) -> dict:
        return plugin_manager.api('device')

    @property
    def _status_api(self) -> dict:
        return plugin_manager.api('status')

    def _require(self, api: dict, name: str) -> t.Callable:
        '''
        取用依赖插件的导出函数

        依赖插件被禁用时给出明确的 503, 而不是让请求以 AttributeError 收场。
        '''
        fn = api.get(name)
        if not fn:
            raise e.APIUnsuccessful(
                hc.HTTP_503_SERVICE_UNAVAILABLE,
                f'Required plugin API "{name}" is unavailable (plugin disabled?)'
            )
        return fn

    async def _read_payload(self, request: Request) -> dict:
        '''
        统一取参: GET 从 query, POST 从 JSON body

        v5 的客户端两种都在用 —— 浏览器脚本和 PowerShell 走 POST,
        部分 shell 脚本走 GET。
        '''
        if request.method == 'GET':
            return dict(request.query_params)

        raw = await request.body()
        if not raw.strip():
            # 有些客户端用 POST 但把参数放在 query 上, body 为空
            return dict(request.query_params)

        try:
            body = loads(raw)
        except Exception as ex:
            # 不要在这里静默回退到 query params: body 明明有内容却解析失败时,
            # 回退会让错误表现成「Missing secret」, 把真正的原因 (编码/格式错误) 藏起来。
            raise e.APIUnsuccessful(hc.HTTP_400_BAD_REQUEST, f'Invalid JSON body: {ex}')

        if not isinstance(body, dict):
            raise e.APIUnsuccessful(hc.HTTP_400_BAD_REQUEST, 'Request body must be a JSON object')

        # query 参数作为兜底, body 优先
        merged = dict(request.query_params)
        merged.update(body)
        return merged

    def _authorize(self, sess: Session, payload: dict, admin: bool = False):
        '''
        校验 v5 风格的 secret

        `secret` 可能出现在 query 或 body 里, 拿不到 FastAPI 的 Security 依赖,
        因此直接调用 TokenDep.verify()。
        '''
        secret = payload.get('secret') or payload.get('token')
        if not secret:
            raise e.APIUnsuccessful(hc.HTTP_401_UNAUTHORIZED, 'Missing secret')
        dep = self._admin_auth if admin else self._auth
        if not dep.verify(sess, str(secret)):
            raise e.APIUnsuccessful(hc.HTTP_401_UNAUTHORIZED, 'Incorrect secret')

    @staticmethod
    def _to_bool(value: t.Any, default: bool | None = None) -> bool | None:
        from core.utils import tobool
        return tobool(value, default)

    # endregion helpers

    # region device-routes

    async def _device_set(self, request: Request, sess: SessionDep):
        '''
        v5 `/api/device/set`

        9 个客户端唯一依赖的接口。
        '''
        payload = await self._read_payload(request)
        self._authorize(sess, payload)

        device_id = payload.get('id')
        if not device_id:
            raise e.APIUnsuccessful(hc.HTTP_400_BAD_REQUEST, 'Missing device id')

        # v5 的 status 有个更旧的别名 app_name
        status = payload.get('status') or payload.get('app_name')
        fields = payload.get('fields')
        if not isinstance(fields, dict):
            fields = {k: v for k, v in payload.items() if k not in RESERVED_FIELDS}

        set_device = self._require(self._device_api, 'set_device')
        await set_device(
            sess,
            str(device_id),
            name=payload.get('show_name'),
            status=status,
            using=self._to_bool(payload.get('using'), True),
            fields=fields
        )
        return {'success': True}

    async def _device_remove(self, request: Request, sess: SessionDep):
        payload = await self._read_payload(request)
        self._authorize(sess, payload)
        device_id = payload.get('id')
        if not device_id:
            raise e.APIUnsuccessful(hc.HTTP_400_BAD_REQUEST, 'Missing device id')
        await self._require(self._device_api, 'remove_device')(sess, str(device_id))
        # v5 在设备不存在时也返回成功
        return {'success': True}

    async def _device_clear(self, request: Request, sess: SessionDep):
        payload = await self._read_payload(request)
        self._authorize(sess, payload, admin=True)
        count = await self._require(self._device_api, 'clear_devices')(sess)
        return {'success': True, 'count': count}

    async def _device_private(self, request: Request, sess: SessionDep):
        payload = await self._read_payload(request)
        self._authorize(sess, payload, admin=True)
        enabled = self._to_bool(payload.get('private'), None)
        if enabled is None:
            raise e.APIUnsuccessful(hc.HTTP_400_BAD_REQUEST, 'Missing or invalid private value')
        self._require(self._device_api, 'set_private')(sess, enabled)
        await self.broadcast('device-changed', {})
        return {'success': True, 'private': enabled}

    # endregion device-routes

    # region status-routes

    async def _status_query(self, sess: SessionDep):
        '''
        v5 `/api/status/query`

        v5 返回的 status 是完整对象 (含 name/desc/color), 而不是 v7 的整数 id,
        这里按预设表还原, 否则老前端拿不到展示文案。
        '''
        snapshot = self._require(self._status_api, 'query')(sess)
        status_id = snapshot.get('status', 0)
        presets = self._require(self._status_api, 'get_presets')()
        matched = next((p for p in presets if p.id == status_id), None)

        return {
            'time': snapshot.get('time', time()),
            'success': True,
            'status': status_id,
            'info': matched.model_dump() if matched else {
                'id': status_id, 'name': 'Unknown', 'desc': '未知状态', 'color': 'error'
            },
            'device': {
                d['id']: {
                    'show_name': d['name'],
                    'using': d['using'],
                    'status': d['status'],
                    **d.get('fields', {})
                }
                for d in snapshot.get('devices', [])
            },
            'device_status_slice': None,
            'last_updated': snapshot.get('last_updated'),
            'refresh': 5000
        }

    async def _status_set(self, request: Request, sess: SessionDep):
        payload = await self._read_payload(request)
        self._authorize(sess, payload, admin=True)
        raw = payload.get('status')
        if raw is None:
            raise e.APIUnsuccessful(hc.HTTP_400_BAD_REQUEST, 'Missing status')
        try:
            value = int(raw)
        except (TypeError, ValueError):
            raise e.APIUnsuccessful(hc.HTTP_400_BAD_REQUEST, f'Invalid status value: {raw}')
        await self._require(self._status_api, 'set_status')(sess, value)
        return {'success': True, 'set_to': value}

    async def _status_list(self):
        presets = self._require(self._status_api, 'get_presets')()
        return [p.model_dump() for p in presets]

    # endregion status-routes

    async def _meta(self):
        from core.app import version, version_str
        return {
            'success': True,
            'version': version_str,
            'version_int': list(version),
            'plugin': plugin_manager.get_loaded_plugins()
        }
