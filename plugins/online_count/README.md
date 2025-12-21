# online_count

显示在线人数 (通过 SSE 连接数计算)

所以实际上任何使用了 `/api/status/events` 的 Event-Stream 流的客户端都算

断开后可能稍有延迟 (须 heartbeat 检测)

## 配置

```yaml
plugin:
  online_count:
    # 控制客户端多久刷新一次在线人数 (毫秒)
    refresh: 5000
```
