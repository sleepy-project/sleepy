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
鉴权基础设施

core 只提供「签发 / 校验 / 撤销 token」的机制与管理面板登录。
设备 token 的业务规则 (谁能签发、绑定哪个设备、默认有效期) 属于 device-auth 插件。

两类凭据:
- session token (`auth_access` / `auth_refresh`) —— 管理面板, access + refresh 轮换
- device  token (`device`)                       —— 设备上报, 长期有效、单值、可撤销

设备侧刻意保持「一个字符串就能用」: Magisk 的 service.sh、AutoX.js 脚本
没有能力实现 OAuth 式的 token 轮换, 强行要求轮换等于把这些客户端全部劝退。
'''

import typing as t
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from uuid import uuid4 as uuid, UUID

import bcrypt
from fastapi import APIRouter, Depends, Header, Security, status as hc
from fastapi.security import APIKeyHeader
from loguru import logger as l
from pydantic import BaseModel, model_validator
from sqlmodel import Session, select

from core import errors as e
from core import models as m
from core.config import config as c
from core.db import get_session
from core.utils import cnen as ce

SessionDep = t.Annotated[Session, Depends(get_session)]
'''FastAPI 依赖: 数据库 Session'''

AUTH_ROOT_USERNAME = '__sleepy__'
AUTH_ACCESS_PREFIX = 'auth_access'
AUTH_REFRESH_PREFIX = 'auth_refresh'
DEVICE_PREFIX = 'device'

DEV_LOGIN_ALLOWED = bool(c.dev)
'''是否允许 dev 登录 (仅开发环境)'''

sleepy_token_header = APIKeyHeader(
    name='X-Sleepy-Token',
    scheme_name='SleepyToken',
    auto_error=False
)

router = APIRouter(prefix='/api/v1/auth', tags=['auth'])


# region models


class InitRequest(BaseModel):
    password: str
    hashed: bool = True


class InitResponse(BaseModel):
    initialized: bool = True


class AuthLoginRequest(BaseModel):
    password: str
    type: t.Literal['web', 'dev'] = 'web'
    device_uid: str | None = None
    hashed: bool = True

    @model_validator(mode='after')
    def _ensure_dev_allowed(self):
        if self.type == 'dev' and not DEV_LOGIN_ALLOWED:
            raise ValueError('Dev login disabled in this environment')
        return self


class AuthRefreshRequest(BaseModel):
    token: UUID
    refresh_token: UUID


class AuthTokensResponse(BaseModel):
    token: UUID
    refresh_token: UUID
    expires_at: float | None = None
    type: str | None = None


class AuthTokenCheckResponse(BaseModel):
    expires_at: float | None = None
    type: str | None = None


# endregion models

# region helpers


def hash_sha256(value: str) -> str:
    '''
    sha256 十六进制摘要
    '''
    return sha256(value.encode('utf-8', errors='xmlcharrefreplace')).hexdigest()


def normalize_password(password: str, hashed: bool) -> str:
    '''
    统一密码形态: 客户端可以直接传明文, 也可以传已 sha256 的值
    '''
    return password if hashed else hash_sha256(password)


def device_hash(device_uid: str) -> str:
    '''
    设备标识摘要
    '''
    return hash_sha256(device_uid)


def _token_parts(token_type: str) -> tuple[str, str | None, str | None]:
    '''
    拆分 token type: `<base>[:<subtype>]:<device_hash>`
    '''
    parts = token_type.split(':') if token_type else []
    if not parts:
        return '', None, None
    base = parts[0]
    if len(parts) == 1:
        return base, None, None
    if len(parts) == 2:
        return base, None, parts[1]
    return base, ':'.join(parts[1:-1]) or None, parts[-1]


def base_token_type(token_type: str) -> str:
    return _token_parts(token_type)[0]


def token_login_type(token_type: str) -> str | None:
    return _token_parts(token_type)[1]


def token_device_hash(token_type: str) -> str | None:
    return _token_parts(token_type)[2]


def get_auth_secret(sess: Session) -> m.AuthSecret | None:
    return sess.exec(select(m.AuthSecret)).first()


def is_auth_initialized(sess: Session) -> bool:
    return get_auth_secret(sess) is not None


def ensure_auth_initialized(sess: Session) -> m.AuthSecret:
    secret = get_auth_secret(sess)
    if not secret:
        raise e.APIUnsuccessful(hc.HTTP_403_FORBIDDEN, 'Auth not initialized')
    return secret


# endregion helpers

# region token-management


def create_token(
    sess: Session,
    prefix: str,
    device_hash_value: str,
    expire_delta: timedelta | None,
    *,
    login_type: str | None = None,
    name: str | None = None
) -> tuple[str, float | None]:
    '''
    签发 token (供插件调用)

    :param sess: 数据库 Session
    :param prefix: token 类别前缀 (`AUTH_ACCESS_PREFIX` / `DEVICE_PREFIX` 等)
    :param device_hash_value: 设备标识摘要
    :param expire_delta: 有效期, None 表示永不过期
    :param login_type: 登录类型子标记 (`web` / `dev`)
    :param name: 备注名 (device token 在面板中展示)
    :return: (token 值, 过期时间戳)
    '''
    token_value = str(uuid())
    expire_ts: float | None = None
    if expire_delta:
        expire_ts = (datetime.now(timezone.utc) + expire_delta).timestamp()

    fragments = [prefix]
    if login_type:
        fragments.append(login_type)
    fragments.append(device_hash_value)
    token_type = ':'.join(fragments)

    sess.add(m.TokenData(
        type=token_type,
        token=token_value,
        name=name,
        expire=expire_ts or 0.0
    ))
    l.info(
        f'Generated new {token_type} token '
        f'{sha256(token_value.encode("utf-8"), usedforsecurity=False).hexdigest()} (sha256), '
        f'expires: {expire_ts or "never"}'
    )
    return token_value, expire_ts


def revoke_token(sess: Session, token_value: str) -> bool:
    '''
    撤销单个 token
    '''
    record = sess.get(m.TokenData, token_value)
    if not record:
        return False
    sess.delete(record)
    sess.commit()
    l.info(f'Revoked token of type {record.type}')
    return True


def list_tokens(sess: Session, prefix: str | None = None) -> list[m.TokenData]:
    '''
    列出 token, 可按类别前缀过滤
    '''
    records = list(sess.exec(select(m.TokenData)).all())
    if prefix is None:
        return records
    return [r for r in records if base_token_type(r.type) == prefix]


def clear_session_tokens(sess: Session, device_hash_value: str):
    '''
    清除某个 web/dev 会话的 access + refresh token
    '''
    for record in sess.exec(select(m.TokenData)).all():
        base = base_token_type(record.type)
        if base in (AUTH_ACCESS_PREFIX, AUTH_REFRESH_PREFIX) and token_device_hash(record.type) == device_hash_value:
            sess.delete(record)


def _issue_full_session(sess: Session, device_uid: str | None, login_type: str | None = None) -> AuthTokensResponse:
    resolved = login_type or 'web'
    if resolved == 'dev' and not DEV_LOGIN_ALLOWED:
        raise e.APIUnsuccessful(hc.HTTP_403_FORBIDDEN, 'Dev token issuance disabled')

    dh = device_hash(device_uid or resolved)
    clear_session_tokens(sess, dh)

    access_token, expires_at = create_token(
        sess, AUTH_ACCESS_PREFIX, dh,
        timedelta(minutes=c.auth_access_token_expires_minutes),
        login_type=resolved
    )
    refresh_token, _ = create_token(
        sess, AUTH_REFRESH_PREFIX, dh,
        timedelta(days=c.auth_refresh_token_expires_days),
        login_type=resolved
    )
    sess.commit()
    return AuthTokensResponse(
        token=UUID(access_token),
        refresh_token=UUID(refresh_token),
        expires_at=expires_at,
        type=resolved
    )


def _issue_access_from_refresh(sess: Session, refresh_record: m.TokenData) -> AuthTokensResponse:
    _, login_type, dh = _token_parts(refresh_record.type)
    if not dh:
        raise e.APIUnsuccessful(hc.HTTP_401_UNAUTHORIZED, 'Malformed refresh token')

    access_token, expires_at = create_token(
        sess, AUTH_ACCESS_PREFIX, dh,
        timedelta(minutes=c.auth_access_token_expires_minutes),
        login_type=login_type
    )
    refresh_record.last_active = datetime.now(timezone.utc).timestamp()
    sess.add(refresh_record)
    sess.commit()
    return AuthTokensResponse(
        token=UUID(access_token),
        refresh_token=UUID(refresh_record.token),
        expires_at=expires_at,
        type=login_type
    )


# endregion token-management

# region dependency


class TokenDep:
    '''
    Token 校验依赖

    ```python
    # 管理面板接口
    token: m.TokenData = Security(TokenDep())
    # 设备上报接口 (device token 或面板 token 均可)
    token: m.TokenData = Security(TokenDep((DEVICE_PREFIX, AUTH_ACCESS_PREFIX)))
    ```
    '''

    def __init__(
        self,
        allowed_token_types: tuple[str, ...] | None = None,
        *,
        throw: bool = True,
        allowed_login_types: tuple[str, ...] | None = None,
        allow_query_secret: bool = False
    ):
        '''
        :param allowed_token_types: 允许的 token 类别前缀
        :param throw: 校验失败时是否抛出异常 (False 则返回 None)
        :param allowed_login_types: 允许的登录类型子标记
        :param allow_query_secret: 是否接受 `?secret=` / `?token=` 查询参数
            (仅 v5 兼容层需要, 新接口不应开启)
        '''
        self.allowed_token_types = allowed_token_types or (AUTH_ACCESS_PREFIX,)
        if allowed_login_types and not DEV_LOGIN_ALLOWED:
            filtered = tuple(x for x in allowed_login_types if x != 'dev')
            self.allowed_login_types = filtered or None
        else:
            self.allowed_login_types = allowed_login_types
        self.throw = throw
        self.allow_query_secret = allow_query_secret

    def __call__(
        self,
        sess: SessionDep,
        token_value: t.Annotated[str | None, Security(sleepy_token_header)] = None,
        authorization: t.Annotated[str | None, Header(include_in_schema=False)] = None,
    ) -> m.TokenData | None:
        if not token_value and authorization and authorization.startswith('Bearer '):
            token_value = authorization[7:]

        if not token_value:
            if self.throw:
                raise e.APIUnsuccessful(hc.HTTP_401_UNAUTHORIZED, 'Missing token')
            return None

        return self.verify(sess, token_value)

    def verify(self, sess: Session, token_value: str) -> m.TokenData | None:
        '''
        校验 token 值本身

        单独暴露出来, 让兼容层可以校验来自 body/query 的 `secret` 字段 ——
        那些字段拿不到 FastAPI 的 Security 依赖。
        '''
        info: m.TokenData | None = sess.get(m.TokenData, token_value)
        now_ts = datetime.now(timezone.utc).timestamp()

        if not info:
            l.debug('Token not found in database')
            return self._fail()

        if info.expire and 0 < info.expire < now_ts:
            l.debug(f'Token of type {info.type} expired, removing')
            sess.delete(info)
            sess.commit()
            return self._fail()

        if base_token_type(info.type) not in self.allowed_token_types:
            l.debug(f'Token type {info.type} not allowed in {self.allowed_token_types}')
            return self._fail()

        login_type = token_login_type(info.type)
        if self.allowed_login_types and login_type not in self.allowed_login_types:
            l.debug(f'Token login type {login_type} not allowed in {self.allowed_login_types}')
            return self._fail()

        touch_token(sess, info, now_ts)
        return info

    def _fail(self) -> None:
        if self.throw:
            raise e.APIUnsuccessful(hc.HTTP_401_UNAUTHORIZED, 'Invalid token')
        return None


def touch_token(sess: Session, token: m.TokenData, now_ts: float | None = None):
    '''
    更新 token 的 `last_active`, 带写入节流

    v6 每次鉴权都会 update + commit 一次。设备每 30 秒上报一次、多设备并发时,
    这个写入量远超实际数据变更量。节流窗口内的访问不再落库。
    '''
    now = now_ts if now_ts is not None else datetime.now(timezone.utc).timestamp()
    if now - token.last_active < c.token_last_active_throttle_seconds:
        return
    token.last_active = now
    sess.add(token)
    sess.commit()


# endregion dependency

# region routes


@router.post('/login', response_model=AuthTokensResponse, name='Login and issue auth tokens')
async def auth_login(sess: SessionDep, req: AuthLoginRequest):
    secret = ensure_auth_initialized(sess)
    normalized = normalize_password(req.password, req.hashed)
    if not bcrypt.checkpw(normalized.encode('utf-8', errors='xmlcharrefreplace'), secret.password):
        l.warning('Auth password mismatch during login request')
        raise e.APIUnsuccessful(hc.HTTP_401_UNAUTHORIZED, 'Incorrect password')
    return _issue_full_session(sess, req.device_uid, req.type)


@router.post('/refresh', response_model=AuthTokensResponse, name='Refresh auth token')
async def auth_refresh(sess: SessionDep, req: AuthRefreshRequest):
    ensure_auth_initialized(sess)
    now_ts = datetime.now(timezone.utc).timestamp()
    access_token = sess.get(m.TokenData, str(req.token))
    refresh_token = sess.get(m.TokenData, str(req.refresh_token))

    if not access_token or base_token_type(access_token.type) != AUTH_ACCESS_PREFIX:
        raise e.APIUnsuccessful(hc.HTTP_401_UNAUTHORIZED, 'Invalid token')
    if not refresh_token or base_token_type(refresh_token.type) != AUTH_REFRESH_PREFIX:
        raise e.APIUnsuccessful(hc.HTTP_401_UNAUTHORIZED, 'Invalid refresh token')

    if token_device_hash(refresh_token.type) != token_device_hash(access_token.type):
        raise e.APIUnsuccessful(hc.HTTP_401_UNAUTHORIZED, 'Token pair mismatch')

    if refresh_token.expire and 0 < refresh_token.expire < now_ts:
        sess.delete(refresh_token)
        sess.commit()
        raise e.APIUnsuccessful(hc.HTTP_401_UNAUTHORIZED, 'Refresh token expired')

    if access_token.expire and 0 < access_token.expire < now_ts:
        sess.delete(access_token)
        sess.commit()
        raise e.APIUnsuccessful(hc.HTTP_401_UNAUTHORIZED, 'Token expired')

    sess.delete(access_token)
    return _issue_access_from_refresh(sess, refresh_token)


@router.get('/check', response_model=AuthTokenCheckResponse, name='Check token validity')
async def auth_check(
    token: m.TokenData | None = Security(TokenDep(allowed_token_types=(AUTH_ACCESS_PREFIX,), throw=False))
):
    if not token:
        raise e.APIUnsuccessful(hc.HTTP_403_FORBIDDEN, 'Invalid token')
    return {
        'expires_at': token.expire if token.expire and token.expire > 0 else None,
        'type': token_login_type(token.type)
    }


init_router = APIRouter(tags=['auth'])


@init_router.post('/api/v1/init', response_model=InitResponse, name='Initialize auth secret')
async def init_auth(sess: SessionDep, req: InitRequest):
    '''
    首次设置管理密码
    '''
    if is_auth_initialized(sess):
        raise e.APIUnsuccessful(hc.HTTP_409_CONFLICT, 'Auth already initialized')
    normalized = normalize_password(req.password, req.hashed)
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(normalized.encode('utf-8', errors='xmlcharrefreplace'), salt)
    sess.add(m.AuthSecret(username=AUTH_ROOT_USERNAME, password=hashed_password, salt=salt))
    sess.commit()
    return {'initialized': True}


@init_router.get('/api/v1/init', response_model=InitResponse, name='Check auth initialization')
async def check_init_auth(sess: SessionDep):
    '''
    查询是否已初始化, 供前端自动跳转使用
    '''
    return {'initialized': is_auth_initialized(sess)}


OPENAPI_SECURITY_SCHEME = {
    'type': 'apiKey',
    'in': 'header',
    'name': 'X-Sleepy-Token',
    'description': ce('在 `X-Sleepy-Token` 中提供 token', '`X-Sleepy-Token` header for sending the raw token')
}

# endregion routes
