# Sleepy v7

> 看看我是不是在线。

Sleepy 是一个可自行部署的个人状态服务：展示手动状态、设备是否正在使用以及当前活动应用，并向客户端提供实时更新和统计接口。

> [!WARNING]
> v7 目前处于早期开发阶段。接口和配置仍可能调整；生产部署前请备份数据库。v5 数据库不会自动迁移到 v7。

## 功能

- 响应式 Web 管理端：首次初始化、登录、状态、设备、隐私模式、令牌和统计
- 设备状态上报与公开状态页
- SSE / WebSocket 实时更新
- 可命名、可撤销的独立设备令牌
- `compat-v5` 内置插件，兼容常用 v5 API 和客户端
- 空壳 core + 插件架构；内置功能和第三方功能使用同一套插件机制
- SQLite 默认存储，支持 Docker、Compose 和源码部署

## 部署方式

### Docker Compose（推荐）

需要 Docker Engine 或 Docker Desktop，并确保 Compose 可用。

```bash
git clone https://github.com/sleepy-project/sleepy.git
cd sleepy
docker compose up -d --build
```

服务默认监听 `9010`，浏览器打开：

```text
http://服务器地址:9010/
```

查看状态和日志：

```bash
docker compose ps
docker compose logs -f sleepy
```

更新：

```bash
git pull
docker compose up -d --build
```

默认 Compose 将宿主机的 `./data` 挂载到容器，并把数据库保存为 `./data/sleepy.db`。停止或重建容器不会删除该目录：

```bash
docker compose down
```

不要使用 `docker compose down -v` 或手动删除 `data/`，除非确定不需要现有数据。

### 从源码运行

要求：

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- 构建 Web 管理端时还需要 Node.js 22+ 和 pnpm 10+

```bash
git clone https://github.com/sleepy-project/sleepy.git
cd sleepy
uv sync
uv run main.py frontend build --install
uv run main.py
```

常用启动参数：

```bash
uv run main.py --host 127.0.0.1 --port 9010
uv run main.py --fresh-start
```

> [!CAUTION]
> `--fresh-start` 会清空并重建数据库，只应用于开发或明确需要重置的实例。

若跳过前端构建，后端仍会以 API-only 模式启动；此时 `/api/v1/*`、`/docs` 和 `/redoc` 可用，但没有 Web 页面。

### 反向代理与 HTTPS

生产环境建议让 Sleepy 仅监听内网地址，再由 Caddy 或 Nginx 提供 HTTPS。Nginx 必须关闭 SSE 缓冲并支持 WebSocket：

```nginx
location / {
    proxy_pass http://127.0.0.1:9010;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_buffering off;
    proxy_read_timeout 3600s;
}
```

完整示例见 [部署文档](./docs/deploy.md)。Sleepy 不能直接完整部署到 Cloudflare Pages、Vercel 等无状态静态/Serverless 环境，因为服务端需要常驻 Python 进程、本地插件和持久数据库；可以只把另行配置过 API 地址的静态前端放到 Pages。

## 首次使用

1. 打开 `http://服务器地址:9010/`。
2. 在初始化页面设置管理密码。
3. 登录管理端。
4. 在“设备令牌”页面为每台设备签发独立令牌。
5. 将令牌填入客户端并开始上报。

也可以通过 API 初始化：

```bash
curl -X POST http://127.0.0.1:9010/api/v1/init \
  -H 'Content-Type: application/json' \
  -d '{"password":"请替换为强密码","hashed":false}'
```

管理密码、管理 token 和设备 token 用途不同：

| 凭据 | 用途 | 是否应交给设备客户端 |
|---|---|---|
| 管理密码 | 登录 Web 管理端 | 否 |
| 管理 access/refresh token | 管理状态、设备和令牌 | 否 |
| 设备 token | 上报单台设备状态 | 是 |

推荐桌面客户端：[Sleepy-GUI](https://github.com/sleepy-project/Sleepy-GUI)。其他脚本和平台客户端见 [sleepy-project/clients](https://github.com/sleepy-project/clients)。

## v5 客户端兼容

`compat-v5` 默认启用。现有 v5 客户端通常只需将其 `SECRET` 改为 v7 管理端签发的设备 token，原有 `/api/device/*`、`/api/status/*`、`/api/meta` 和 `/api/metrics` 路径由兼容插件处理。

所有客户端完成迁移后可以关闭兼容层：

```toml
[plugins]
disabled = ["compat-v5"]
```

详细差异和限制见 [v5 迁移指南](./docs/migration.md)。

## 配置

不创建配置文件也可以使用默认值。需要定制时，将 `config.toml.example` 复制为 `config.toml`：

```bash
cp config.toml.example config.toml
```

Windows PowerShell：

```powershell
Copy-Item config.toml.example config.toml
```

常用配置：

```toml
host = "0.0.0.0"
port = 9010
database = "sqlite:///data/sleepy.db"

[plugins]
disabled = []

[plugin.device-auth]
expires_days = 0
```

配置可来自环境变量、`config.yaml`、`config.toml` 或 `config.json`，后加载的文件覆盖前面的值；环境变量使用 `SLEEPY_` 前缀。完整字段见 [配置文档](./docs/config.md)。不要提交包含密钥或生产连接信息的本地配置。

## 数据与备份

默认数据库位于 `data/sleepy.db`。SQLite 使用中建议通过 SQLite 备份命令生成一致快照：

```bash
mkdir -p backup
sqlite3 data/sleepy.db ".backup backup/sleepy.db"
```

至少备份数据库；自定义 `config.toml` 和外部 `plugins/` 也应按需备份。升级前先创建备份，v5 数据库不要直接覆盖 v7 数据库。

## API 与插件

v7 API 位于 `/api/v1/`，运行后可访问：

- `/docs`：Swagger UI
- `/redoc`：ReDoc
- `/api/v1/health`：健康检查
- `/api/v1/meta`：版本与服务元信息

内置插件：

| 插件 | 作用 |
|---|---|
| `status` | 手动状态、状态预设、聚合状态 |
| `device` | 设备上报、列表和隐私模式 |
| `device-auth` | 设备 token 签发、列出和撤销 |
| `metrics` | 访问统计 |
| `frontend` | Web 管理端静态资源和 SPA fallback |
| `compat-v5` | v5 API 兼容层 |

目录结构：

```text
core/       HTTP、配置、存储、鉴权、事件和插件机制
builtin/    随项目发布的内置插件
frontend/   Vue 3 + TypeScript 管理端源码
plugins/    本地安装的第三方插件（不受 Git 跟踪）
tests/      后端与集成测试
docs/       项目文档
```

## 开发

后端：

```bash
uv sync --extra dev
uv run ruff check .
uv run pytest -q
```

前端：

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm check
pnpm test
pnpm build
```

前端开发服务器默认将 `/api` 代理到 `http://127.0.0.1:9010`：

```bash
pnpm dev
```

插件开发参见 [插件指南](./docs/plugin.md)。提交代码前也请阅读 [贡献指南](./CONTRIBUTING.md)。

## 文档

| 文档 | 内容 |
|---|---|
| [部署](./docs/deploy.md) | Docker、源码运行、反向代理与备份 |
| [配置](./docs/config.md) | core 与插件配置项 |
| [API 参考](./docs/api.md) | v7 接口速查 |
| [从 v5 迁移](./docs/migration.md) | 兼容范围、令牌和数据差异 |
| [插件开发](./docs/plugin.md) | 插件结构、路由、事件与 CLI |

## 许可证

Sleepy 采用 [GNU General Public License v3.0](./LICENSE) 或更高版本授权。

Copyright © 2026 sleepy-project.
