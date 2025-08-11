# API

0. [鉴权说明](#一些说明)
1. [特殊接口](#special)
2. [Status 接口](#status)
3. [Device 接口](#device)

## 一些说明

### 关于错误

所有 API 返回的错误都会通过 `utils.APIUnsuccessful` 格式化:

```jsonc
{
  "success": false, // 表示请求未成功
  "code": 500, // 数字 HTTP Code (如 404, 500, ...), 同时也是响应的 HTTP 状态
  "details": "Internal Server Error", // HTTP Code 描述 (如 Not Found, Internal Server Error, ...)
  "message": "..." // 附带的错误详情
}
```

<!--
{
  "success": false,
  "code": 0,
  "details": "",
  "message": ""
}
-->

### 关于鉴权

> 在接口列表中, 标记为斜体的即为需要鉴权

任何标记了需要鉴权的接口，都需要用下面三种方式的一种传入 **与服务端一致** 的 `secret` *(优先级从上到下)*:

1. 请求体 *(`Body`)* 的 `secret` *(仅适用于 POST 请求)*

```jsonc
{
  "secret": "MySecretCannotGuess",
  // ...
}
```

2. 请求参数 *(`Param`)* 的 `secret`

```url
?secret=MySecretCannotGuess
```

3. 请求头 *(`Header`)* 的 `Sleepy-Secret`

```http
Sleepy-Secret: MySecretCannotGuess
```

4. 请求头 *(`Header`)* 的 `Authorization` *(需要在 secret 前加 `Bearer `)*

```http
Authorization: Bearer MySecretCannotGuess
```

5. Cookie *(`Cookie`)* 的 `sleepy-secret`

```
sleepy-secret=MySecretCannotGuess
```

> 服务端的 `secret` 即为在环境变量中配置的 `SLEEPY_SECRET`

如 `secret` 错误，则会返回:

```jsonc
// 401 Unauthorized
{
  "success": false,
  "code": 401,
  "details": "Unauthorized",
  "message": "Wrong Secret"
}
```

## Special

[Back to # api](#api)

|                  | 路径        | 方法  | 作用           |
| ---------------- | ----------- | ----- | -------------- |
| [Jump](#apimeta) | `/api/meta` | `GET` | 获取站点元数据 |

### /api/meta

> `/api/meta`

获取站点的元数据 (页面设置, 版本等)

#### Response

```jsonc
// 200 OK
{
  "success": true,
  "version": [5, 0, 0], // 版本号
  "version_str": "5.0-dev-20250629", // 也是版本号
  "timezone": "Asia/Shanghai", // 服务器时区 (用于 metrics)
  "page": { // 页面设置
    "background": "https://imgapi.siiway.top/image", // 背景
    "desc": "Development Site of Sleepy Project", // 描述
    "favicon": "/static/favicon.ico", // 图标
    "name": "Fake_wyf9", // 名字
    "theme": "default", // 默认主题
    "title": "SleepyDev" // 页面标题
  },
  "status": { // 状态设置
    "device_slice": 40, // 设备状态截取文字数
    "not_using": "关掉了~", // 未在使用提示覆盖
    "refresh_interval": 5000, // 刷新间隔 (ms)
    "sorted": true, // 是否启用排序
    "using_first": true // 是否优先显示使用中设备
  },
  "metrics": true // 是否已启用 metrics
}
```

## Status

[Back to # api](#api)

|                         | 路径                              | 方法  | 作用             |
| ----------------------- | --------------------------------- | ----- | ---------------- |
| [Jump](#apistatusquery) | `/api/status/query`               | `GET` | 获取状态         |
| [Jump](#apistatusset)   | `/api/status/set?status=<status>` | `GET` | 设置状态         |
| [Jump](#apistatuslist)  | `/api/status/list`                | `GET` | 获取可用状态列表 |
| [Jump](#apimetrics)     | `/api/metrics`                    | `GET` | 获取统计信息     |

### /api/status/query

[Back to ## status](#status)

> `/api/status/query`

获取当前的状态

* Method: GET
* 无需鉴权

#### Params

- `meta`: 是否同时请求元数据 *(bool)*
- `metrics`: 是否同时请求统计数据 *(bool)*

#### Response

```jsonc
// 200 OK
{
  "success": true, // 请求是否成功
  "time": 1751697213.46574, // 服务端时间 (UTC 时间戳)
  "status": {
    "id": 0, // 状态数字 id
    "name": "活着", // 状态名称
    "desc": "目前在线，可以通过任何可用的联系方式联系本人。", // 状态描述
    "color": "awake" // 状态颜色, 对应 static/style.css 中的 .sleeping .awake 等类
  },
  "device": { // 设备状态列表
    "test1": { // 设备 id
      "show_name": "Test 1", // 设备显示名称
      "status": null, // 状态文本 (之前的 app_name, 可为 null)
      "using": true, // 是否正在使用 (可为 null)
      "fields": { // 其他状态字段
        "online": "true"
      },
      "last_updated": 1751668348.684424 // 本设备最后更新时间
    },
    "test2": {
      "show_name": "Test 2",
      "status": "关掉了~",
      "using": false,
      "fields": {},
      "last_updated": 1751668359.072248
    }
  },
  "meta": { // 元数据 (仅在指定 ?meta=true 时包含)
    "metrics": true,
    "page": {
      "background": "https://imgapi.siiway.top/image",
      "desc": "Development Site of Sleepy Project",
      "favicon": "/static/favicon.ico",
      "name": "Fake_wyf9",
      "theme": "default",
      "title": "SleepyDev"
    },
    "status": {
      "device_slice": 40,
      "not_using": "关掉了~",
      "refresh_interval": 5000,
      "sorted": true,
      "using_first": true
    },
    "timezone": "Asia/Shanghai",
    "version": "5.0-dev-20250629"
  },
  "metrics": { // 统计数据 (仅在指定 ?metrics=true 时包含)
    "enabled": true,
    "time": 1751782809.226177,
    "time_local": "2025-07-06 14:20:09",
    "timezone": "Asia/Shanghai",
    "daily": {},
    "weekly": {},
    "monthly": {},
    "yearly": {},
    "total": {}
  },
  "last_updated": 1751668399.061304 // 所有数据最后更新时间
}
```

### /api/status/set

[Back to ## status](#status)

> `/api/status/set?status=<status>`

设置当前状态

* Method: GET
* **需要鉴权**

#### Params

- `<status>`: 状态码 *(`int`)*

#### Response

```jsonc
// 200 OK | 成功
{
  "success": true, // 请求是否成功
  "set_to": 0 // 设置到的状态码
}

// 400 Bad Request | 失败 - 请求无效
{
  "success": false,
  "code": 400,
  "details": "Bad Request",
  "message": "argument 'status' must be int"
}
```

### /api/status/list

[Back to ## status](#status)

> `/api/status/list`

获取可用状态的列表

* Method: GET
* 无需鉴权

#### Response

```jsonc
// 200 OK
{
  "success": true,
  "status_list": [
    {
      "id": 0, // 索引 (从 0 开始)
      "name": "活着", // 状态名称
      "desc": "目前在线，可以通过任何可用的联系方式联系本人。", // 状态描述
      "color": "awake" // 状态颜色, 对应 static/style.css 中的 .sleeping .awake 等类
    }, 
    {
      "id": 1, 
      "name": "似了", 
      "desc": "睡似了或其他原因不在线，紧急情况请使用电话联系。", 
      "color": "sleeping"
    }, 
    // 以此类推
  ]
}
```

### /api/metrics

[Back to ## status](#status)

> `/api/metrics`

获取统计信息

* Method: GET
* 无需鉴权

#### Response

```jsonc
// 200 OK (功能已启用)
{
  "success": true,
  "time": 1751790785.572329, // 服务端时间
  "enabled": true, // 是否启用 metrics 功能
  "time_local": "2025-07-06 16:33:05", // 服务端时间字符串 (基于设置的时区)
  "timezone": "Asia/Shanghai", // 时区
  "daily": { // 今天的数据
    "/device/set": 18,
    "/": 2,
    "/style.css": 1,
    "/query": 2
  },
  "weekly": { // 本周的数据
    "/device/set": 18,
    "/": 2,
    "/style.css": 1,
    "/query": 2
  },
  "month": { // 本月的数据
    "/device/set": 18,
    "/": 2,
    "/style.css": 1,
    "/query": 2
  },
  "year": { // 今年的数据
    "/device/set": 18,
    "/": 2,
    "/style.css": 1,
    "/query": 2
  },
  "total": { // 总统计数据，不清除
    "/device/set": 18,
    "/": 2,
    "/style.css": 1,
    "/query": 2
  }
}
```

```jsonc
// 200 OK (功能已禁用)
{
  "success": true,
  "enabled": false // 是否启用 metrics 功能
}
```

## Device

[Back to # api](#api)

|                           | 路径                                                                          | 方法   | 作用                          |
| ------------------------- | ----------------------------------------------------------------------------- | ------ | ----------------------------- |
| [Jump](#apideviceset)     | `/api/device/set`                                                             | `POST` | 设置单个设备的状态 (打开应用) |
|                           | `/api/device/set?id=<id>&show_name=<show_name>&using=<using>&status=<status>` | `GET`  | -                             |
| [Jump](#apideviceremove)  | `/api/device/remove?name=<device_name>`                                       | `GET`  | 移除单个设备的状态            |
| [Jump](#apideviceclear)   | `/api/device/clear`                                                           | `GET`  | 清除所有设备的状态            |
| [Jump](#apideviceprivate) | `/api/device/private?private=<isprivate>`                                     | `GET`  | 设置隐私模式                  |

### /api/device/set

[Back to ## device](#device)

> `/api/device/set`

设置单个设备的状态

* Method: GET / POST
* **需要鉴权**

#### Params (GET)

> [!WARNING]
> 使用 url params 传递参数在某些情况下 *(如内容包含特殊符号)* 可能导致非预期行为, 此处更建议使用 POST

> `/api/device/set?id=<id>&show_name=<show_name>&using=<using>&status=<status>`

- `<id>`: 设备标识符
- `<show_name>`: 显示名称
- `<using>`: 是否正在使用
- `<status>`: 设备状态文本 *(之前为正在使用的应用名称, 即 `app_name`)*

#### Body (POST)

> `/api/device/set`

```jsonc
{
  "id": "device-1", // 设备标识符
  "show_name": "MyDevice1", // 显示名称
  "using": true, // 是否正在使用
  "status": "VSCode" // 正在使用应用的名称
}
```

#### Response

```jsonc
// 200 OK | 成功
{
  "success": true
}

// 400 Bad Request | 失败 - 缺少参数 / 参数类型错误
{
  "success": false,
  "code": 400,
  "details": "Bad Request",
  "message": "missing param or wrong param type: ..."
}

// 405 Method Not Allowed | 失败 - 请求方式错误
{
  "success": false,
  "code": 405,
  "details": "Method Not Allowed",
  "message": "/api/device/set only supports GET and POST method!"
}
```

### /api/device/remove

[Back to ## device](#device)

> `/api/device/remove?id=<device_id>`

移除单个设备的状态

* Method: GET
* **需要鉴权**

#### Params

- `<device_id>`: 设备标识符

#### Response

```jsonc
// 200 OK | 成功
{
  "success": true
}

// 400 Bad Request | 失败 - 未提供设备 ID
{
  "success": false,
  "code": 400,
  "details": "Bad Request",
  "message": "Missing device id!"
}
```

### /api/device/clear

[Back to ## device](#device)

> `/api/device/clear`

清除所有设备的状态

* Method: GET
* **需要鉴权**

#### Response

```jsonc
// 200 OK | 成功
{
  "success": true
}
```

### /api/device/private

[Back to ## device](#device)

> `/api/device/private?private=<isprivate>`

设置隐私模式 *(即在 [`/api/status/query`](#apistatusquery) 的返回中设置 `device` 项为空 (`{}`))*

* Method: GET
* **需要鉴权**

#### Params

- `<isprivate>`: bool, 开关状态

#### Response

```jsonc
// 200 OK | 成功
{
  "success": true
}

// 400 Bad Request | 失败 - 请求无效
{
  "success": false,
  "code": 400,
  "details": "Bad Request",
  "message": "'private' arg must be boolean"
}
```
