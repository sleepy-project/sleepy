# screen_usage_time

## 简介

屏幕使用时长统计插件，用于统计和展示设备的应用和网站使用时长数据，支持多设备管理和实时数据更新。

## 功能

1. 支持多个设备的使用时长统计
2. 统计各应用的使用时间
3. 统计各网站的浏览时间（仅Windows）
4. 通过SSE事件流实时更新数据
5. **设备排序**：按最新更新时间排序显示设备
6. **自适应布局**：网站数据为空时自动调整布局
7. **响应式设计**：适配不同屏幕尺寸

## 配置

以下是本插件的默认配置：

```yaml
plugin:
  screen_usage_time:
    top_apps: 5      # 每个设备最大显示的应用数量
    top_websites: 5  # 每个设备最大显示的网站数量
```

## 客户端配置

### Windows 客户端

Windows 系统需要配合 Tai 软件使用，用于获取应用和网站的使用时间。

应用使用情况统计黑白名单请在Tai软件中配置，`win_device.py` 仅用于负责上传应用使用情况数据。不提供使用情况黑白名单功能

#### 使用方法

1. 进入 `plugins/screen_usage_time/client` 目录
2. 编辑 `win_device.py` 文件，配置以下参数：

```python
# 服务地址
SERVER: str = 'http://localhost:9010'
# 密钥
SECRET: str = 'your-secret-here'
# 设备标识符
DEVICE_ID: str = 'test-device'
# 前台显示名称
DEVICE_SHOW_NAME: str = '我的电脑'
# 检查间隔（秒）
CHECK_INTERVAL: int = 5
# 是否启用媒体信息获取
MEDIA_INFO_ENABLED: bool = True
# 是否启用 Tai 使用时间统计
TAI_ENABLED: bool = True
# Tai 所在路径
TAI_PATH: str = r'D:\\Program Files\\Tai1.5.0.6'
```

#### 启动客户端

```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
venv\Scripts\activate

# 安装依赖
pip install pywin32 httpx psutil

# 启动客户端
python win_device.py
```

### 安卓客户端

前往这里下载安卓客户端：[ScreenTimeForSleepy](https://github.com/VanillaNahida/ScreenTimeForSleepy)

安装好后填写API地址，API 密钥，设备ID，设备名称，上传间隔。授予相关权限即可使用

需要授予如下权限：
 - 使用情况访问权限 （用于获取应用使用数据）
 - 自启动权限      （后台自启动权限）
 - 无障碍权限      （后台保活用）
 - 获取应用列表    （应用黑白名单需要使用）
 - 忽略电池优化    （用于防止系统杀后台）
 - 通知           （上传状态通知和前台保活）

## 数据结构

### 服务端接收的数据格式

```json
{
  "device-id": "device-computer",
  "device-name": "香草的电脑",
  "date": "2026-02-23",
  "update-time": "2026-02-23 20:24:25",
  "screen_usage_time": {
    "app_usage": {
      "Chrome": {
        "icon": "chrome.png",
        "total_time": 3600
      }
    },
    "website_usage": {
      "Bilibili": {
        "icon": "bilibili.ico",
        "total_time": 1800
      }
    }
  }
}
```

### 前端响应数据格式

```json
{
  "screen_usage_time": {
    "devices": {
      "device-computer": {
        "device-name": "香草的电脑",
        "app_usage": {
          "Chrome": {
            "icon": "Y2hyb21lLnBuZw==", // base64 编码后的图标文件名
            "total_time": 3600,
            "formatted_time": "1 小时 0 分 0 秒",
            "progress": 100
          }
        },
        "website_usage": {
          "Bilibili": {
            "icon": "YmlsaWJpbGkuaWNv",
            "total_time": 1800,
            "formatted_time": "30 分 0 秒",
            "progress": 50
          }
        },
        "last-update": "2026-02-23T20:24:25",
        "last-date": "2026-02-23"
      }
    },
    "last_updated": "2026-02-23T20:24:26",
    "current_date": "2026-02-23"
  }
}
```

## API 接口

### 1. 接收使用时间数据

- **URL**: `/plugin/screen_usage_time/usage`
- **Method**: POST
- **Headers**: `{ "Sleepy-Secret": "your-secret" }`
- **Body**: 见上文数据结构

### 2. 接收图标文件

- **URL**: `/plugin/screen_usage_time/icons`
- **Method**: POST
- **Headers**: 
  - `{ "Sleepy-Secret": "your-secret", "x-device-id": "device-id" }`
  - 或 `{ "Sleepy-Secret": "your-secret", "filename": "base64-encoded-filename" }`
- **Body**: 图片文件二进制数据

### 3. 提供图标文件

- **URL**: `/plugin/screen_usage_time/icons/<device-id>/<filename>`
- **Method**: GET
- **Response**: 图片文件