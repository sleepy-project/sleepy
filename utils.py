# coding: utf-8

import os
from pathlib import Path
from datetime import datetime
import time
from typing import Any

from logging import Formatter


class CustomFormatter(Formatter):
    '''
    自定义的 logging formatter
    '''
    # symbols = {
    #     'DEBUG': '⚙️ ',
    #     'INFO': 'ℹ️ ',
    #     'WARNING': '⚠️ ',
    #     'ERROR': '❌',
    #     'CRITICAL': '💥'
    # }
    replaces = {
        'DEBUG': f'[DEBUG]',
        'INFO': f'[INFO] ',
        'WARNING': f'[WARN] ',
        'ERROR': f'[ERROR]',
        'CRITICAL': f'[CRIT] '
    }
    # replaces_colorful = {
    #     'DEBUG': f'{Fore.BLUE}[DEBUG]{Style.RESET_ALL}',
    #     'INFO': f'{Fore.GREEN}[INFO]{Style.RESET_ALL} ',
    #     'WARNING': f'{Fore.YELLOW}[WARN]{Style.RESET_ALL} ',
    #     'ERROR': f'{Fore.RED}[ERROR]{Style.RESET_ALL}',
    #     'CRITICAL': f'{Fore.MAGENTA}[CRIT]{Style.RESET_ALL} '
    # }
    # default_symbol = '📢'
    # colorful: bool

    # def __init__(self, colorful: bool = True):
    # super().__init__()
    # if colorful:
    #     self.replaces = self.replaces_colorful
    # else:
    #     self.replaces = self.replaces_nocolor
    #     self.symbols = {}
    #     self.default_symbol = ''

    def format(self, record):
        timestamp = datetime.now().strftime('[%Y-%m-%d %H:%M:%S]')  # 格式化时间
        # symbol = f' {self.symbols.get(record.levelname, self.default_symbol)}'  # 表情符号
        level = self.replaces.get(record.levelname, f'[{record.levelname}]')  # 日志等级
        file = os.path.relpath(record.pathname)  # 源文件名
        line = record.lineno  # 文件行号

        message = super().format(record)  # 日志内容
        # formatted_message = f"{timestamp}{symbol} {level} | {file}:{line} | {message}"
        formatted_message = f"{timestamp} {level} | {file}:{line} | {message}"
        return formatted_message


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
