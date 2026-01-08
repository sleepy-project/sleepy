# font

使用 Google Fonts 或你自定义的字体 URL 替换页面默认字体.

效果:

<details>

<summary>点击展开预览图</summary>

- 插件配置的默认字体

```yaml
# 即:
plugin:
  font:
    google_fonts: true
    family: ['Inter', 'sans-serif']
```

![](https://cb.wss.moe/xmcwze.png)

- 自定义字体

```yaml
plugin:
  font:
    google_fonts: false
    faces:
      - family: xiaolai1
        src: https://cdn.jsdmirror.com/gh/FrecklyComb1728/blog@main/public/fonts/XiaolaiMonoSC-Regular.woff2
        format: woff2
      - family: xiaolai2
        src: https://cdn.jsdmirror.com/gh/FrecklyComb1728/blog@main/public/fonts/XiaolaiMonoSC-Regular.woff
        format: woff
    family: [xiaolai1, xiaolai2]
```

![](https://cb.wss.moe/h7rhkf.png)

</details>

## 配置

```yaml
plugin:
  font:
    # 是否加载 Google Fonts
    google_fonts: true
    # 自定义的字体 faces
    faces:
      - family: aaa # family 名称
        src: https://host.name/path/to/abc.woff2 # 字体文件 url
        format: woff2 # 字体格式
      - family: bbb
        src: https://another.host/path/to/def.woff
        format: woff
    # 应用的字体 family 列表, 也可为字符串
    family: ['aaa', 'bbb', 'sans-serif']
    # 是否注入到所有 html 返回中
    all_html: false
```

> [!WARNING]
> `all_html` 选项会将字体配置注入到所有 Header `Content-Type` 包含 `html` 的响应体中, 可能会出现意外行为, 故默认禁用.

> 上面的字体配置将会转换成如下 CSS 片段 *(不包含加载 Google Fonts)*:

```css
@font-face {
  font-family: 'aaa';
  src: url('https://host.name/path/to/abc.woff2') format('woff2');
}
@font-face {
  font-family: 'bbb';
  src: url('https://another.host/path/to/def.woff') format('woff');
}
body {
  font-family: 'aaa', 'bbb';
}
```
