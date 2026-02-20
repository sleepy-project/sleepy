# GitHub Stats 插件

## 简介

此插件用于展示 GitHub 用户的统计信息，包括 GitHub Stats、Top Languages 和 Wakatime 数据。通过配置 API 参数，您可以自定义显示内容，并将其集成到您的面板中。

## 功能

- **GitHub Stats**: 显示用户的 GitHub 活跃统计信息，例如 PR 合并、讨论参与等。
- **Top Languages**: 展示用户最常使用的编程语言。
- **Wakatime Stats**: 集成 Wakatime 数据，展示用户的编程时间统计。

> *[Hackatime](https://hackatime.hackclub.com/) 同样适用 Wakatime Stats API (只需要额外配置 `api_domain` 为 `hackatime.hackclub.com` 即可)*

## 配置

以下是本插件的默认配置：

```yaml
plugin:
  github_stats:
    base_url: "https://gh-readme-stats.siiway.top/api"

    stats:
      enabled: true
      params:
        username: "wyf9"
        count_private: true
        show_icons: true
        theme: "solarized-dark"
        cache_seconds: 3600
        hide_border: true
        show:
          - "reviews"
          - "discussions_started"
          - "discussions_answered"
          - "prs_merged"
          - "prs_merged_percentage"

    top_langs:
      enabled: true
      params:
        username: "wyf9"
        count_private: true
        show_icons: true
        theme: "solarized-dark"
        cache_seconds: 3600
        hide_border: true

    wakatime:
      enabled: true
      params:
        username: "11095"
        api_domain: "hackatime.hackclub.com"
        custom_title: "Hackatime Stats (last year)"
        layout: "compact"
        cache_seconds: 3600
        langs_count: 8
        theme: "solarized-dark"
        hide_border: true
```

## 使用方法

1. 确保通过 `plugins_enabled` 配置启用此插件。
2. 根据需要修改配置，启用或禁用特定统计项 (以及配置你的用户名 / 显示设置等)。
3. 启动插件后，统计信息将自动显示在面板中。

## 示例

以下是默认配置生成的统计信息：

```html
<img src="https://gh-readme-stats.siiway.top/api?username=wyf9&count_private=true&show_icons=true&theme=solarized-dark&cache_seconds=3600&hide_border=true&show=reviews,discussions_started,discussions_answered,prs_merged,prs_merged_percentage" alt="GitHub Stats">
<img src="https://gh-readme-stats.siiway.top/api/top-langs?username=wyf9&count_private=true&show_icons=true&theme=solarized-dark&cache_seconds=3600&hide_border=true" alt="Top Langs">
<img src="https://gh-readme-stats.siiway.top/api/wakatime?username=11095&api_domain=hackatime.hackclub.com&custom_title=Hackatime Stats (last year)&layout=compact&cache_seconds=3600&langs_count=8&theme=solarized-dark&hide_border=true" alt="Wakatime Stats">
```

效果：

## 参考

- [GitHub Readme Stats](https://github.com/anuraghazra/github-readme-stats)
- [Wakatime](https://wakatime.com/)