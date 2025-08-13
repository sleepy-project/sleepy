# coding: utf-8

from pydantic import BaseModel
import typing as t

# region user-config


class _LoggingConfigModel(BaseModel):
    '''
    日志配置 Model
    '''

    level: t.Literal['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] = 'INFO'
    '''
    日志等级
    - DEBUG
    - INFO
    - WARNING
    - ERROR
    - CRITICAL
    '''

    file: str | None = 'running.log'
    '''
    保存日志文件目录 (留空禁用) \n
    如: `running.log`
    '''

    rotating: bool = True
    '''
    是否启用日志轮转
    '''

    rotating_size: float = 1024
    '''
    日志轮转大小 (单位: KB)
    '''

    rotating_count: int = 5
    '''
    日志轮转数量
    '''


class ConfigModel(BaseModel):
    '''
    配置 Model
    '''

    log: _LoggingConfigModel = _LoggingConfigModel()

    database: str = 'sqlite:///data.db'
    '''
    数据库 url
    - SQLite: `sqlite:///文件名.db`
    - MySQL: `mysql://用户名:密码@主机:端口号/数据库名`
    - 更多: https://docs.sqlalchemy.org.cn/en/20/core/engines.html#backend-specific-urls
    '''

# endregion user-config


env_vaildate_json_keys = [
    'status_status_list',
    'metrics_allow_list',
    'plugins_enabled',
    'plugin'
]
'''
此列表中的键将会尝试解析为 json
(不包含 `sleepy_`)
'''
