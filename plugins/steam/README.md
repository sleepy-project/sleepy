# steam

以卡片形式显示你的 Steam 信息 & 状态

效果:

![preview](https://cb.wss.moe/u62yw3.png)

![preview-2](https://cb.wss.moe/jh713o.png)

## 配置

```yaml
plugin:
  steam:
    # 你的 Steam 数字 ID, 可到 SteamDB 查询
    account_id: 76561199733292625
    # 你的 Steam 社区名称, 用于点击跳转主页 (可为 null)
    vanity_id: bbdqz
    # 你想展示信息的游戏的 AppID (可能需要调整隐私设置, 可为 null)
    app_id: 1144400
    # 语言 (可用: bulgarian,danish,english,french,greek,italian,koreana,polish,brazilian,russian,latam,swedish,tchinese,ukrainian,czech,dutch,finnish,german,hungarian,japanese,norwegian,portuguese,romanian,schinese,spanish,thai,turkish,vietnamese, 可为 null)
    lang: schinese
    # 你可能想要调整 iframe 的高度 (height, 单位 px) 来解决可能的过大 / 过小问题
    iframe_height: 300
    # iframe base url (可自部署: https://github.com/sleepy-project/steam-miniprofile, index.html -> Pages)
    base_url: "https://miniprofile.siiway.top"
```
