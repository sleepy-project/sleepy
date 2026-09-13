# Sleepy 文档

## 上手

- [部署](./deploy.md) — Docker、源码运行、反向代理
- [从 v5 迁移](./migration.md) — **现有客户端一行都不用改**
- [配置](./config.md) — 所有配置项

## 参考

- [API](./api.md) — 接口速查（完整文档见运行中的 `/docs`）
- [插件开发](./plugin.md) — 写一个插件

## 架构

core 是空壳，只提供机制：HTTP、配置、日志、存储、鉴权、事件总线、实时广播、插件加载。

业务功能全部是插件：

| 插件 | 作用 |
|---|---|
| `status` | 手动状态、状态预设、整体状态查询 |
| `device` | 设备上报、设备列表、隐私模式 |
| `device-auth` | 设备 Token 的签发、列出、吊销 |
| `metrics` | 访问统计 |
| `frontend` | 前端静态资源 |
| `compat-v5` | v5 旧版 API 兼容层 |

这些插件放在 `builtin/`，随仓库分发，`git clone` 下来就能跑，不需要联网下载任何东西。

你自己的插件放 `plugins/`，同名时覆盖 `builtin/` 里的实现。
