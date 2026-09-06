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
Sleepy core —— 空壳框架

core 提供机制, 插件提供策略。这里不含任何业务功能:
设备、状态、统计、前端都由 `builtin/` 下的插件实现。

插件应当按完整路径导入所需组件, 例如:

```python
from core.auth import SessionDep, TokenDep, DEVICE_PREFIX
from core.plugin import PluginBase, PluginMetadata
from core.events import BaseEvent
from core import errors as e
```

本文件刻意不做聚合导出 —— `core.config` 等模块在导入期就会被 `core.app` 拉起,
在包的 `__init__` 里再转发一层会形成循环导入。
'''
