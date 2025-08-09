# 部署

1. **[手动部署](#手动部署)** *(建议有自己的服务器 / 本地部署使用)*
2. **[Huggingface 部署](#huggingface-部署)** *(无服务器推荐)*
3. [Vercel 部署](#vercel-部署) *(限制较多, 不推荐使用)*
4. [一键部署](#一键部署-未测试) *(未测试, 不推荐使用)*

## 快速跳转

- [部署](#部署)
  - [快速跳转](#快速跳转)
  - [手动部署](#手动部署)
    - [安装](#安装)
    - [启动](#启动)
  - [Huggingface 部署](#huggingface-部署)
  <<<<<<< HEAD
    - [我承认你的代码写的确实很nb，但对我来说还是太吃操作了 (已过时)](#我承认你的代码写的确实很nb但对我来说还是太吃操作了-已过时)
  =======
>>>>>>> main
    - [卡在 Deploying?](#卡在-deploying)
    - [如何使用自定义域名](#如何使用自定义域名)
  - [Vercel 部署](#vercel-部署)
  - [一键部署 (未测试)](#一键部署-未测试)
    - [Linux](#linux)
    - [Windows](#windows)

## 手动部署

本方式理论上全平台通用, 安装了 Python **3.10+** 即可

> 优点: 数据文件 (`data/data.json`) 可持久化，不会因为重启而被删除

### 安装

1. Clone 本仓库 *(也可先 Fork)*

```shell
git clone --depth=1 -b main https://github.com/sleepy-project/sleepy.git
```

2. 安装依赖

```shell
pip install -r pyproject.toml
```

> 推荐使用 `uv` 管理环境:

```shell
uv sync
```


3. 编辑配置文件

<<<<<<< HEAD
> *配置文件变化史* <br/> 
> ~~`data.json`~~ <br/>
> -> ~~`config.json`~~ <br/>
> -> ~~`config.jsonc`~~ <br/>
> -> ~~环境变量 & `.env`~~ <br/>
> -> ~~`config.yaml` & 环境变量 & `.env`~~ <br/>
> -> **环境变量 & `data/.env` & `data/config.yaml` & `data/config.toml` & `data/config.json`**

在 `data` 目录下新建上面几种配置文件中的**一种**，并**按照 [此处](./config.md) 的说明编辑配置**
=======
在项目目录创建 `.env` 文件:

```ini
sleepy_main_host = "0.0.0.0" # 监听地址
sleepy_main_port = "9010" # 端口号
sleepy_main_secret = "改成别人猜不出来的密钥" # 密钥，相当于密码
sleepy_page_name = "你的名字" # 将显示在网页中
sleepy_page_favicon = "./static/favicon.ico" # 网站图标, 可替换 static/favicon.ico 自定义 (也可以用其他格式的, 自己改路径)
sleepy_page_more_text = "欢迎来到我的状态页!" # 说两句? (也可以留空)
sleepy_page_using_first = true # 使用中设备优先显示
```

更多配置项详见 [此处](./env.md)
>>>>>>> main

### 启动

> [!WARNING]
> **使用宝塔面板 (uwsgi) 等部署时，请确定只为本程序分配了 1 个进程, 如设置多个服务进程可能导致数据不同步!!!**

有两种启动方式:

```shell
# 直接启动
python3 main.py
# 简易启动器
python3 start.py
```

默认服务 http 端口: **`9010`**

## Huggingface 部署

> 适合没有服务器部署的同学使用 <br/>
> *~~有服务器也推荐，不怕被打~~* <br/>
> ~~唯一的缺点: 不能使用自定义域名~~ <br/>
> **可用 Cloudflared Tunnel 方式使用自定义域名，见 [如何使用自定义域名](#如何使用自定义域名)**

只需三步:

1. 复制 Space `wyf9/sleepy` (**[点击直达](https://huggingface.co/spaces/wyf9/sleepy?duplicate=true&visibility=public)**)
<<<<<<< HEAD
2. 在复制页面设置 secret 和页面信息等环境变量 ***([配置文档](./config.md))***
=======

> 如果没有弹出窗口, 请手动点击右上角三点 -> `Duplicate this Space` (如图)

![huggingface-5](https://ghimg.siiway.top/sleepy/deploy/huggingface-5.1.png)

2. 在复制页面设置 secret 和页面信息等环境变量 *[**[配置示例](../.env.example)**]*
>>>>>>> main
3. 点击部署，等待完成后点击右上角三点 -> `Embed this space`，即可获得你的部署地址 *(类似于: <https://wyf9-sleepy.hf.space>)*

> [!IMPORTANT]
> **在创建时请务必选择 Space 类型为公开 (`Public`)，否则无法获取部署地址 (他人无法访问)!** <br/>
> *Hugging Face Space 如 48h 未访问将会休眠，建议使用定时请求平台 (如 `cron-job.org`, `Uptime Kuma` 等) 定时请求 `(你的部署地址)/none`*

<<<<<<< HEAD
### 我承认你的代码写的确实很nb，但对我来说还是太吃操作了 (已过时)

<details>

***<summary>点!此!展!开! (大图警告)</summary>***

有没有更简单无脑的方法推荐一下
**有的兄弟，有的！**
这样的方法有很多个，各个都是`GitHub` T<sub>0.5</sub>的操作
我怕教太多了你学不会，现在只要点
[这里](https://huggingface.co/spaces/sadg456/s?duplicate=true&visibility=public)
然后自己去注册一个账号
参考[配置文档](./config.md)在Setting==>Variables and secrets添加环境变量配置
然后在这里:
![链接](https://ghimg.siiway.top/sleepy/deploy/huggingface-1.1.png)
就可以复制你的`URL`，填入你选择的 **[`/client`](./client/README.md)** 对应的url配置中即可快速开始

</details>

### 卡在 Deploying?

> [!TIP]
> *对所有的 Hugging Face Space 都有效*
=======
### 卡在 Deploying?

> [!TIP]
> 适用于日志中程序已经启动, 但部署状态仍然为 `Deploying` 的情况 <br/>
> *对所有的 Hugging Face 仓库都有效*

<details>

<summary>解决方法</summary>
>>>>>>> main

1. 点击右上角三点 -> `Duplicate this Space`，**复制** Space 并**填写好和之前一样的环境变量**
2. 在 `Settings` 页面底部 `Delete this Space` 处**删除**旧 Space
3. 在 `Settings` -> `Rename or transfer this space` 将新 Space **重命名**为旧 Space 的名称

### 如何使用自定义域名

1. 到 [Zero Trust Dashboard](https://one.dash.cloudflare.com/?to=/:account/networks/tunnels/add/cfd_tunnel) 创建一个 Tunnel

随便填一个名字后进入 `安装并运行连接器`，复制 Token:

![huggingface-2](https://ghimg.siiway.top/sleepy/deploy/huggingface-2.1.png)

进入 `路由隧道`，按如下图片配置并保存:

![huggingface-3](https://ghimg.siiway.top/sleepy/deploy/huggingface-3.1.png)

2. 编辑 Space 的 `Dockerfile`，将底部的 `CMD python3 main.py` 删除，并添加:

```dockerfile
# Install wget
RUN apt install wget -y

# Download Cloudflared script
RUN wget -O cfd.sh https://gist.github.com/wyf9/71ff358636154ab00d90602c3c818763/raw/cfd.sh

# Start
CMD bash cfd.sh
```

3. 新建两个环境变量 (`Settings` -> `Variables and secrets`):

- `CFD_COMMAND` *(`Variable`)*: `python3 main.py`
- `CFD_TOKEN`: 你的 Cloudflare Tunnel 密钥

设置完成后如图:

![huggingface-4](https://ghimg.siiway.top/sleepy/deploy/huggingface-4.1.png)

4. 重新构建 Space (`Factory rebuild`) 即可

> 定时请求仍然需要使用 Huggingface 提供的子域 <br/>
> *详见: [Gist](https://gist.github.com/wyf9/71ff358636154ab00d90602c3c818763)*

## Vercel 部署

<<<<<<< HEAD
> 可以使用自定义域名，但限制较多 **(如无法使用 SSE)** <br/>
> *当前端检测到为 Vercel 部署时会自动回退到轮询方式更新*
=======
> 可以使用自定义域名，但**限制较多** (如无法使用 SSE, 请求数 / 请求完成时间有限制等) <br/>
> *当前端检测到为 Vercel 部署时会回退到轮询方式更新*
>>>>>>> main

1. Fork 本项目
2. 打开 [`vercel.com/new`](https://vercel.com/new)，并按照提示授权访问 GitHub *(如未注册则注册)*
3. 选择你的 Fork，点击 `Import`

![vercel-1](https://ghimg.siiway.top/sleepy/deploy/vercel-1.1.png)

1. 在导入界面设置环境变量 (其他配置保持默认)，点击 `Deploy` 部署 ***([配置文档](./config.md))***

![vercel-2](https://ghimg.siiway.top/sleepy/deploy/vercel-2.1.png)

即可完成部署，默认分配 `vercel.app` 域名

5. ***[可选]*** 绑定自定义域名: `Settings` -> `Domains`

![vercel-3](https://ghimg.siiway.top/sleepy/deploy/vercel-3.1.png)

6. ***[可选]*** 添加更多环境变量: `Settings` -> `Environment Variables`

![vercel-4](https://ghimg.siiway.top/sleepy/deploy/vercel-4.1.png)

> 修改环境变量后需重新部署

## 一键部署 (未测试)

> [!WARNING]
> 完全由 AI 生成, 未经任何测试, **不要使用此方式!!!**

### Linux

运行命令：

```bash
bash <(curl -s https://ghproxy.com/https://raw.githubusercontent.com/sleepy-project/sleepy/main/scripts/install.sh)
```

如果你的服务器不在中国大陆，可以去掉 `ghproxy.com/` 部分：

```bash
bash <(curl -s https://raw.githubusercontent.com/sleepy-project/sleepy/main/scripts/install.sh)
```

### Windows

运行命令：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
irm https://ghproxy.com/https://raw.githubusercontent.com/sleepy-project/sleepy/main/scripts/install.ps1 | iex
```

如果你的服务器不在中国大陆，可以去掉 `ghproxy.com/` 部分：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
irm https://raw.githubusercontent.com/sleepy-project/sleepy/main/scripts/install.ps1 | iex
```
