# 配置项说明

有两种方式修改配置:

1. 环境变量 ***(优先级最高)***
2. 与 `server.py` 同级的 `.env` 文件

> [!IMPORTANT]
> *(特别是)* Windows 用户请确保 `.env` 文件**使用 `UTF-8` 编码保存**，否则会导致**错误读入注释 / 中文乱码** <br/>
> Huggingface / Vercel 等容器平台部署需将环境变量放在 **`Environment Variables`**，而**不是** `.env` 文件 *(见 [部署文档](./deploy.md))* <br/>
> *请确保变量名为全大写或全小写* <br/>
> *修改配置后需重启服务生效*

> **配置类型**: <br/>
> - `str`: 字符串，在 `.env` 中**建议使用双引号括起**，如: `sleepy_page_desc = "someone's status page"`
> - `int`: 整数 *(小数部分会被舍弃)*
> - `bool`: 布尔值，可选 `true` **(是)** / `false` **(否)**, *(也可简写为 `1` / `0` 等，详见 [此处](../_utils.py))*

## (main) 系统基本配置

| 变量名                           | 类型 | 默认值          | 说明                                                         |
| -------------------------------- | ---- | --------------- | ------------------------------------------------------------ |
| `sleepy_main_host`               | str  | `0.0.0.0`       | 服务的监听地址，如需同时监听 IPv6 地址需改为 `::`            |
| `sleepy_main_port`               | int  | 9010            | 服务的监听端口 *(0-65535)*                                   |
| `sleepy_main_debug`              | bool | false           | 控制是否开启 Flask 的调试模式 (一般无需开启) *(开启后可自动重载代码)* |
| `sleepy_main_timezone`           | str  | `Asia/Shanghai` | 控制 **API 返回中 / 网页上**显示时间的时区，一般无需更改 *(`Asia/Shanghai` 或 `Asia/Chongqing` 均为北京时间)* |
| `sleepy_main_checkdata_interval` | int  | 30              | 控制多久检查一次状态数据的更新 **(秒)** (*检测到更新后会写入 `data.json`，供下次启动时恢复状态*) |
| `sleepy_main_secret`             | str  | ` `             | 密钥 (相当于密码，用于防止未授权设置状态)，**客户端须使用相同的密钥** |
| `sleepy_main_https_enabled`      | bool | false           | 是否启用 HTTPS，启用后需配置 `sleepy_main_ssl_cert` 和 `sleepy_main_ssl_key` |
| `sleepy_main_ssl_cert`           | str  | `cert.pem`      | SSL 证书路径 (相对于项目根目录或绝对路径)，详见 [HTTPS 配置指南](./https.md) |
| `sleepy_main_ssl_key`            | str  | `key.pem`       | SSL 密钥路径 (相对于项目根目录或绝对路径)，详见 [HTTPS 配置指南](./https.md) |

---

## (page) 页面内容配置

| 变量名                    | 类型 | 默认值                                     | 说明                                                         |
| ------------------------- | ---- | ------------------------------------------ | ------------------------------------------------------------ |
| `sleepy_page_name`        | str  | `User`                                     | 网页顶部 `(用户名)'s Status` 中用户名                        |
| `sleepy_page_title`       | str  | `(用户名) Alive?`                          | 标题栏中显示的网页标题                                       |
| `sleepy_page_desc`        | str  | `(用户名)'s Online Status Page`            | 网页描述 *(主要用于 SEO)*                                    |
| `sleepy_page_favicon`     | str  | `./static/favicon.ico`                     | 网页的图标 (`.png` 或 `.ico` 图片) 路径，可以为绝对路径或相对路径 |
| `sleepy_page_background`  | str  | `https://imgapi.siiway.top/image`          | 背景图片地址，可以使用网上的图片 API 或单张图片 *(默认为 [siiway/imgapi](https://github.com/siiway/imgapi))* |
| `sleepy_page_learn_more`  | str  | `GitHub Repo`                              | 网页底部链接的**显示文字**                                   |
| `sleepy_page_repo`        | str  | `https://github.com/sleepy-project/sleepy` | 网页底部链接的**目标** *(默认为本 repo 地址)*                |
| `sleepy_page_more_text`   | str  | ` `                                        | 网页底部链接上方插入的文字 (**支持 HTML**，可以插入 统计代码 / 备案号 等) |
| `sleepy_page_sorted`      | bool | false                                      | 是否按字母顺序排序设备列表                                   |
| `sleepy_page_using_first` | bool | false                                      | 是否设置使用中设备优先显示                                   |
| `sleepy_page_hitokoto`    | bool | true                                       | 在插入文字上方显示随机 [一言](https://hitokoto.cn)           |
| `sleepy_page_canvas`      | bool | true                                       | 是否启用粒子效果 *(如影响性能可关闭)*                        |
| `sleepy_page_moonlight`   | bool | true                                       | 在卡片左上角 / 右上角显示**切换暗色模式**和**卡片透明度**的按钮 |
| `sleepy_page_lantern`     | bool | false                                      | 在网页顶部显示节日灯笼 *(默认文字为 `欢度新春`)*             |
| `sleepy_page_mplayer`     | bool | false                                      | 在网页左下角显示**音乐播放器**                               |
| `sleepy_page_zhixue`      | bool | false                                      | 显示智学网分数 (详见 **[对应客户端设置](../client/README.md#zhixuewang)**) |

## (status) 页面状态显示配置

这部分配置控制状态信息在页面上的具体展示方式。

| 环境变量                         | 类型 | 默认值     | 说明与提示                                                                   |
| -------------------------------- | ---- | ---------- | ---------------------------------------------------------------------------- |
| `sleepy_status_device_slice`     | int  | 30         | 网页中设备状态文本的最大长度，超过此长度会被截断 *(设置为 `0` 禁用)*         |
| `sleepy_status_show_loading`     | bool | true       | 控制是否在更新状态时显示 `更新中...` 提示 *(仅在使用原始轮询方式更新时生效)* |
| `sleepy_status_refresh_interval` | int  | 5000       | 两次更新状态之间的间隔 (**毫秒**，*仅在使用原始轮询方式更新时生效*)          |
| `sleepy_status_not_using`        | str  | `未在使用` | 设备未在使用时显示的状态文本 *(如为空则使用设备上报值)*                      |

## (util) 可选功能

| 环境变量                             | 类型 | 默认值 | 说明与提示                                                                               |
| ------------------------------------ | ---- | ------ | ---------------------------------------------------------------------------------------- |
| `sleepy_util_metrics`                | bool | true   | 控制是否启用内置的访问计数功能，并启用 `/metrics` 接口                                   |
| `sleepy_util_auto_switch_status`     | bool | true   | 是否启用自动切换状态 *(当状态为 `0` (活着) 且所有设备都未在使用时自动切换为 `1` (似了))* |
| `sleepy_util_steam_enabled`          | bool | false  | 是否启用新版 Steam 状态 *(iframe 卡片显示，需配置 `sleepy_util_steam_ids`)*              |
| `sleepy_util_steam_ids`              | str  | ` `    | 你的 Steam 账号 ID *(应为一串数字)*                                                      |
| `sleepy_util_steam_refresh_interval` | int  | 20000  | 刷新 Steam 状态的频率 (**毫秒**，*建议至少设置为 10000ms，过低可能触发速率限制*)         |
