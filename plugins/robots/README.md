# robots

配置供搜索引擎 / AI 爬虫使用的 `robots.txt` 文件和 `X-Robots-Tag` 响应头.

## 配置示例

- 允许爬取 `/` (index), 但不允许 `/panel/*`, `/api/*`:

```yaml
plugin:
  robots:
    robots_txt:
      - user_agent: '*'
        allow: '/'
        disallow: ['/panel/*', '/api/*']
    
    x_robots_rules:
      '/': 'all' # 其实 all 和没加效果一样
      '/panel/*': 'noindex, nofollow, nostore'
      '/api/*': 'noindex, nofollow, nostore'
```

- 禁止所有爬取:

```yaml
plugin:
  robots:
    robots_txt:
      - user_agent: '*'
        disallow: '/*'
    
    x_robots_rules:
      '*': 'noindex, nofollow, nostore'
```

- 你也可以直接写原始的 `robots.txt`:

```yaml
plugin:
  robots:
    robots_txt: |
      User-Agent: *
      Content-signal: search=yes,ai-train=no
      Allow: /

      User-agent: Amazonbot
      Disallow: /

      User-agent: Applebot-Extended
      Disallow: /

      User-agent: Bytespider
      Disallow: /

      User-agent: CCBot
      Disallow: /

      User-agent: ClaudeBot
      Disallow: /

      User-agent: Google-Extended
      Disallow: /

      User-agent: GPTBot
      Disallow: /

      User-agent: meta-externalagent
      Disallow: /
```
