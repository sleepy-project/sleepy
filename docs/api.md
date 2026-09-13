# API 参考

主干接口在 `/api/v1/` 下。服务跑起来后，`/docs`（Swagger）和 `/redoc` 提供可交互的完整文档，本页是速查。

`/api/status/*`、`/api/device/*`、`/api/meta`、`/api/metrics` 是 v5 兼容路径，由 `compat-v5` 插件提供，见 [migration.md](./migration.md)。

## 凭据

两种 token，用途不同：

| 类型 | 获取方式 | 有效期 | 用途 |
|---|---|---|---|
| **管理 token** | `POST /api/v1/auth/login` | 默认 60 分钟，可用 refresh token 续 | 管理面板、改全局状态 |
| **设备 token** | `POST /api/v1/tokens` | 默认永不过期 | 设备上报 |

设备 token 刻意做成长期有效且不轮换——Magisk 的 `service.sh`、AutoX.js 脚本没有能力实现 refresh 流程。

三种传递方式都接受：

```
X-Sleepy-Token: <token>
Authorization: Bearer <token>
?secret=<token>          # 仅 v5 兼容路径
```

## 初始化与登录

| 方法 | 路径 | 凭据 | 说明 |
|---|---|---|---|
| GET | `/api/v1/init` | — | 查询是否已设置管理密码 |
| POST | `/api/v1/init` | — | 首次设置管理密码，已设置时返回 409 |
| POST | `/api/v1/auth/login` | — | 登录，返回 access + refresh token |
| POST | `/api/v1/auth/refresh` | — | 用 refresh token 换新的 access token |
| GET | `/api/v1/auth/check` | 管理 / 设备 | 校验 token 是否有效并返回 `web`、`dev` 或 `device` 类型 |

```bash
# 设置密码
curl -X POST /api/v1/init -d '{"password": "pw", "hashed": false}'

# 登录
curl -X POST /api/v1/auth/login -d '{"password": "pw", "hashed": false}'
# -> {"token": "...", "refresh_token": "...", "expires_at": 1788..., "type": "web"}
```

`hashed: false` 表示传的是明文，服务端会先做一次 sha256；客户端也可以自己 sha256 后传 `hashed: true`。

## 状态

| 方法 | 路径 | 凭据 | 说明 |
|---|---|---|---|
| GET | `/api/v1/status` | — | 整体状态（手动状态 + 设备列表） |
| PUT | `/api/v1/status` | 管理 | 设置手动状态 |
| GET | `/api/v1/status/presets` | — | 状态预设列表 |

`GET /api/v1/status` 返回的是**聚合快照**，各插件贡献自己那部分：

```json
{
  "time": 1788690295.89,
  "status": 0,
  "last_updated": 1788690295.89,
  "devices": [
    {"id": "pc-1", "name": "我的电脑", "status": "VSCode",
     "using": true, "fields": {}, "last_updated": 1788690295.85}
  ],
  "private": false
}
```

禁用 `device` 插件时 `devices` 字段就不出现，`status` 仍然可用——两个插件互不依赖。

## 设备

| 方法 | 路径 | 凭据 | 说明 |
|---|---|---|---|
| GET | `/api/v1/devices` | — | 设备列表（隐私模式下返回空） |
| PUT | `/api/v1/devices/{id}` | 设备 / 管理 | 上报设备状态（不存在则创建） |
| DELETE | `/api/v1/devices/{id}` | 设备 / 管理 | 移除设备 |
| DELETE | `/api/v1/devices` | 管理 | 清空所有设备 |
| GET | `/api/v1/privacy` | — | 查询隐私模式 |
| PUT | `/api/v1/privacy` | 管理 | 开关隐私模式 |

```bash
curl -X PUT /api/v1/devices/pc-1 \
     -H "X-Sleepy-Token: <设备 token>" \
     -d '{"name": "我的电脑", "status": "VSCode", "using": true}'
```

字段都是可选的，没传的沿用已有值，方便客户端只上报变化的部分。`fields` 放自定义数据（电量、音乐等），会原样返回。

隐私模式开启后 `devices` 一律返回空，数据仍在库里，关掉即恢复。

## 设备 Token

| 方法 | 路径 | 凭据 | 说明 |
|---|---|---|---|
| GET | `/api/v1/tokens` | 管理 | 列出所有设备 token |
| POST | `/api/v1/tokens` | 管理 | 签发一个设备 token |
| DELETE | `/api/v1/tokens/{token}` | 管理 | 吊销 |

```bash
curl -X POST /api/v1/tokens -H "X-Sleepy-Token: <管理 token>" \
     -d '{"name": "我的电脑"}'
# -> {"token": "...", "name": "我的电脑", "expires_at": null, "hint": "..."}
```

## 实时推送

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/events` | SSE 事件流 |
| WS | `/api/v1/ws` | WebSocket |

两边推的是同一份内容。事件类型：

| 事件 | 触发时机 |
|---|---|
| `connected` | 刚连上，附带一份完整快照 |
| `status-changed` | 手动状态变更 |
| `device-changed` | 设备上报、移除、清空，或隐私模式切换 |
| `online-changed` | 在线连接数变化 |
| `refresh` | WebSocket 定期快照（兜底，防止漏事件） |

```javascript
const es = new EventSource('/api/v1/events');
es.addEventListener('device-changed', (e) => {
  const data = JSON.parse(e.data);   // data 一定是合法 JSON
});
```

## 统计与元信息

| 方法 | 路径 | 凭据 | 说明 |
|---|---|---|---|
| GET | `/api/v1/metrics` | — | 访问统计（日/周/月/年/总计） |
| GET | `/api/v1/meta` | — | 服务版本等元信息 |
| GET | `/api/v1/health` | — | 健康检查，返回 204 |
| GET | `/api/v1/plugins` | — | 已加载插件列表 |
| GET | `/api/v1/plugins/{id}` | — | 单个插件信息 |

取版本信息请用 `/api/v1/meta` 而不是 `/`——装了前端插件时 `/` 会被它接管去渲染页面。

## 错误格式

```json
{
  "code": 401,
  "message": "Unauthorized",
  "detail": "Invalid token"
}
```

每个响应都带两个头：

- `X-Sleepy-Version` — 服务版本
- `X-Sleepy-Request-Id` — 请求 ID，报问题时附上它能直接对到日志
