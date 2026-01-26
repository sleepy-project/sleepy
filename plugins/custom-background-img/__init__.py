# coding: utf-8

import os
import json
from typing import Annotated, Optional
from pydantic import BaseModel
from fastapi import Security, status as hc
from loguru import logger as l

from plugin import PluginBase, PluginMetadata
from main import SessionDep, TokenDep
import utils as u

DATA_FILE = 'data/bg_config.json'

class ConfigModel(BaseModel):
    url: str

class Plugin(PluginBase):
    def __init__(self, metadata: PluginMetadata):
        super().__init__(metadata)
        self.data_path = os.path.join(os.path.dirname(__file__), DATA_FILE)
        self._register_routes()

    def on_load(self):
        l.info(f'{self.metadata.name} loaded. Data path: {self.data_path}')

    def _register_routes(self):
        self.add_route(
            path='/api/background',
            endpoint=self.get_background,
            methods=['GET'],
            response_model=ConfigModel,
            tags=['custom-background'],
            name='Get Background'
        )

        self.add_route(
            path='/api/background',
            endpoint=self.set_background,
            methods=['POST'],
            status_code=hc.HTTP_200_OK,
            tags=['custom-background'],
            name='Set Background'
        )

    def _ensure_file(self):
        """Ensure the directory and config file exist."""
        directory = os.path.dirname(self.data_path)
        if not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

        if not os.path.exists(self.data_path):
            with open(self.data_path, 'w', encoding='utf-8') as f:
                json.dump({'url': ""}, f)


    def _load_config(self) -> str:
        self._ensure_file()
        try:
            with open(self.data_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('url', "")
        except Exception as e:
            l.error(f"Failed to load background config: {e}")
            return ""


    def _save_config(self, url: str):
        self._ensure_file()
        try:
            with open(self.data_path, 'w', encoding='utf-8') as f:
                json.dump({'url': url}, f)
        except Exception as e:
            l.error(f"Failed to save background config: {e}")

    async def get_background(self):
        url = self._load_config()
        return {'url': url}

    async def set_background(
        self, 
        config: ConfigModel,
        _: Annotated[bool, Security(TokenDep(allowed_login_types=('web', 'dev')))]
    ):
        self._save_config(config.url)
        return {'url': config.url}
    