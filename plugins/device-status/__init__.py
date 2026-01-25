# coding: utf-8

import typing as t
from time import time
from uuid import uuid4 as uuid, UUID

from fastapi import WebSocket, WebSocketDisconnect, Security, Header, status as hc, FastAPI
from sqlmodel import select, Session
from pydantic import BaseModel
from loguru import logger as l

from plugin import PluginBase, PluginMetadata
import models as m
import errors as e

# Importing shared resources from main
from main import (
    SessionDep, TokenDep, manager, engine, sleepy_token_header,
    _issue_full_session, _clear_device_tokens, _device_hash, _token_login_type
)


# region Models

class CreateDeviceRequest(BaseModel):
    name: str
    status: str | None = None
    using: bool | None = None
    fields: dict | None = None


class CreateDeviceResponse(BaseModel):
    id: str
    device: m.DeviceData
    token: UUID
    refresh_token: UUID
    expires_at: float | None = None


class UpdateDeviceRequest(BaseModel):
    name: str | None = None
    status: str | None = None
    using: bool | None = None
    fields: dict | None = None


class GetDevicesResponse(BaseModel):
    devices: list[m.DeviceData]

# endregion Models


class Plugin(PluginBase):
    def __init__(self, metadata: PluginMetadata):
        super().__init__(metadata)
        self._register_http_routes()

    def on_load(self):
        l.info(f'{self.metadata.name} loaded')

    def setup_routes(self, app: FastAPI):
        """
        Override setup_routes to register WebSocket endpoints, 
        as add_route typically handles API routes.
        """
        app.add_api_websocket_route('/api/devices/{device_id}', self.websocket_device)
        l.debug(f'Plugin {self.metadata.name} registered websocket: /api/devices/{{device_id}}')

    def _register_http_routes(self):
        tags = ['devices']
        
        self.add_route(
            path='/api/devices/{device_id}',
            endpoint=self.get_device,
            methods=['GET'],
            response_model=m.DeviceData,
            tags=tags
        )

        self.add_route(
            path='/api/devices/',
            endpoint=self.create_device,
            methods=['POST'],
            response_model=CreateDeviceResponse,
            status_code=hc.HTTP_201_CREATED,
            tags=tags,
            name='Create a device'
        )

        self.add_route(
            path='/api/devices/{device_id}',
            endpoint=self.update_device,
            methods=['PUT'],
            status_code=hc.HTTP_204_NO_CONTENT,
            tags=tags,
            name='Update a device'
        )

        self.add_route(
            path='/api/devices/{device_id}',
            endpoint=self.delete_device,
            methods=['DELETE'],
            status_code=hc.HTTP_204_NO_CONTENT,
            tags=tags
        )

        self.add_route(
            path='/api/devices/',
            endpoint=self.get_devices,
            methods=['GET'],
            response_model=GetDevicesResponse,
            tags=tags
        )

        self.add_route(
            path='/api/devices/',
            endpoint=self.clear_devices,
            methods=['DELETE'],
            status_code=hc.HTTP_204_NO_CONTENT,
            tags=tags
        )

    # region WebSocket Logic

    async def websocket_device(self, ws: WebSocket, device_id: str):
        """
        Device WebSocket Endpoint
        """
        token_value = ws.query_params.get('token') or ws.headers.get('x-sleepy-token')

        if not token_value:
            l.warning(f'WebSocket connection to device {device_id} rejected: missing token')
            await ws.close(code=1008, reason='Missing token')
            return

        with Session(engine) as sess:
            try:
                token_dep = TokenDep(
                    allowed_login_types=('web', 'dev', 'device'),
                    device_id=device_id,
                    throw=True
                )
                
                # Manually invoking TokenDep logic since this is a WS handler
                token_info = token_dep(
                    sess=sess,
                    token_value=token_value,
                    authorization=None
                )

                if not token_info:
                    l.warning(f'WebSocket connection to device {device_id} rejected: invalid token')
                    await ws.close(code=1008, reason='Invalid token')
                    return

                login_type = _token_login_type(token_info.type)
                l.info(f'WebSocket connected for device {device_id} with {login_type} token')

            except e.APIUnsuccessful as ex:
                l.warning(f'WebSocket connection to device {device_id} rejected: {ex.message}')
                await ws.close(code=1008, reason=ex.message)
                return

        try:
            await ws.accept()

            while True:
                data: dict = await ws.receive_json()
                using = data.get('using')
                status = data.get('status')
                fields = data.get('fields', {})
                using_bool = str(using) == '1' or using is True
                
                with Session(engine) as sess:
                    device = sess.exec(select(m.DeviceData).where(m.DeviceData.id == device_id)).first()
                    if not device:
                        device = m.DeviceData(
                            id=device_id,
                            name=device_id,
                            status=str(status) if status is not None else '',
                            using=using_bool,
                            fields=fields,
                            last_updated=time()
                        )
                        sess.add(device)
                    else:
                        device.status = str(status) if status is not None else device.status
                        device.using = using_bool
                        device.fields = fields
                        device.last_updated = time()
                    sess.commit()
                
                await ws.send_json({
                    'ok': True,
                    'id': device_id,
                    'status': status,
                    'using': using,
                    'fields': fields
                })

        except WebSocketDisconnect:
            l.info(f'WebSocket disconnected for device {device_id}')
        except Exception as ex:
            l.error(f'WebSocket error for device {device_id}: {ex}')
            try:
                await ws.close(code=1011, reason='Internal error')
            except:
                pass

    # region HTTP Handlers

    async def get_device(self, sess: SessionDep, device_id: str):
        device = sess.get(m.DeviceData, device_id)
        if device:
            return device
        else:
            raise e.APIUnsuccessful(hc.HTTP_404_NOT_FOUND, 'Device not found')

    async def create_device(
        self,
        sess: SessionDep,
        req: CreateDeviceRequest,
        _: t.Annotated[m.TokenData, Security(TokenDep(allowed_login_types=('web', 'dev')))]
    ):
        device_id = uuid().hex
        status = req.status or ''
        using = req.using if req.using is not None else False
        fields = req.fields or {}
        device = m.DeviceData(
            id=device_id,
            name=req.name,
            status=status,
            using=using,
            fields=fields
        )
        sess.add(device)
        meta = sess.exec(select(m.Metadata)).first()
        if meta:
            meta.last_updated = time()
        sess.commit()
        
        # Accessing private auth helper from main
        tokens = _issue_full_session(sess, device_id, 'device')
        
        await manager.evt_broadcast('device_added', {
            'id': device_id,
            'name': req.name,
            'status': status,
            'using': using,
            'fields': fields
        })
        return {
            'id': device_id,
            'device': device,
            'token': tokens.token,
            'refresh_token': tokens.refresh_token,
            'expires_at': tokens.expires_at
        }

    async def update_device(
        self,
        sess: SessionDep,
        device_id: str,
        req: UpdateDeviceRequest,
        token_value: t.Annotated[str | None, Security(sleepy_token_header)] = None,
        authorization: t.Annotated[str | None, Header(include_in_schema=False)] = None
    ):
        TokenDep(
            allowed_login_types=('web', 'dev', 'device'),
            device_id=device_id
        )(sess, token_value, authorization)

        device = sess.get(m.DeviceData, device_id)
        if device:
            updated = {}
            if req.name is not None:
                device.name = req.name
                updated['name'] = req.name
            if req.status:
                device.status = req.status
                updated['status'] = req.status
            if req.using is not None:
                device.using = req.using
                updated['using'] = req.using
            if req.fields:
                device.fields = req.fields
                updated['fields'] = req.fields
            if updated:
                device.last_updated = time()
                meta = sess.exec(select(m.Metadata)).first()
                if meta:
                    meta.last_updated = time()
                sess.commit()
                await manager.evt_broadcast('device_updated', {'id': device_id, 'updated_fields': updated})
            return
        else:
            raise e.APIUnsuccessful(hc.HTTP_404_NOT_FOUND, 'Device not found')

    async def delete_device(
        self,
        sess: SessionDep,
        device_id: str,
        _: t.Annotated[m.TokenData, Security(TokenDep(allowed_login_types=('web', 'dev')))]
    ):
        device = sess.get(m.DeviceData, device_id)
        if device:
            device_hash = _device_hash(device.id)
            sess.delete(device)
            meta = sess.exec(select(m.Metadata)).first()
            if meta:
                meta.last_updated = time()
            _clear_device_tokens(sess, device_hash)
            sess.commit()
            await manager.evt_broadcast('device_deleted', {'id': device_id})
        return

    async def get_devices(self, sess: SessionDep):
        devices = sess.exec(select(m.DeviceData)).all()
        return {'devices': devices}

    async def clear_devices(
        self,
        sess: SessionDep,
        _: t.Annotated[m.TokenData, Security(TokenDep(allowed_login_types=('web', 'dev')))]
    ):
        devices = sess.exec(select(m.DeviceData)).all()
        for d in devices:
            _clear_device_tokens(sess, _device_hash(d.id))
            sess.delete(d)
        meta = sess.exec(select(m.Metadata)).first()
        if meta:
            meta.last_updated = time()
        sess.commit()
        await manager.evt_broadcast('devices_cleared')
        return
    