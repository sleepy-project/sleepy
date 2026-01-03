# hitokoto

一言插件 (https://hitokoto.cn)

启用后, 将会在 More Info 底部 / 新卡片 增加一句随机的一言

效果:

- 追加到 more-info 卡片末尾 (`standalone: false`):

![not-standalone](https://cb.wss.moe/tosms2.png)

- 独立卡片 (`standalone: true`):

![standalone](https://cb.wss.moe/n0q8xk.png)

- 管理面板卡片:

![panel](https://cb.wss.moe/lgh6l3.png)

## 配置

```yaml
plugin:
  hitokoto:
    standalone: false
    # 控制是否显示单独卡片 (如为 false 则追加到 more-info 卡片底部, 仅适用于主页)
```