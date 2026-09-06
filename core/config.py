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
配置加载

优先级 (后者覆盖前者): 环境变量 -> config.yaml -> config.toml -> config.json
'''

import os
import typing as t
from logging import getLogger
from json import load as load_json, loads as load_json_str, JSONDecodeError

from dotenv import load_dotenv
from yaml import safe_load as load_yaml
from toml import load as load_toml

from core import utils as u
from core.config_models import ConfigModel, env_vaildate_json_keys

l = getLogger(__name__)


def load_env_config() -> dict:
    '''
    从环境变量与 `.env` 加载配置 (前缀 `SLEEPY_`)
    '''
    config_env: dict = {}
    try:
        load_dotenv(dotenv_path=u.get_path('.env', create_dirs=False))
        # 筛选有效配置项
        vaild_kvs: dict[str, str] = {}
        for k_, v in os.environ.items():
            k = k_.lower()
            if k.startswith('sleepy_'):
                vaild_kvs[k[7:]] = v
        # 生成字典
        for k, v in vaild_kvs.items():
            value: t.Any = v
            if k in env_vaildate_json_keys:
                try:
                    value = load_json_str(v)
                except JSONDecodeError:
                    pass
            config_env = u.deep_merge_dict(config_env, u.process_env_split(k.split('_'), value))
    except Exception as e:
        l.warning(f'Error when loading environment variables: {e}')
    return config_env


def load_file_config(filename: str, loader: t.Callable) -> dict:
    '''
    加载单个配置文件, 不存在或解析失败时返回空字典

    :param filename: 相对项目根目录的文件名
    :param loader: 解析函数 (接收 file object)
    '''
    path = u.get_path(filename, create_dirs=False)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return loader(f) or {}
    except Exception as e:
        l.warning(f'Error when loading {filename}: {e}')
        return {}


def build_config() -> ConfigModel:
    '''
    合并所有配置源并构建 ConfigModel
    '''
    return ConfigModel(**u.deep_merge_dict(
        load_env_config(),
        load_file_config('config.yaml', load_yaml),
        load_file_config('config.toml', load_toml),
        load_file_config('config.json', load_json)
    ))


config = build_config()
'''
全局配置实例
'''
