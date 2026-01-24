# coding: utf-8

from pydantic import BaseModel, PositiveInt
import typing as t

# region user-config
class _StatusItemModel(BaseModel):
    '''
    状态列表设置 (`status.status_list`) 中的项
    '''

    id: int = -1
    '''
    状态索引 (id)
    - *应由 `config.Config.__init__()` 动态设置*
    '''

    name: str
    '''
    `status.status_list[*].name`
    状态名称
    '''

    desc: str
    '''
    `status.status_list[*].desc`
    状态描述
    '''

    color: str = 'awake'
    '''
    `status.status_list[*].color`
    状态颜色 \n
    对应 `static/style.css` 中的 `.sleeping` `.awake` 等类 (可自行前往修改)
    '''
class _PageConfigModel(BaseModel):
    '''
    页面内容配置 (`page`)
    '''

    status_list: list[_StatusItemModel] = [
        _StatusItemModel(
            name='活着',
            desc='目前在线，可以通过任何可用的联系方式联系本人。',
            color='awake'
        ),        
        _StatusItemModel(
            name='似了',
            desc='睡似了或其他原因不在线，紧急情况请使用电话联系。',
            color='sleeping'
        )
    ]
    
    name: str = 'User'
    '''
    `page.name`
    你的名字
    - 将显示在网页中的 `[User]'s Status:` 处
    '''

    title: str = f'{name} Alive?'
    '''
    `page.title`
    页面标题 (`<title>`)
    '''

    desc: str = f'{name} \'s Online Status Page'
    '''
    `page.desc`
    页面详情 (用于 SEO, 或许吧)
    - *`<meta name="description">`*
    '''
    favicon: str = '/favicon.ico'
    '''
    `page.favicon`
    页面图标 (favicon) url, 默认为 /favicon.ico
    - *可为绝对路径 / 相对路径 url*
    '''

    background: str = 'https://imgapi.siiway.top/image'
    '''
    `page.background`
    背景图片 url / api
    - *默认为 `https://imgapi.siiway.top/image` (https://github.com/siiway/imgapi)*
    '''

    learn_more_text: str = 'GitHub Repo'
    '''
    `page.learn_more_text`
    更多信息链接的提示
    - *默认为 `GitHub Repo`*
    '''

    learn_more_link: str = 'https://github.com/sleepy-project/sleepy'
    '''
    `page.learn_more_link`
    更多信息链接的目标
    - *默认为本仓库链接*
    '''

    more_text: str = ''
    '''
    `page.more_text`
    内容将在状态页底部 learn_more 上方插入 (不转义)
    - *你可以在此中插入 统计代码 / 备案号 等信息*
    '''

    theme: str = 'default'
    '''
    `page.theme`
    设置页面的默认主题
    - 主题名即为 `theme/` 下的文件夹名
    '''

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

    file: str | None = 'logs/{time:YYYY-MM-DD}.log'
    '''
    日志文件保存格式 (for Loguru)
    - 设置为 None 以禁用
    '''

    file_level: t.Literal['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] | None = 'INFO'
    '''
    单独设置日志文件中的日志等级, 如设置为 None 则使用 level 设置
    - DEBUG
    - INFO
    - WARNING
    - ERROR
    - CRITICAL
    '''

    rotation: str | int = '1 days'
    '''
    配置 Loguru 的 rotation (轮转周期) 设置
    '''

    retention: str | int = '3 days'
    '''
    配置 Loguru 的 retention (轮转保留) 设置
    '''


class ConfigModel(BaseModel):
    '''
    配置 Model
    '''

    host: str = '0.0.0.0'
    '''
    服务监听地址 (仅在直接启动 main.py 时有效)
    '''

    port: PositiveInt = 9010
    '''
    服务监听端口 (仅在直接启动 main.py 时有效)
    '''

    dev: bool = False
    '''
    启用 dev Token 登录 (仅用于开发环境)
    '''
    metrics: bool = False
    '''
    启用 统计 (没写)
    '''
    metrics: bool = False
    '''
    启用 统计 (没写)
    '''

    # workers: PositiveInt = 2
    # '''
    # 服务 Worker 数 (仅在直接启动 main.py 时有效)
    # '''

    log: _LoggingConfigModel = _LoggingConfigModel()
    page: _PageConfigModel = _PageConfigModel()
    page: _PageConfigModel = _PageConfigModel()

    database: str = 'sqlite:///data.db'
    '''
    数据库 url
    - SQLite: `sqlite:///文件名.db`
    - MySQL: `mysql://用户名:密码@主机:端口号/数据库名`
    - 更多: https://docs.sqlalchemy.org.cn/en/20/core/engines.html#backend-specific-urls
    '''

    cache_age: int = 1200
    '''
    `main.cache_age`
    静态资源缓存时间 (秒)
    - *建议设置为 20 分钟 (1200s)*
    '''

    


    cache_age: int = 1200
    '''
    `main.cache_age`
    静态资源缓存时间 (秒)
    - *建议设置为 20 分钟 (1200s)*
    '''

    


    ping_interval: int = 20
    '''
    Event-Stream Ping 间隔 (单位: 秒, 设置为 0 禁用)
    '''

    ws_refresh_interval: PositiveInt = 5
    '''
    /api/ws 推送刷新间隔 (秒)
    '''

    auth_access_token_expires_minutes: PositiveInt = 60
    '''
    Auth Token (管理登录) 过期时间 (分钟)
    '''

    auth_refresh_token_expires_days: PositiveInt = 30
    '''
    Refresh Token (管理登录) 过期时间 (天)
    '''

    device_token_expires_days: PositiveInt = 365
    '''
    (默认) Device Token (设备更新状态密钥) 过期时间 (天)
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
