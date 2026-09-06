# Sleepy v7

> 看看我是不是在线。

v7 的形态是 **空壳 core + 内置插件**：`core/` 只提供机制（HTTP、配置、日志、存储、鉴权、事件总线、广播、插件加载），所有业务功能都是插件。

必需的插件放在 `builtin/`，随仓库分发、受 git 跟踪 —— `git clone` 下来直接就能跑，不需要联网下载任何东西。

## 快速开始

```bash
uv sync
uv run main.py
```

首次启动后设置管理密码：

```bash
curl -X POST http://127.0.0.1:9010/api/v1/init \
     -H 'Content-Type: application/json' \
     -d '{"password": "你的密码", "hashed": false}'
```

## 旧客户端怎么接

**现有的 v5 客户端不需要修改。**

1. 登录拿到管理 token，签发一个设备 token：

   ```bash
   curl -X POST http://127.0.0.1:9010/api/v1/tokens \
        -H "X-Sleepy-Token: <管理 token>" \
        -H 'Content-Type: application/json' \
        -d '{"name": "我的电脑"}'
   ```

2. 把返回的 `token` 填进客户端脚本原有的 `SECRET` 变量。

就这样。`compat-v5` 插件把旧的 `secret` 当作设备 token 校验，并完成 `show_name` → `name`、`app_name` → `status` 的字段映射。

不需要兼容层时在配置里关掉：

```toml
[plugins]
disabled = ["compat-v5"]
```

## 目录结构

```
core/       空壳框架，不含任何业务功能
builtin/    内置插件，随仓库分发
plugins/    用户自行安装的插件（不受 git 跟踪，同名时覆盖 builtin）
tests/      测试
```

## 内置插件

| 插件 | 作用 |
|---|---|
| `status` | 手动状态、状态预设、整体状态查询 |
| `device` | 设备上报、设备列表、隐私模式 |
| `device-auth` | 设备 Token 的签发、列出、撤销 |
| `compat-v5` | v5 旧版 API 兼容层 |

## API

主干接口在 `/api/v1/` 下，完整文档见 `/docs`（Swagger）或 `/redoc`。

`/api/status/*`、`/api/device/*`、`/api/meta` 是 v5 兼容路径，由 `compat-v5` 插件提供。

## 开发

```bash
uv sync --extra dev
uv run pytest -q
```

写插件参考 `builtin/` 下的任意一个，插件基类在 `core/plugin.py`。

## License

This project is licensed under the GNU General Public License v3.0.
See the [LICENSE](./LICENSE) file for details.

Copyright © 2026 sleepy-project contributors.
