# 配置

## 配置源

四个来源，后面的覆盖前面的：

```
环境变量  →  config.yaml  →  config.toml  →  config.json
```

都不存在时全部走默认值，服务照常启动。

环境变量加 `SLEEPY_` 前缀，下划线表示层级：

```bash
SLEEPY_PORT=9010
SLEEPY_LOG_LEVEL=DEBUG           # -> log.level
SLEEPY_PLUGIN_METRICS_ENABLED=false
```

也可以写进项目根的 `.env` 文件。

## 服务

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `host` | `0.0.0.0` | 监听地址 |
| `port` | `9010` | 监听端口 |
| `dev` | `false` | 启用 dev token 登录，**仅开发环境** |
| `cors_origins` | `["*"]` | 允许跨域的来源。浏览器端客户端需要它 |
| `database` | `sqlite:///data/sleepy.db` | 数据库 URL |

```toml
host = "0.0.0.0"
port = 9010
database = "sqlite:///data/sleepy.db"
cors_origins = ["https://blog.example.com"]
```

MySQL / PostgreSQL 也支持，填对应的 SQLAlchemy URL 即可。SQLite 会自动开启 WAL。

## 日志

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `log.level` | `INFO` | 控制台日志等级 |
| `log.file` | `logs/{time:YYYY-MM-DD}.log` | 日志文件路径，设为 `null` 关闭 |
| `log.file_level` | `INFO` | 文件日志等级，`null` 则跟随 `level` |
| `log.rotation` | `1 days` | 轮转周期 |
| `log.retention` | `3 days` | 保留时长 |

```toml
[log]
level = "INFO"
file = "logs/{time:YYYY-MM-DD}.log"
retention = "7 days"
```

每条日志都带请求 ID，和响应头的 `X-Sleepy-Request-Id` 对得上。

## 实时推送

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `ping_interval` | `20` | SSE 心跳间隔（秒），`0` 关闭 |
| `ws_refresh_interval` | `5` | WebSocket 定期快照间隔（秒） |

推送以事件驱动为主，定期快照是兜底，用于纠正客户端短暂断连时漏掉的事件。

## 鉴权

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `auth_access_token_expires_minutes` | `60` | 管理 token 有效期（分钟） |
| `auth_refresh_token_expires_days` | `30` | refresh token 有效期（天） |
| `token_last_active_throttle_seconds` | `60` | token 活跃时间的写入节流间隔 |

设备 token 的有效期不在这里，由 `device-auth` 插件配置。

## 插件系统

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `plugins.disabled` | `[]` | 禁用的插件（按目录名） |
| `plugins.builtin_dir` | `builtin` | 内置插件目录 |
| `plugins.external_dir` | `plugins` | 外部插件目录 |

```toml
[plugins]
disabled = ["compat-v5"]      # 所有客户端都迁移完之后可以关掉
```

## 各插件的配置

插件自己的配置写在 `plugin.<插件目录名>` 下。

### `plugin.status`

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `presets` | 两个内置状态 | 状态预设列表 |
| `default` | `0` | 初始状态 id |

```toml
[[plugin.status.presets]]
id = 0
name = "活着"
desc = "目前在线，可以联系"
color = "awake"

[[plugin.status.presets]]
id = 1
name = "似了"
desc = "睡似了或者在忙别的事情"
color = "sleeping"
```

设置一个不在预设里的状态 id 会返回 400。

### `plugin.device-auth`

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `expires_days` | `0` | 设备 token 有效期（天），`0` 为永不过期 |

默认永不过期是有意的：设备脚本一旦部署很少有人回去更新，过期只会带来「某天状态突然不更新了」这种难排查的故障。

### `plugin.metrics`

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `enabled` | `true` | 是否统计 |
| `timezone` | `Asia/Shanghai` | 计算「今天」用的时区 |
| `flush_interval` | `30` | 计数落库间隔（秒） |
| `allow_list` | 见默认配置 | 计入统计的路径白名单 |

白名单是必要的——不限制的话，任意 404 路径都会在表里建一行。

Windows 上需要 `tzdata` 包（已在依赖里）；缺失时会退回 UTC 并给出警告，不会让服务失败。

### `plugin.frontend`

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `dist_dir` | `frontend/dist` | 前端构建产物目录 |
| `source_dir` | `frontend` | 前端源码目录 |
| `spa_fallback` | `true` | 未匹配路径是否回落到 `index.html` |

构建产物不存在时插件不注册任何路由，只在日志里提示，后端 API 不受影响。

## 完整示例

```toml
host = "0.0.0.0"
port = 9010
database = "sqlite:///data/sleepy.db"
cors_origins = ["*"]

[log]
level = "INFO"
retention = "7 days"

[plugins]
disabled = []

[plugin.metrics]
timezone = "Asia/Shanghai"

[plugin.device-auth]
expires_days = 0
```
