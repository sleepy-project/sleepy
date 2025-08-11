# coding: utf-8
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from logging import Formatter, getLogger, DEBUG
from functools import wraps
from typing import Any

import flask
from colorama import Fore, Style
import pytz

l = getLogger(__name__)


class CustomFormatter(Formatter):
    '''
    自定义的 logging formatter
    '''
    symbols = {
        'DEBUG': '⚙️ ',
        'INFO': 'ℹ️ ',
        'WARNING': '⚠️ ',
        'ERROR': '❌',
        'CRITICAL': '💥'
    }
    replaces_nocolor = {
        'DEBUG': f'[DEBUG]',
        'INFO': f'[INFO] ',
        'WARNING': f'[WARN] ',
        'ERROR': f'[ERROR]',
        'CRITICAL': f'[CRIT] '
    }
    replaces_colorful = {
        'DEBUG': f'{Fore.BLUE}[DEBUG]{Style.RESET_ALL}',
        'INFO': f'{Fore.GREEN}[INFO]{Style.RESET_ALL} ',
        'WARNING': f'{Fore.YELLOW}[WARN]{Style.RESET_ALL} ',
        'ERROR': f'{Fore.RED}[ERROR]{Style.RESET_ALL}',
        'CRITICAL': f'{Fore.MAGENTA}[CRIT]{Style.RESET_ALL} '
    }
    default_symbol = '📢'
    colorful: bool

    def __init__(self, colorful: bool = True, timezone: str | None = None):
        super().__init__()
        if colorful:
            self.replaces = self.replaces_colorful
        else:
            self.replaces = self.replaces_nocolor
            self.symbols = {}
            self.default_symbol = ''
        self.timezone = timezone

    def format(self, record):
        timestamp = (datetime.now(pytz.timezone(self.timezone)) if self.timezone else datetime.now()).strftime('[%Y-%m-%d %H:%M:%S]')  # 格式化时间
        symbol = f' {self.symbols.get(record.levelname, self.default_symbol)}'  # 表情符号
        level = self.replaces.get(record.levelname, f'[{record.levelname}]')  # 日志等级
        file = relative_path(record.pathname)  # 源文件名
        line = record.lineno  # 文件行号

        message = super().format(record)  # 日志内容
        formatted_message = f"{timestamp}{symbol} {level} | {file}:{line} | {message}"
        return formatted_message


def cache_response(*args):
    '''
    给返回添加缓存标头
    '''
    resp = flask.make_response(*args)
    resp.headers['Cache-Control'] = 'max-age=86400, must-revalidate'
    resp.headers['Expires'] = '86400'
    return resp


def no_cache_response(*args):
    '''
    给返回添加阻止缓存标头
    '''
    resp = flask.make_response(*args)
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


def require_secret(redirect_to: str | None = None):
    '''
    (装饰器) require_secret, 用于指定函数需要 secret 鉴权
      - 不带参数调用: `@require_secret()`
      - 带参数调用: `@require_secret(redirect_to='/path')`
    '''

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            # 1. body
            body: dict = flask.request.get_json(silent=True) or {}
            if body and body.get('secret') == flask.g.secret:
                l.debug('[Auth] Verify secret Success from Body')
                return view_func(*args, **kwargs)

            # 2. param
            elif flask.request.args.get('secret') == flask.g.secret:
                l.debug('[Auth] Verify secret Success from Param')
                return view_func(*args, **kwargs)

            # 3. header (Sleepy-Secret)
            elif flask.request.headers.get('Sleepy-Secret') == flask.g.secret:
                l.debug('[Auth] Verify secret Success from Header (Sleepy-Secret)')
                return view_func(*args, **kwargs)

            # 4. header (Authorization)
            auth_header = flask.request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer ') and auth_header[7:] == flask.g.secret:
                l.debug('[Auth] Verify secret Success from Header (Authorization)')
                return view_func(*args, **kwargs)

            # 5. cookie (sleepy-secret)
            elif flask.request.cookies.get('sleepy-secret') == flask.g.secret:
                l.debug('[Auth] Verify secret Success from Cookie (sleepy-secret)')
                return view_func(*args, **kwargs)

            # -1. no any secret
            else:
                if redirect_to:
                    l.debug(f'[Auth] Verify secret failed, redirect to {redirect_to}')
                    return flask.redirect(redirect_to, 302)
                else:
                    l.debug('[Auth] Verify secret Failed')
                    raise APIUnsuccessful(401, 'Wrong Secret')
        return wrapper
    return decorator


class SleepyException(Exception):
    '''
    Custom Exception for sleepy
    '''

    def __init__(self, msg: str | None = None):
        '''
        SleepyException

        :param msg: 错误信息
        '''
        if msg:
            self.msg = msg

    def __str__(self):
        return self.msg


class APIUnsuccessful(Exception):
    '''
    api 接口调用失败异常
    '''
    codes = {
        # 4xx - 客户端错误
        400: 'Bad Request',
        401: 'Unauthorized',
        402: 'Payment Required',
        403: 'Forbidden',
        404: 'Not Found',
        405: 'Method Not Allowed',
        406: 'Not Acceptable',
        407: 'Proxy Authentication Required',
        408: 'Request Timeout',
        409: 'Conflict',
        410: 'Gone',
        411: 'Length Required',
        412: 'Precondition Failed',
        413: 'Payload Too Large',
        414: 'URI Too Long',
        415: 'Unsupported Media Type',
        416: 'Range Not Satisfiable',
        417: 'Expectation Failed',
        418: "I'm a Teapot",  # RFC 2324
        422: 'Unprocessable Entity',  # WebDAV
        423: 'Locked',  # WebDAV
        424: 'Failed Dependency',  # WebDAV
        425: 'Too Early',  # RFC 8470
        426: 'Upgrade Required',
        428: 'Precondition Required',
        429: 'Too Many Requests',
        431: 'Request Header Fields Too Large',
        451: 'Unavailable For Legal Reasons',  # RFC 7725

        # 5xx - 服务器错误
        500: 'Internal Server Error',
        501: 'Not Implemented',
        502: 'Bad Gateway',
        503: 'Service Unavailable',
        504: 'Gateway Timeout',
        505: 'HTTP Version Not Supported',
        506: 'Variant Also Negotiates',  # RFC 2295
        507: 'Insufficient Storage',  # WebDAV
        508: 'Loop Detected',  # WebDAV
        510: 'Not Extended',
        511: 'Network Authentication Required',
    }
    '''
    http code 对应表, 由 DeepSeek 扩充
    '''

    def __init__(self, code: int = 500, message: str | None = None):
        '''
        创建 APIUnsuccessful 异常

        :param code: HTTP 状态码\n
            常用状态码:
            - 400 - 错误的请求 (Bad Request)
            - 401 - 未授权 (Unauthorized)
            - 403 - 禁止访问 (Forbidden)
            - 404 - 未找到 (Not Found)
            - 405 - 方法被禁止 (Method Not Allowed)
            - 429 - 请求过多 (Too Many Requests)
            - 500 - 服务器内部错误 (Internal Server Error)
            - 503 - 服务不可用 (Service Unavailable)

            *完整列表参考 `codes`*

        :param message: 错误信息
        '''
        self.code = code
        self.details = self.codes.get(code, f'HTTP Error {code}')
        self.message = message

    def __str__(self):
        return f'{self.code} {self.details} ({self.message})'


def list_files(path: str, include_subfolder: bool = False, name_only: bool = False, strict_exist: bool = False, ext: str = '') -> list:
    '''
    列出目录下的**文件**列表

    :param path: 目录路径
    :param include_subfolder: 是否包括子目录的文件 *(递归查找)*
    :param name_only: 是否仅返回文件名
    :param strict_exist: 目标目录不存在时是否抛出错误 *(为否则返回空列表)*
    :param ext: 指定文件扩展名 *(只有文件以此结尾才会计入)*
    '''

    try:
        rawlst = os.listdir(path)
        endlist: list[str] = []
        for i in rawlst:
            fullname_i = str(Path(path).joinpath(i))
            if os.path.isdir(fullname_i) and include_subfolder:
                # 如为目录，且包含子目录 -> 递归
                endlist.extend([
                    n if name_only else str(Path(i).joinpath(n))
                    for n in list_files(
                        path=fullname_i,
                        include_subfolder=include_subfolder,
                        name_only=name_only,
                        strict_exist=strict_exist,
                        ext=ext
                    )
                ])
            # 否则为文件 -> 添加
            endlist.append(i if name_only else fullname_i)
    except FileNotFoundError:
        # 找不到目标文件夹
        if strict_exist:
            raise
        else:
            return []
    else:
        if ext:
            newlst = []
            for i in endlist:
                if i.endswith(ext):
                    newlst.append(i)
            return newlst
        else:
            return endlist


def list_dirs(path: str, strict_exist: bool = False, name_only: bool = False) -> list:
    '''
    列出目录下的**目录**列表

    :param path: 目录路径
    :param strict_exist: 目标目录不存在时是否抛出错误 *(为否则返回空列表)*
    :param name_only: 是否仅返回目录名
    '''

    try:
        rawlst = os.listdir(path)
        endlist: list[str] = []
        for i in rawlst:
            fullname_i = str(Path(path).joinpath(i))
            if os.path.isdir(fullname_i) and (not '__pycache__' in fullname_i):
                # 如为目录 -> 追加
                endlist.append(i if name_only else fullname_i)
        return endlist
    except FileNotFoundError:
        # 找不到目标文件夹
        if strict_exist:
            raise
        else:
            return []


_themes_available_cache = sorted(list_dirs('theme', name_only=True))


def themes_available() -> list[str]:
    if l.level == DEBUG:
        return sorted(list_dirs('theme', name_only=True))
    else:
        return _themes_available_cache


def tobool(string, throw: bool = False) -> bool | None:
    '''
    将形似 `true`, `1`, `yes` 之类的内容转换为布尔值

    :param throw: 控制无匹配项时是否直接抛出 `ValueError` (为否则返回 `None`)
    :return: `True` or `False` or `None` (如果不在 `booldict` 内)
    '''
    booldict = {
        # 此列表中的项 (强制小写) 会转换为对应的布尔值
        'true': True,
        'false': False,
        '1': True,
        '0': False,
        't': True,
        'f': False,
        'yes': True,
        'no': False,
        'y': True,
        'n': False,
        'on': True,
        'off': False,
        'enable': True,
        'disable': False,
        'v': True,
        'x': False,
        'none': None,
        'null': None,
        'nope': None
    }
    ret = booldict.get(str(string).lower(), None)
    assert ret or (not throw), ValueError
    return ret


def current_dir() -> str:
    '''
    获取当前主程序所在目录
    '''
    return str(Path(__file__).parent)


def get_path(path: str, create_dirs: bool = True, is_dir: bool = False) -> str:
    '''
    相对路径 (基于主程序目录) -> 绝对路径

    :param path: 相对路径
    :param create_dirs: 是否自动创建目录（如果不存在）
    :param is_dir: 目标是否为目录
    :return: 绝对路径
    '''
    if path == '/data/data.json' and current_dir().startswith('/var/task'):
        # 适配 Vercel 部署 (调整 data/data.json 路径为可写的 /tmp/)
        full_path = '/tmp/sleepy/data/data.json'
    else:
        full_path = str(Path(__file__).parent.joinpath(path))
        if create_dirs:
            # 自动创建目录
            if is_dir:
                os.makedirs(full_path, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
    return full_path


def relative_path(path: str) -> str:
    '''
    绝对路径 -> 相对路径
    '''
    return os.path.relpath(path)


def perf_counter():
    '''
    获取一个性能计数器, 执行返回函数来结束计时, 并返回保留两位小数的毫秒值
    '''
    start = time.perf_counter()
    return lambda: round((time.perf_counter() - start)*1000, 2)


def process_env_split(keys: list[str], value: Any) -> dict:
    '''
    处理环境变量配置项分割
    - `page_name=wyf9` -> `['page', 'name'], 'wyf9'` -> `{'page': {'name': 'wyf9'}, 'page_name': 'wyf9'}`
    '''
    if len(keys) == 1:
        return {keys[0]: value}
    else:
        sub_dict = process_env_split(keys[1:], value)
        result = {
            keys[0]: sub_dict,
            '_'.join(keys): value,
            keys[0] + '_' + keys[1]: sub_dict[keys[1]]
        }
        return result


def deep_merge_dict(*dicts: dict) -> dict:
    '''
    递归合并多个嵌套字典 (先后顺序) \n
    例:
    ```
    >>> dict1 = {'a': {'x': 1}, 'b': 2, 'n': 1}
    >>> dict2 = {'a': {'y': 3}, 'c': 4, 'n': 2}
    >>> dict3 = {'a': {'z': 5}, 'd': 6, 'n': 3}
    >>> print(deep_merge_dict(dict1, dict2, dict3))
    {'a': {'z': 5, 'x': 1, 'y': 3}, 'b': 2, 'n': 3, 'c': 4, 'd': 6}
    ```
    '''
    if not dicts:
        return {}

    # 创建基础字典的深拷贝（避免修改原始输入）
    base = {}
    for d in dicts:
        if d:  # 跳过空字典
            base.update(d.copy())

    # 递归合并所有字典
    for d in dicts:
        if d:
            for key, value in d.items():
                # 如果当前键存在于基础字典且双方值都是字典，则递归合并
                if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                    # 递归合并嵌套字典
                    base[key] = deep_merge_dict(base[key], value)
                else:
                    # 直接赋值（覆盖原有值）
                    base[key] = value

    return base
