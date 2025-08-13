# coding: utf-8

from pydantic import BaseModel

# region user-config


class ConfigModel(BaseModel):
    '''
    配置 Model
    '''

    debug: bool = False
    '''
    是否启用调试模式 (显示更多日志)
    '''

    colorful_log: bool = True
    '''
    控制控制台输出日志是否有颜色及 Emoji 图标
    - 如在获取控制台输出时遇到奇怪问题可关闭
    - 建议使用 `log_file` 来获取日志文件 (日志文件始终不带颜色 & Emoji)
    '''

    log_file: str | None = 'running.log'
    '''
    保存日志文件目录 (留空禁用) \n
    如: `data/running.log` \n
    **注意: 不会自动切割日志**
    '''

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
