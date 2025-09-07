# sleepy

> 欢迎来到 Sleepy Project 的主仓库!

一个用于 ~~*视奸*~~ 查看个人在线状态 (以及正在使用软件) 的 Flask 应用，让他人能知道你不在而不是故意吊他/她

[**功能**](#功能) / [**演示**](#preview) / [**部署**](#部署--更新) / [**服务端配置**](#服务器配置) / [**使用**](#使用) / [**Client**](#client) / [**API**](#api) / [**关于**](#关于)

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/sleepy-project/sleepy)

## 功能

- [x] 自行设置在线状态 *(活着 / 似了 等, 也可 **[自定义](./setting/README.md#status_listjson)** 状态列表)*
- [x] 实时更新设备使用状态 *(包括 是否正在使用 / 打开的应用名, 通过 **[client](./client/README.md)** 主动推送)*
- [x] 美观的展示页面 [见 [Preview](#preview)]
- [x] 开放的 Query / Metrics [接口](./doc/api.md), 方便统计
- [x] 支持 HTTPS (需要自行配置 SSL 证书)

> [!TIP]
> 如有 Bug / 建议, 可发 issue (**[Bug][link-issue-bug]** / **[Feature][link-issue-feature]**) 或选择下面的联系方式 *(注明来意)*.

### Working...

我们正在使用 FastAPI 重构此项目, 请关注以下社交平台消息:

- [Discord][link-dc]
- [QQ][link-qq]
- [Telegram][link-tg]

预计将在 1-2 个月内完成 *(希望吧)*

如仍需使用此分支, 请仔细阅读本仓库的文档, 或找上面的 DeepWiki Ask.

> [!TIP]
> 以及 V4 API (即不带 `/api` 前缀的 API) 兼容**默认启用**, **文档: [`plugins/v4_compatible/README.md`](./plugins/v4_compatible/README.md)**

### Preview

演示站: [sleepy.wyf9.top](https://sleepy.wyf9.top)

**开放预览站**: [sleepy-preview.wyf9.top](https://sleepy-preview.wyf9.top)

<details>

<summary>展开更多</summary>

**HuggingFace** 部署预览: [wyf9-sleepy.hf.space](https://wyf9-sleepy.hf.space)

**Vercel** 部署预览: [sleepy-vercel.wyf9.top](https://sleepy-vercel.wyf9.top)

**开发服务器**: [请在 Discord 服务器查看][link-dc]

</details>

## 部署 / 更新

请移步 **[部署教程](./doc/deploy.md)** 或 **[更新教程](./doc/update.md)** *(多图警告)*

## 客户端

搭建完服务端后，你可在 **[`/client`](./client/README.md)** 找到客户端 (用于**手动更新状态**/**自动更新设备打开应用**)

*目前已有 [Windows](./client/README.md#windevice), [Linux](./client/README.md#linux), [IOS / MacOS](./client/README.md#iosmacos), [Android](./client/README.md#autoxjsscript), [油猴脚本](./client/README.md#browserscript) 等客户端*

> [!IMPORTANT]
> 每个客户端的标题可以 **点击跳转最新文件**, 不要使用固定 commit 的链接, 否则无法获取最新文件

## API

详细的 API 文档见 [doc/api.md](./doc/api.md).

<!-- ## 插件系统

(普通用户看这个) **[doc/plugin.md](./doc/plugin.md)**

(插件开发看这个) **[doc/plugin-dev/README.md](./doc/plugin-dev/README.md)** -->

## Star History

[![Star History Chart (如无法加载图片可点击查看)](https://api.star-history.com/svg?repos=sleepy-project/sleepy&type=Date)](https://star-history.com/#sleepy-project/sleepy&Date)

## 贡献者

> [!WARNING]
> 在提交代码前, 请先查阅 **[贡献准则](https://github.com/sleepy-project/.github/blob/main/CODE_OF_CONDUCT.md)** 和 **[贡献指南](./CONTRIBUTING.md)**

*因为权限问题, 我把贡献者名单 actions 扬了, 请 **[在此](https://github.com/sleepy-project/sleepy/graphs/contributors)** 查看*

## 关于

非常感谢 **ZMTO** *(原名 VTEXS)* 的 **「开源项目免费 VPS 计划」** 对项目提供的算力支持！

> **[Link](https://console.zmto.com/?affid=1566)** *(使用此链接获得 10% 优惠)* <!-- 谁都不许改 affid -->

---

本项目灵感由 Bilibili UP [@WinMEMZ](https://space.bilibili.com/417031122) 而来: **[site](https://maao.cc/sleepy/)** / **[blog](https://www.maodream.com/archives/192/)** / **[repo: `maoawa/sleepy`](https://github.com/maoawa/sleepy)**, 并~~部分借鉴~~使用了前端代码, 在此十分感谢。

[`templates/steam-iframe.html`](./templates/steam-iframe.html) 来自 repo **[gamer2810/steam-miniprofile](https://github.com/gamer2810/steam-miniprofile).**

---

对智能家居 / Home Assistant 感兴趣的朋友，一定要看看 WinMEMZ 的 [sleepy 重生版](https://maao.cc/project-sleepy/): **[maoawa/project-sleepy](https://github.com/maoawa/project-sleepy)!**

感谢 [@1812z](https://github.com/1812z) 的 B 站视频推广~ **([BV1LjB9YjEi3](https://www.bilibili.com/video/BV1LjB9YjEi3))**

---

[link-dc]: https://sleepy.siiway.top/t/dc
[link-tg]: https://sleepy.siiway.top/t/tgc
[link-qq]: https://sleepy.siiway.top/t/qq
[link-issue-bug]: https://sleepy.siiway.top/t/bug
[link-issue-feature]: https://sleepy.siiway.top/t/feature
