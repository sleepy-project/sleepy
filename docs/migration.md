# 从 v5 迁移到 v7

> 结论先说：**现有客户端脚本一行都不用改。**

## 你需要做的三件事

### 1. 部署 v7

```bash
git clone https://github.com/sleepy-project/sleepy.git
cd sleepy
uv sync
uv run main.py
```

### 2. 设置管理密码

```bash
curl -X POST http://127.0.0.1:9010/api/v1/init \
     -H 'Content-Type: application/json' \
     -d '{"password": "你的密码", "hashed": false}'
```

### 3. 签发一个设备 Token，替换客户端里的 `SECRET`

先登录拿管理 token：

```bash
curl -X POST http://127.0.0.1:9010/api/v1/auth/login \
     -H 'Content-Type: application/json' \
     -d '{"password": "你的密码", "hashed": false}'
```

用它签发设备 token：

```bash
curl -X POST http://127.0.0.1:9010/api/v1/tokens \
     -H "X-Sleepy-Token: <上一步返回的 token>" \
     -H 'Content-Type: application/json' \
     -d '{"name": "我的电脑"}'
```

把返回的 `token` 填进客户端脚本原有的 `SECRET` 变量：

```powershell
# client/Sleepy.Powershell.ps1
$SECRET = "刚刚签发的 token"     # 只改这一行
```

```bash
# client/linux_device_hyprland.sh
SECRET="刚刚签发的 token"         # 只改这一行
```

完成。脚本其余部分、请求格式、上报逻辑全都不用动。

## 为什么能这样

v7 的 `compat-v5` 插件保留了 v5 的接口路径，并且把请求里的 `secret` 字段直接当作设备 token 校验。字段名的差异（`show_name` → `name`、`app_name` → `status`）由兼容层负责翻译。

比起 v5 的全局共享 secret，设备 token 还多了几个好处：

- 可以给每台设备发一个，互不影响
- 可以随时单独吊销某一个
- 面板上能看到每个 token 的备注名和最后活跃时间

## 兼容的接口

| 路径 | 方法 | 说明 |
|---|---|---|
| `/api/device/set` | GET / POST | 设备上报，9 个客户端脚本用的就是它 |
| `/api/device/remove` | GET | 移除设备 |
| `/api/device/clear` | GET | 清空设备（需管理 token） |
| `/api/device/private` | GET | 隐私模式（需管理 token） |
| `/api/status/query` | GET | 查询整体状态 |
| `/api/status/set` | GET | 设置手动状态（需管理 token） |
| `/api/status/list` | GET | 状态预设列表 |
| `/api/meta` | GET | 服务元信息 |
| `/api/metrics` | GET | 访问统计 |

## 行为差异

有几处 v7 和 v5 不完全一样，多数情况下感知不到：

**设备上报的字段是增量的。** 只传 `status` 时，`name` 和 `using` 会沿用上次的值，不会被清空。v5 的行为也类似，但 v7 更明确。

**`using` 接受多种写法。** `true` / `True` / `1` / `yes` / `on` 都识别，shell 脚本传裸 `true` 没问题。

**权限分了两级。** 设备 token 只能写自己的设备；改全局状态、清空设备、切换隐私模式需要管理 token。v5 里所有操作共用一个 secret，任何持有它的脚本都能改全局状态。

**访问统计的计数不是实时落库的。** 默认每 30 秒批量写一次，读取 `/api/metrics` 时会先强制落库，所以看到的数字始终是准的。

## 不再提供的东西

**主题系统。** v5 的 `theme/{default,dark,blue,console}` 是服务端 Jinja 模板渲染的，v7 的前端是独立的单页应用，换外观的方式不同。

**Vercel 部署。** v7 用 SQLite 存数据、从本地目录加载插件，serverless 环境跑不了。用 Docker 或直接跑在 VPS 上。

## 数据迁移

v5 和 v7 的表结构不兼容，设备数据不会自动迁移。

不过设备数据本来就是各客户端每隔几十秒上报一次的，**启动 v7 后等一个上报周期，设备列表就自己回来了**，不需要手工搬运。

要保留的话，管理密码需要重新设置（`/api/v1/init`），统计数据需要手工导出导入。

## 停用兼容层

等所有客户端都迁移到 `/api/v1/*` 之后，可以关掉兼容层：

```toml
# config.toml
[plugins]
disabled = ["compat-v5"]
```

新接口的说明见 [api.md](./api.md)。
