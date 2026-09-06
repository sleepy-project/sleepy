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
device-auth —— 设备 Token 管理

设备 token 刻意做成「一个字符串就能用」: 长期有效、不轮换、可命名、可撤销。

原因是客户端的现实条件 —— Magisk 的 `service.sh`、AutoX.js 脚本、
PowerShell 单文件脚本都没有能力实现 OAuth 式的 refresh 流程。
强行要求轮换, 等于把这些客户端全部劝退 (v6 就是这样丢掉全部 20+ 个客户端的)。

签发出来的 token 可以直接填进 v5 客户端原有的 `SECRET` 变量, 配合 compat-v5
插件即可零改动接入。
'''

import typing as t
from datetime import timedelta

from fastapi import Security, status as hc
from pydantic import BaseModel
from sqlmodel import Session

from core import errors as e
from core.auth import (
    AUTH_ACCESS_PREFIX, DEVICE_PREFIX, SessionDep, TokenDep,
    create_token, device_hash, list_tokens, revoke_token
)
from core.plugin import PluginBase, PluginMetadata


class DeviceAuthConfig(BaseModel):
    '''
    device-auth 插件配置 (`plugin.device-auth`)
    '''
    expires_days: int = 0
    '''
    设备 token 有效期 (天), 0 表示永不过期

    默认永不过期 —— 设备脚本一旦部署很少有人回去更新, 过期只会带来
    「某天状态突然不更新了」这种难排查的故障。需要定期轮换的场景再打开。
    '''


class TokenCreateRequest(BaseModel):
    name: str | None = None
    '''备注名, 便于在面板里分辨是哪台设备'''

    device_uid: str | None = None
    '''设备标识, 不填则用备注名'''


class TokenInfo(BaseModel):
    token: str
    name: str | None = None
    created: float
    last_active: float
    expire: float


class Plugin(PluginBase):

    def __init__(self, metadata: PluginMetadata):
        super().__init__(metadata)
        self.register_config(DeviceAuthConfig)
        self.exports = {
            'issue_device_token': self.issue_device_token,
            'revoke_device_token': self.revoke_device_token,
            'list_device_tokens': self.list_device_tokens,
        }

    @property
    def config(self) -> DeviceAuthConfig:
        return t.cast(DeviceAuthConfig, self.get_config())

    def on_load(self):
        admin_auth = TokenDep((AUTH_ACCESS_PREFIX,))

        self.add_route('/api/v1/tokens', self._route_list, ['GET'],
                       tags=['device-auth'], name='List device tokens',
                       dependencies=[Security(admin_auth)], response_model=list[TokenInfo])
        self.add_route('/api/v1/tokens', self._route_create, ['POST'],
                       tags=['device-auth'], name='Issue a device token',
                       dependencies=[Security(admin_auth)], status_code=hc.HTTP_201_CREATED)
        self.add_route('/api/v1/tokens/{token}', self._route_revoke, ['DELETE'],
                       tags=['device-auth'], name='Revoke a device token',
                       dependencies=[Security(admin_auth)])

    # region api

    def issue_device_token(self, sess: Session, name: str | None = None, device_uid: str | None = None) -> dict:
        '''
        签发一个设备 token
        '''
        identifier = device_uid or name or 'device'
        days = self.config.expires_days
        token_value, expire_ts = create_token(
            sess,
            DEVICE_PREFIX,
            device_hash(identifier),
            timedelta(days=days) if days > 0 else None,
            name=name
        )
        sess.commit()
        return {'token': token_value, 'name': name, 'expires_at': expire_ts}

    def revoke_device_token(self, sess: Session, token_value: str) -> bool:
        '''
        撤销设备 token
        '''
        return revoke_token(sess, token_value)

    def list_device_tokens(self, sess: Session) -> list:
        '''
        列出所有设备 token
        '''
        return list_tokens(sess, DEVICE_PREFIX)

    # endregion api

    # region routes

    async def _route_list(self, sess: SessionDep):
        return self.list_device_tokens(sess)

    async def _route_create(self, sess: SessionDep, req: TokenCreateRequest):
        result = self.issue_device_token(sess, name=req.name, device_uid=req.device_uid)
        return {
            **result,
            'hint': '把这个值填进客户端脚本的 SECRET 变量即可 (需启用 compat-v5 插件)'
        }

    async def _route_revoke(self, sess: SessionDep, token: str):
        if not self.revoke_device_token(sess, token):
            raise e.APIUnsuccessful(hc.HTTP_404_NOT_FOUND, 'Token not found')
        return {'revoked': True}

    # endregion routes
