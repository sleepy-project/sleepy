# 部署

## Docker（推荐）

```bash
git clone https://github.com/sleepy-project/sleepy.git
cd sleepy
docker compose up -d
```

默认监听 9010，数据落在 `./data`。

改配置用环境变量，写在 `docker-compose.yml` 里：

```yaml
environment:
  - SLEEPY_DATABASE=sqlite:///data/sleepy.db
  - SLEEPY_PORT=9010
  - SLEEPY_LOG_LEVEL=INFO
```

## 从源码

需要 Python 3.13+ 和 [uv](https://docs.astral.sh/uv/)。

```bash
git clone https://github.com/sleepy-project/sleepy.git
cd sleepy
uv sync
uv run main.py
```

常用参数：

```bash
uv run main.py --port 8080        # 覆盖端口
uv run main.py --host 127.0.0.1   # 覆盖监听地址
uv run main.py --fresh-start      # 清空数据库后启动
```

也可以直接把 ASGI 应用交给别的服务器：

```bash
uv run uvicorn core.app:app --host 0.0.0.0 --port 9010
```

## 首次设置

启动后设置管理密码：

```bash
curl -X POST http://127.0.0.1:9010/api/v1/init \
     -H 'Content-Type: application/json' \
     -d '{"password": "你的密码", "hashed": false}'
```

密码只能设一次，重设需要清空 `userdata` 表或用 `--fresh-start`。

接下来给设备签发 token，见 [migration.md](./migration.md)。

## 反向代理

Nginx：

```nginx
location / {
    proxy_pass http://127.0.0.1:9010;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;

    # SSE 和 WebSocket 需要这几行
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_buffering off;
    proxy_read_timeout 3600s;
}
```

`proxy_buffering off` 是必须的，否则 SSE 事件会被缓冲住，前端看起来就是「状态不更新」。

Caddy 不需要额外配置：

```
sleepy.example.com {
    reverse_proxy 127.0.0.1:9010
}
```

## 前端

Docker 镜像和 release 包里已经带了构建产物，直接可用。

从源码运行且需要前端时：

```bash
uv run main.py frontend build --install     # 需要 pnpm
```

构建产物不存在时后端照常工作，只是没有网页界面。

## 数据与备份

要备份的只有数据库文件：

```bash
cp data/sleepy.db backup/sleepy-$(date +%F).db
```

SQLite 开着 WAL，热备建议用：

```bash
sqlite3 data/sleepy.db ".backup backup/sleepy.db"
```

## 跑不了的环境

**Vercel 等 serverless 平台。** v7 用 SQLite 存数据、从本地目录加载插件，文件系统是只读且无状态的环境跑不起来。用 VPS 或任何能跑长驻进程的地方。
