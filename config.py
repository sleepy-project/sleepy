# coding: utf-8

import os
from logging import getLogger

from dotenv import load_dotenv
from yaml import safe_load as load_yaml
from toml import load as load_toml
from json import load as load_json, loads as load_json_str, JSONDecodeError

import utils as u
from config_models import ConfigModel, env_vaildate_json_keys

l = getLogger(__name__)

# ----- prepare .env -----
config_env = {}
try:
    load_dotenv(dotenv_path=u.get_path('.env'))
    # 筛选有效配置项
    vaild_kvs: dict[str, str] = {}
    for k_, v in os.environ.items():
        k = k_.lower()
        if k.startswith('sleepy_'):
            vaild_kvs[k[7:]] = v
    # 生成字典
    for k, v in vaild_kvs.items():
        if k in env_vaildate_json_keys:
            try:
                v = load_json_str(v)
            except JSONDecodeError:
                pass
        klst = k.split('_')
        config_env = u.deep_merge_dict(config_env, u.process_env_split(klst, v))
except Exception as e:
    l.warning(f'Error when loading environment variables: {e}')

# ----- prepare config.yaml -----
config_yaml = {}
try:
    if os.path.exists(u.get_path('config.yaml')):
        with open(u.get_path('config.yaml'), 'r', encoding='utf-8') as f:
            config_yaml = load_yaml(f)
            f.close()
except Exception as e:
    l.warning(f'Error when loading config.yaml: {e}')

# ----- prepare config.toml -----
config_toml = {}
try:
    if os.path.exists(u.get_path('config.toml')):
        with open(u.get_path('config.toml'), 'r', encoding='utf-8') as f:
            config_toml = load_toml(f)
            f.close()
except Exception as e:
    l.warning(f'Error when loading config.toml: {e}')

# ----- prepare config.json -----
config_json = {}
try:
    if os.path.exists(u.get_path('config.json')):
        with open(u.get_path('config.json'), 'r', encoding='utf-8') as f:
            config_json = load_json(f)
            f.close()
except Exception as e:
    l.warning(f'Error when loading config.json: {e}')

# ----- mix configs -----
config = ConfigModel(**u.deep_merge_dict(config_env, config_yaml, config_toml, config_json))
for i in range(len(config.page.status_list)):
    config.page.status_list[i].id = i