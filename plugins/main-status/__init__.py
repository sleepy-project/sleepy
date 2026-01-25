# coding: utf-8

from time import time
from typing import Annotated

from fastapi import Security, status as hc
from pydantic import BaseModel
from sqlmodel import select
from loguru import logger as l

from plugin import PluginBase, PluginMetadata
import models as m
import errors as e

from main import SessionDep, TokenDep, manager

class GetStatusResponse(BaseModel):
    status: int | None = 0


class SetStatusRequest(BaseModel):
    status: int


class Plugin(PluginBase):
    def __init__(self, metadata: PluginMetadata):
        super().__init__(metadata)
        self._register_routes()

    def on_load(self):
        l.info(f'{self.metadata.name} loaded')

    def _register_routes(self):
        self.add_route(
            path='/api/status/',
            endpoint=self.get_status,
            methods=['GET'],
            response_model=GetStatusResponse,
            tags=['status'],
            name='Get Status'
        )

        self.add_route(
            path='/api/status/',
            endpoint=self.set_status,
            methods=['POST'],
            status_code=hc.HTTP_204_NO_CONTENT,
            tags=['status'],
            name='Set Status'
        )

    async def get_status(self, sess: SessionDep):
        meta = sess.exec(select(m.Metadata)).first()
        if meta:
            return {'status': meta.status}
        else:
            raise e.APIUnsuccessful(hc.HTTP_500_INTERNAL_SERVER_ERROR, 'Cannot read metadata')

    async def set_status(
        self,
        sess: SessionDep,
        req: SetStatusRequest,
        _: Annotated[m.TokenData, Security(TokenDep(allowed_login_types=('web', 'dev')))]
    ):
        meta = sess.exec(select(m.Metadata)).first()
        if not meta:
            raise e.APIUnsuccessful(hc.HTTP_500_INTERNAL_SERVER_ERROR, 'Cannot update metadata')
        elif meta.status == req.status:
            return
        else:
            meta.status = req.status
            meta.last_updated = time()
            sess.commit()
            await manager.evt_broadcast('status_changed', {'status': req.status})
            return
        