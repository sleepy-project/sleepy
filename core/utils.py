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

import os
import time
import typing as t
from pathlib import Path

ROOT_DIR: Path = Path(__file__).resolve().parent.parent
'''
项目根目录

`core/` 是包目录, 根目录在其上一层。
v6 的 `utils.get_path()` 基于 `utils.py` 自身位置解析, 模块移入 `core/` 后会整体偏移一层,
因此这里显式定义根目录, 所有相对路径都基于它。
'''


def __replace_code_tags(text: str) -> str:
    '''
    markdown -> html
    '''
    while '`' in text:
        text = text.replace('`', '<code>', 1).replace('`', '</code>', 1)
    return text


def cnen(cn: str, en: str) -> str:
    '''
    生成中英双语说明 (用于 OpenAPI 描述)
    '''
    return f'{__replace_code_tags(cn)}<br/><i>{__replace_code_tags(en)}</i>'


def current_dir() -> str:
    '''
    获取项目根目录
    '''
    return str(ROOT_DIR)


def get_path(path: str, create_dirs: bool = True, is_dir: bool = False) -> str:
    '''
    相对路径 (基于项目根目录) -> 绝对路径

    :param path: 相对路径
    :param create_dirs: 是否自动创建目录 (如果不存在)
    :param is_dir: 目标是否为目录
    :return: 绝对路径
    '''
    full_path = str(ROOT_DIR.joinpath(path))
    if create_dirs:
        if is_dir:
            os.makedirs(full_path, exist_ok=True)
        else:
            parent = os.path.dirname(full_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
    return full_path


def perf_counter() -> t.Callable[[], float]:
    '''
    获取一个性能计数器, 执行返回的函数来结束计时, 并返回保留两位小数的毫秒值
    '''
    start = time.perf_counter()
    return lambda: round((time.perf_counter() - start) * 1000, 2)


def process_env_split(keys: list[str], value: t.Any) -> dict:
    '''
    处理环境变量配置项分割
    - `page_name=wyf9` -> `['page', 'name'], 'wyf9'` -> `{'page': {'name': 'wyf9'}, 'page_name': 'wyf9'}`

    同时生成嵌套与扁平两种键, 因为无法从环境变量名本身判断下划线是层级分隔还是名称的一部分。
    '''
    if len(keys) == 1:
        return {keys[0]: value}
    sub_dict = process_env_split(keys[1:], value)
    return {
        keys[0]: sub_dict,
        '_'.join(keys): value,
        keys[0] + '_' + keys[1]: sub_dict[keys[1]]
    }


def deep_merge_dict(*dicts: dict | None) -> dict:
    '''
    递归合并多个嵌套字典 (后者覆盖前者) \n
    例:
    ```
    >>> dict1 = {'a': {'x': 1}, 'b': 2, 'n': 1}
    >>> dict2 = {'a': {'y': 3}, 'c': 4, 'n': 2}
    >>> dict3 = {'a': {'z': 5}, 'd': 6, 'n': 3}
    >>> deep_merge_dict(dict1, dict2, dict3)
    {'a': {'x': 1, 'y': 3, 'z': 5}, 'b': 2, 'n': 3, 'c': 4, 'd': 6}
    ```
    '''
    base: dict = {}
    for d in dicts:
        if not d:
            continue
        for key, value in d.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                base[key] = deep_merge_dict(base[key], value)
            else:
                base[key] = value
    return base


def tobool(value: t.Any, default: bool | None = None) -> bool | None:
    '''
    将任意值转为 bool

    用于兼容 v5 客户端: 它们的 `using` 可能是 `true` / `True` / `1` / `yes` 等字符串。

    :param value: 待转换的值
    :param default: 无法判断时的返回值
    '''
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ('true', 'yes', 'y', 'on', '1'):
            return True
        if lowered in ('false', 'no', 'n', 'off', '0'):
            return False
    return default
