# coding: utf-8
import os
from logging import getLogger

from dotenv import load_dotenv
from yaml import safe_load as yaml_load
from toml import load as toml_load
from json import load as json_load, loads as json_loads, JSONDecodeError

import utils as u
from models import ConfigModel, env_vaildate_json_keys
from pydantic import ValidationError

l = getLogger(__name__)


class Config:
    '''
    用户配置
    '''

    config: ConfigModel

    def __init__(self):
        perf = u.perf_counter()  # 性能计数器

        # ===== prepare .env =====
        load_dotenv(dotenv_path=u.get_path('data/.env'))
        config_env = {}
        try:
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
                        v = json_loads(v)
                    except JSONDecodeError:
                        pass
                klst = k.split('_')
                config_env = u.deep_merge_dict(config_env, u.process_env_split(klst, v))
        except Exception as e:
            l.warning(f'Error when loading environment variables: {e}')

        # ===== prepare config.yaml =====
        config_yaml = {}
        try:
            if os.path.exists(u.get_path('data/config.yaml')):
                with open(u.get_path('data/config.yaml'), 'r', encoding='utf-8') as f:
                    config_yaml = yaml_load(f)
                    f.close()
        except Exception as e:
            l.warning(f'Error when loading data/config.yaml: {e}')

        # ===== prepare config.toml =====
        config_toml = {}
        try:
            if os.path.exists(u.get_path('data/config.toml')):
                with open(u.get_path('data/config.toml'), 'r', encoding='utf-8') as f:
                    config_toml = toml_load(f)
                    f.close()
        except Exception as e:
            l.warning(f'Error when loading data/config.toml: {e}')

        # ===== prepare config.json =====
        config_json = {}
        try:
            if os.path.exists(u.get_path('data/config.json')):
                with open(u.get_path('data/config.json'), 'r', encoding='utf-8') as f:
                    config_json = json_load(f)
                    f.close()
        except Exception as e:
            l.warning(f'Error when loading data/config.json: {e}')

        # ===== mix sources =====
        try:
            self.config = ConfigModel(**u.deep_merge_dict(config_env, config_yaml, config_toml, config_json))
        except ValidationError as e:
            raise u.SleepyException(f'Invaild config!\n{e}')

        # ===== optimize =====
        # status_list 中自动补全 id
        for i in range(len(self.config.status.status_list)):
            self.config.status.status_list[i].id = i

        # metrics_list 中 [static] 处理
        if '[static]' in self.config.metrics.allow_list:
            self.config.metrics.allow_list.remove('[static]')
            static_list = u.list_dirs(u.get_path('static/'))
            self.config.metrics.allow_list.extend(['/static/' + i for i in static_list])

        if self.config.main.debug:
            # *此处还未设置日志等级, 需手动判断*
            l.debug(f'[config] init took {perf()}ms')
