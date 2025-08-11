# 配置项说明

有多种方式修改配置 _(优先级从上到下)_:

1. 环境变量 & `data/.env`
2. `data/config.yaml` **(建议使用)**
3. `data/config.toml` **(建议使用)**
4. `data/config.json`

> [!IMPORTANT]
> _(特别是 Windows 用户)_ 请确保所有配置文件 **使用 `UTF-8` 编码保存**，否则会导致 **错误读入注释 / 中文乱码** 等异常情况 <br/>
> Huggingface / Vercel 等容器平台部署需将环境变量放在 **`Environment Variables`** 中 _(见 [部署文档](./deploy.md))_ <br/>
> _修改配置后需重启服务生效_

## 多种配置文件的格式转换

> 以 `main.host` _(str)_, `main.port` _(int)_, `main.debug` _(bool)_, `metrics.allow_list` _(list)_ 为例

### 环境变量

```bat
:: Windows
set SLEEPY_MAIN_HOST=0.0.0.0
set SLEEPY_MAIN_PORT=9010
set SLEEPY_MAIN_DEBUG=false
```

```bash
# non-Windows
export sleepy_main_host=0.0.0.0
export sleepy_main_port=9010
export sleepy_main_debug=false
```

### `data/.env`

```ini
sleepy_main_host = "0.0.0.0"
sleepy_main_port = 9010
sleepy_main_debug = false
```

### `data/config.yaml`

```yaml
# 可以这样配置
main:
  host: '0.0.0.0'
  port: 9010
  debug: false
metrics:
  allow_list:
    - /
    - /api/status/query
    - /api/metrics

# 也可以这样配置
main.host: '0.0.0.0'
main.port: 9010
main.debug: false
metrics.allow_list: ["/", "/api/status/query", "/api/metrics"]
```

### `data/config.toml`

```toml
[main]
host = "0.0.0.0"
port = 9010
debug = false

[metrics]
allow_list = ["/", "/api/status/query", "/api/metrics"]
```

### `data/config.json`

```json
{
    "main": {
        "host": "0.0.0.0",
        "port": 9010,
        "debug": false
    },
    "metrics": {
        "allow_list": [
            "/",
            "/query",
            "/api/metrics"
        ]
    }
}
```

---

## 可用配置项

> - `str`: 字符串
> - `int`: 整数
> - `PositiveInt`: 正整数 *(必须大于 0)*
> - `bool`: 布尔值，可选 `true` _(是)_ / `false` _(否)_
> - `list`: 列表
> - `dict`: 字典

完整的配置项定义列表可以到 [`models.py`](../models.py) 中查看

### (小白向) 如何阅读配置项定义

首先, 配置项定义的范围是 [`models.py`](../models.py) 中的 `用户配置开始` 到 `用户配置结束` 之间

即:

```py

# ========== 用户配置开始 ==========

# ...
# 配置项定义
# ...

# ========== 用户配置结束 ==========

```

其中:

- `class ...(...):` 可以理解为配置的类别, 你无需理会
- `name: type = ...` 就是配置项的定义了

一个配置项的定义看起来像这样:

```py
host: str = '0.0.0.0'
'''
`main.host`
监听地址
- ipv4: `0.0.0.0` 表示监听所有接口
- ipv6: `::` 表示监听所有接口
'''
```

其中:

- `host` 为配置项在代码中的局部名称
- `str` 为配置项的**类型** _(此处为字符串)_
- `"0.0.0.0"` 为配置项的**默认值** _(你没有自行配置就会使用这个值)_
- 由一对 `'''` 包围的部分为配置项的**注释**
    * 注释第一行 `main.host` 即为它在**配置文件中的名称** (见 [如何转换格式](#多种配置文件的格式转换))
    * 注释的其他内容就是配置项的**说明** *(用途 / 举例 / 注意事项)*
