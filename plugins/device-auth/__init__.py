# coding: utf-8

from datetime import timedelta
from uuid import UUID
from typing import Annotated

from fastapi import Security, Header, status as hc
from sqlmodel import Session, select
from loguru import logger as l

from plugin import PluginBase, PluginMetadata
import models as m
import errors as e
from config import config as c

# Import core auth utilities from main
from main import (
    SessionDep, 
    TokenDep, 
    create_token, 
    AuthTokensResponse,
    sleepy_token_header,
    _device_hash,
    _token_device_hash,
    _token_login_type,
    AUTH_ACCESS_PREFIX,
    AUTH_REFRESH_PREFIX
)


class Plugin(PluginBase):
    def __init__(self, metadata: PluginMetadata):
        super().__init__(metadata)

    def on_load(self):
        l.info(f'{self.metadata.name} loaded')

    # No routes to register, this plugin provides services to other plugins

def clear_device_tokens(sess: Session, device_id: str):
    """
    Clears all tokens (access and refresh) associated with a specific device ID.
    """
    device_hash = _device_hash(device_id)
    
    def _tokens_with_prefix(prefix: str) -> list[m.TokenData]:
        return list(sess.exec(select(m.TokenData).where(m.TokenData.type.startswith(f'{prefix}:'))).all())

    candidates = _tokens_with_prefix(AUTH_ACCESS_PREFIX) + _tokens_with_prefix(AUTH_REFRESH_PREFIX)
    for tk in candidates:
        if _token_device_hash(tk.type) == device_hash:
            sess.delete(tk)

def issue_device_session(sess: Session, device_id: str) -> AuthTokensResponse:
    """
    Issues a new session (access + refresh token) for a device.
    """
    device_hash = _device_hash(device_id)
    
    # Clean up old tokens for this device
    clear_device_tokens(sess, device_id)
    
    access_token, expires_at = create_token(
        sess,
        AUTH_ACCESS_PREFIX,
        device_hash,
        timedelta(minutes=c.auth_access_token_expires_minutes),
        login_type='device'
    )
    refresh_token, _ = create_token(
        sess,
        AUTH_REFRESH_PREFIX,
        device_hash,
        timedelta(days=c.auth_refresh_token_expires_days),
        login_type='device'
    )
    sess.commit()
    
    return AuthTokensResponse(
        token=UUID(access_token),
        refresh_token=UUID(refresh_token),
        expires_at=expires_at,
        type='device'
    )

class DeviceTokenVerifier:
    """
    Dependency to verify a token acts on behalf of a specific device.
    It allows:
    1. 'web' or 'dev' tokens (admin access)
    2. 'device' tokens BUT only if they match the requested device_id
    """
    def __init__(self, device_id: str):
        self.device_id = device_id
        # We use the base TokenDep to do the heavy lifting (DB lookup, expiration)
        self.base_dep = TokenDep(
            allowed_login_types=('web', 'dev', 'device'),
            throw=True
        )

    def __call__(
        self,
        sess: SessionDep,
        token_value: Annotated[str | None, Security(sleepy_token_header)] = None,
        authorization: Annotated[str | None, Header(include_in_schema=False)] = None,
    ) -> m.TokenData:
        # 1. Basic validation
        token_info = self.base_dep(sess, token_value, authorization)
        if not token_info:
            # Should imply throw=True raised exception, but for safety:
            raise e.APIUnsuccessful(hc.HTTP_401_UNAUTHORIZED, 'Invalid token')

        # 2. Check Device Specific Logic
        login_type = _token_login_type(token_info.type)
        
        if login_type == 'device':
            token_device_hash = _token_device_hash(token_info.type)
            expected_device_hash = _device_hash(self.device_id)
            
            if token_device_hash != expected_device_hash:
                l.debug(f'Device token hash mismatch for device {self.device_id}')
                raise e.APIUnsuccessful(hc.HTTP_403_FORBIDDEN, 'Unauthorized for this device')
        
        # 'web' and 'dev' are allowed to access any device, so they pass through
        
        return token_info
    