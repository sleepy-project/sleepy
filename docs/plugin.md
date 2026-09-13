# 插件开发

sleepy 的 core 是空壳：它提供机制（HTTP、配置、日志、存储、鉴权、事件、广播），业务功能全部由插件实现。状态、设备、统计、前端、v5 兼容层都是插件。

## 两个目录

| 目录 | 用途 |
|---|---|
| `builtin/` | 内置插件，随仓库分发、受 git 跟踪 |
| `plugins/` | 你自己装的插件，不受 git 跟踪 |

`builtin/` 先加载，`plugins/` 后加载，**同名时后者覆盖前者**——想替换某个内置实现，把自己的版本放进 `plugins/` 同名目录即可，不需要改动仓库代码。

不需要某个插件时在配置里关掉：

```toml
[plugins]
disabled = ["compat-v5", "metrics"]
```

## 最小插件

一个插件是一个目录，需要 `pyproject.toml` 和 `__init__.py`：

```
plugins/hello/
├── pyproject.toml
└── __init__.py
```

```toml
# pyproject.toml
[project]
name = "hello"
version = "1.0.0"
description = "示例插件"

[tool.sleepy]
enabled = true
dependencies = []          # 依赖的其他插件
```

```python
# __init__.py
from core.plugin import PluginBase, PluginMetadata


class Plugin(PluginBase):
    def on_load(self):
        self.add_route('/api/v1/hello', self.hello, ['GET'], tags=['hello'])

    async def hello(self):
        return {'hello': 'world'}
```

模块里必须有一个叫 `Plugin` 的类，继承 `PluginBase`。

## 生命周期

| 钩子 | 时机 | 能做什么 |
|---|---|---|
| `__init__` | 实例化 | `register_model()`、`register_config()`、`add_cli_command()`、填 `exports` |
| `on_load` | 加载完成 | 注册路由。**配置此时已就绪** |
| `on_startup` | 应用启动（有 event loop） | 起后台任务 |
| `on_shutdown` | 应用关闭 | 收尾、flush |
| `on_unload` | 插件卸载 | 释放资源 |

顺序是 `__init__` → 解析配置 → `on_load` → 建表 → `on_startup`。

配置在 `on_load` **之前**解析，所以可以按配置决定注册哪些路由（`builtin/frontend` 就是这么做的：构建产物不存在时它一条路由都不注册）。

## 配置

```python
from pydantic import BaseModel

class HelloConfig(BaseModel):
    greeting: str = 'world'
    times: int = 1


class Plugin(PluginBase):
    def __init__(self, metadata):
        super().__init__(metadata)
        self.register_config(HelloConfig)

    @property
    def config(self) -> HelloConfig:
        return self.get_config()
```

用户在 `plugin.<插件目录名>` 下配置：

```toml
[plugin.hello]
greeting = "sleepy"
times = 3
```

环境变量也行：`SLEEPY_PLUGIN_HELLO_GREETING=sleepy`。

## 数据表

```python
from sqlmodel import Field, SQLModel

class HelloData(SQLModel, table=True):
    __tablename__ = 'hello_data'
    id: str = Field(primary_key=True)
    value: int = Field(default=0)


class Plugin(PluginBase):
    def __init__(self, metadata):
        super().__init__(metadata)
        self.register_model(HelloData)
```

建表发生在所有插件加载完成之后，所以在 `__init__` 或 `on_load` 里声明都可以。

只存少量键值对的话，core 的 `PluginKV` 表够用，不必自建表：

```python
from core.models import PluginKV
record = sess.get(PluginKV, ('hello', 'some_key'))
```

## 路由

```python
self.add_route(path, endpoint, methods, **kwargs)
```

`kwargs` 会原样传给 FastAPI 的 `add_api_route`，所以 `response_model`、`tags`、`dependencies`、`status_code` 都能用。

两个特殊参数：

- `override=True` — 覆盖已存在的同路径路由（会先把旧的移除）
- `low_priority=True` — 推迟到所有插件路由之后再注册

**catch-all 路由必须开 `low_priority`。** 插件按名称排序加载，一个字母序靠前的插件注册的 `/{path:path}` 会抢先匹配掉后面所有插件的接口。

也可以挂 ASGI 应用：

```python
from fastapi.staticfiles import StaticFiles
self.mount('/assets', StaticFiles(directory='...'), name='my-assets')
```

## 鉴权

```python
from fastapi import Security
from core.auth import AUTH_ACCESS_PREFIX, DEVICE_PREFIX, TokenDep

admin_auth = TokenDep((AUTH_ACCESS_PREFIX,))              # 仅管理 token
write_auth = TokenDep((DEVICE_PREFIX, AUTH_ACCESS_PREFIX))  # 设备或管理

self.add_route('/api/v1/thing', self.handler, ['PUT'],
               dependencies=[Security(write_auth)])
```

需要校验来自 body 或 query 的 token（拿不到 Security 依赖）时，直接用 `TokenDep(..., throw=False).verify(sess, value)`。

## 事件

事件用于插件之间协作，可以拦截。

```python
from core.events import BaseEvent

class ThingHappened(BaseEvent):
    id = 'thing_happened'

    def __init__(self, value: int):
        super().__init__()
        self.value = value
```

发布：

```python
evt = await self.emit(ThingHappened(42))
if evt.intercepted:
    response, code = evt.interception
    ...
```

订阅（按事件类或字符串 id 都行，用字符串就不必 import 对方模块）：

```python
def on_device_set(evt):
    evt.status = evt.status.upper()      # 直接改事件对象
    # evt.intercept({'error': 'nope'}, 403)  # 也可以拦下

self.subscribe('device_set', on_device_set)
```

handler 可以是同步或异步；返回值会被忽略，直接修改事件对象即可。任一 handler 抛异常不会影响其余 handler。插件卸载时订阅自动清除。

内置插件发布的事件：

| 事件 id | 来源 | 可拦截 |
|---|---|---|
| `device_set` | device | 是 |
| `device_removed` | device | 否 |
| `device_cleared` | device | 否 |
| `status_updated` | status | 是 |
| `app_startup` / `app_shutdown` | core | 否 |
| `stream_connected` / `stream_disconnected` | core | 否 |

## 实时推送

```python
await self.broadcast('thing-changed', {'value': 42})
```

同时推给 SSE 和 WebSocket。

新连接接入时会收到一份快照，插件贡献自己那部分：

```python
def on_load(self):
    self.register_snapshot_provider(self._snapshot)

def _snapshot(self) -> dict:
    return {'things': [...]}
```

所有 provider 的返回值合并成一个字典下发。这是 `/api/v1/status` 能同时包含状态和设备的原因——两个插件都注册了 provider，彼此不知道对方存在。

## 插件间调用

```python
class Plugin(PluginBase):
    def __init__(self, metadata):
        super().__init__(metadata)
        self.exports = {'do_thing': self.do_thing}
```

别的插件这样取用：

```python
from core.plugin import plugin_manager

api = plugin_manager.api('hello')
if 'do_thing' in api:
    api['do_thing'](...)
```

**用 `exports` 而不是直接 import。** 插件是按文件路径动态加载的，没有稳定的 import 路径。

依赖的插件可能被禁用，取不到就优雅降级——`compat-v5` 在 metrics 缺席时返回「统计未启用」，而不是报错。

硬依赖写在 `pyproject.toml` 里，加载顺序会自动按拓扑排序：

```toml
[tool.sleepy.dependencies]
device = "*"
status = ">=1.0.0"
```

## CLI 命令

```python
self.add_cli_command(
    command='hello',
    handler=self.cli_hello,
    help='Say hello',
    arguments=[(['--name'], {'default': 'world'})]
)

def cli_hello(self, args):
    print(f'hello {args.name}')
```

```bash
python main.py hello --name sleepy
```

handler 同步异步都可以。

## 修改响应

```python
def modify_response(self, request, response, endpoint):
    response.headers['X-My-Header'] = 'hi'
    return response
```

这个钩子在**每个请求**的路径上，别在里面做阻塞操作。`metrics` 插件用它累加计数，但只写内存，落库交给后台任务。

只有真正覆盖了这个方法的插件才会进入响应链。
