# coding: utf-8
'''
win_device.py
在 Windows 上获取窗口名称
by: @wyf9, @pwnint, @kmizmal, @gongfuture, @LeiSureLyYrsc
基础依赖: pywin32, httpx
媒体信息依赖:
 - Python≤3.9: winrt
 - Python≥3.10: winrt.windows.media.control, winrt.windows.foundation
 * (如果你嫌麻烦并且不在乎几十m的包占用, 也可以直接装winsdk :)
电池状态依赖: psutil
'''

# ----- Part: Import

import sys
import io
import asyncio
import time  # 改用 time 模块以获取更精确的时间
import base64
from datetime import datetime
import httpx
import threading
import win32api  # type: ignore - 勿删，用于强忽略非 windows 系统上 vscode 找不到模块的警告
import win32con  # type: ignore
import win32gui  # type: ignore
from pywintypes import error as pywinerror  # type: ignore
import sqlite3
import json
import os

# ----- Part: Config

# --- config start
# 服务地址, 末尾同样不带 /
SERVER: str = 'http://localhost:9010'
# 密钥
SECRET: str = 'your-secret-here'
# 设备标识符，唯一 (它也会被包含在 api 返回中, 不要包含敏感数据)
DEVICE_ID: str = 'test-device'
# 前台显示名称
DEVICE_SHOW_NAME: str = '我的电脑'
# 检查间隔，以秒为单位
CHECK_INTERVAL: int = 5
# 是否忽略重复请求，即窗口未改变时不发送请求
BYPASS_SAME_REQUEST: bool = True
# 控制台输出所用编码，避免编码出错，可选 utf-8 或 gb18030
ENCODING: str = 'gb18030'
# 当窗口标题为其中任意一项时将不更新
SKIPPED_NAMES: list = [
    '',  # 空字符串
    '系统托盘溢出窗口。', '新通知', '任务切换', '快速设置', '通知中心', '操作中心', '日期和时间信息', '网络连接', '电池信息', '搜索', '任务视图', '任务切换', 'Program Manager', '贴靠助手',  # 桌面组件
    'Flow.Launcher', 'Snipper - Snipaste', 'Paster - Snipaste'  # 其他程序
]
# 当窗口标题为其中任意一项时视为未在使用
NOT_USING_NAMES: list = [
    '启动', '「开始」菜单',  # 开始菜单
    '我们喜欢这张图片，因此我们将它与你共享。', '就像你看到的图像一样？选择以下选项', '喜欢这张图片吗?', 'Windows 默认锁屏界面'  # 锁屏界面
]
# 是否反转窗口标题，以此让应用名显示在最前 (以 ` - ` 分隔)
REVERSE_APP_NAME: bool = False
# 鼠标静止判定时间 (分钟)
MOUSE_IDLE_TIME: int = 15
# 鼠标移动检测的最小距离 (像素)
MOUSE_MOVE_THRESHOLD: int = 10
# 控制日志是否显示更多信息
DEBUG: bool = False
# 代理地址 (<http/socks>://host:port), 设置为空字符串禁用
PROXY: str = ''
# 是否启用媒体信息获取
MEDIA_INFO_ENABLED: bool = True
# 媒体信息显示模式: 'prefix' - 作为前缀添加到当前窗口名称, 'standalone' - 使用独立设备
MEDIA_INFO_MODE: str = 'standalone'
# 独立设备模式下的设备ID (仅当 MEDIA_INFO_MODE = 'standalone' 时有效)
MEDIA_DEVICE_ID: str = 'media-device'
# 独立设备模式下的显示名称 (仅当 MEDIA_INFO_MODE = 'standalone' 时有效)
MEDIA_DEVICE_SHOW_NAME: str = '正在播放'
# 是否启用电源状态获取
BATTERY_INFO_ENABLED: bool = True
# --- Tai 配置 --- #
# 是否启用 Tai 使用时间统计
TAI_ENABLED: bool = True
# Tai 所在路径
TAI_PATH: str = r'D:\\Program Files\\Tai1.5.0.6'
# Tai 检查间隔 (秒)
TAI_CHECK_INTERVAL: int = 5 * 60 # 5 分钟
# --- config end

# ----- Part: Functions

# stdout = TextIOWrapper(stdout.buffer, encoding=ENCODING)  # https://stackoverflow.com/a/3218048/28091753
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
_print_ = print


def print(msg: str, **kwargs):
    '''
    修改后的 `print()` 函数，解决不刷新日志的问题
    - 原: `_print_()`
    '''
    msg = str(msg).replace('\u200b', '')
    try:
        _print_(f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {msg}', flush=True, **kwargs)
    except Exception as e:
        _print_(f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] Log Error: {e}', flush=True)


def debug(msg: str, **kwargs):
    '''
    显示调试消息
    '''
    if DEBUG:
        print(msg, **kwargs)


def reverse_app_name(name: str) -> str:
    '''
    反转应用名称 (将末尾的应用名提前)
    如 Before: win_device.py - dev - Visual Studio Code
    After: Visual Studio Code - dev - win_device.py
    '''
    lst = name.split(' - ')
    new = []
    for i in lst:
        new = [i] + new
    return ' - '.join(new)


# 导入拎出来优化性能 (?)
if MEDIA_INFO_ENABLED:
    try:
        import winrt.windows.media.control as media  # type: ignore
    except ImportError:
        import winrt.windows.media.control as media  # type: ignore


async def get_media_info():
    '''
    使用 pywinrt 获取 Windows SMTC 媒体信息 (正在播放的音乐等)
    Returns:
        tuple: (是否正在播放, 标题, 艺术家, 专辑)
    '''
    # 首先尝试使用 pywinrt
    try:
        # 获取媒体会话管理器
        manager = await media.GlobalSystemMediaTransportControlsSessionManager.request_async()  # type: ignore
        session = manager.get_current_session()

        if not session:
            return False, '', '', ''

        # 获取播放状态
        info = session.get_playback_info()
        is_playing = info.playback_status == media.GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING  # type: ignore

        # 获取媒体属性
        props = await session.try_get_media_properties_async()

        title = props.title or '' if props else ''  # type: ignore
        artist = props.artist or '' if props else ''  # type: ignore
        album = props.album_title or '' if props else ''  # type: ignore

        if '未知唱片集' in album or '<' in album and '>' in album:
            album = ''

        debug(f'[get_media_info] return: {is_playing}, {title}, {artist}, {album}')
        return is_playing, title, artist, album

    except Exception as primary_error:
        debug(f"主要媒体信息获取方式失败: {primary_error}")
        return False, '', '', ''

# 电池状态拎出来导入状态
if BATTERY_INFO_ENABLED:
    try:
        import psutil  # type: ignore
        battery = psutil.sensors_battery()
        if battery is None:
            print("无法获取电池信息")
            BATTERY_INFO_ENABLED = False
    except Exception as e:
        print(f"获取电池信息失败: {e}")
        BATTERY_INFO_ENABLED = False


def get_battery_info():
    """
    获取电池信息
    Returns:
        tuple: (电池百分比, 充电状态)
    """
    try:
        # 电池信息变量
        battery = psutil.sensors_battery()  # type: ignore
        if battery is None:
            return 0, "未知"

        percent = battery.percent
        power_plugged = battery.power_plugged
        # 获取充电状态
        status = "⚡" if power_plugged else ""
        debug(f'--- 电量: `{percent}%`, 状态: {status}')
        return percent, status
    except Exception as e:
        debug(f"获取电池信息失败: {e}")
        return 0, "未知"

# ----- Part: Tai Database

def read_sqlite_database(db_path):
    """
    读取SQLite数据库并提取所有表的数据
    """
    if not os.path.exists(db_path):
        print(f"错误：数据库文件不存在 - {db_path}")
        return None
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row  # 这样我们可以通过列名访问数据
        cursor = conn.cursor()
        
        # 获取所有用户表（排除系统表）
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        all_tables = [row[0] for row in cursor.fetchall()]
        
        if not all_tables:
            print("错误：在数据库中未找到任何用户表")
            return None
        
        debug(f"找到的表：{all_tables}")
        
        # 获取表结构信息
        data = {}
        
        for table_name in all_tables:
            # 获取表结构
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = [row[1] for row in cursor.fetchall()]
            debug(f"表 {table_name} 的列：{columns}")
            
            # 获取所有数据
            cursor.execute(f"SELECT * FROM {table_name}")
            rows = cursor.fetchall()
            
            # 转换为字典列表
            table_data = []
            for row in rows:
                row_dict = {}
                for idx, column in enumerate(columns):
                    value = row[idx]
                    # 处理特殊数据类型（如datetime）
                    if isinstance(value, bytes):
                        try:
                            value = value.decode('utf-8')
                        except:
                            value = str(value)
                    row_dict[column] = value
                table_data.append(row_dict)
            
            data[table_name] = table_data
            debug(f"表 {table_name} 有 {len(table_data)} 条记录")
        
        conn.close()
        return data
        
    except sqlite3.Error as e:
        print(f"数据库错误：{e}")
        return None

async def process_tai_data():
    """
    处理Tai数据并发送到服务器
    """
    if not TAI_ENABLED:
        return
    
    try:
        # 初始化Tai路径
        tai_path = TAI_PATH
        if not os.path.exists(tai_path):
            print(f"错误：Tai路径不存在 - {tai_path}")
            return
        
        # 构建路径
        db_path = os.path.join(tai_path, 'Data', 'data.db')
        app_icons_path = os.path.join(tai_path, 'AppIcons')
        web_favicons_path = os.path.join(tai_path, 'WebFavicons')
        
        # 检查路径
        if not os.path.exists(db_path):
            print(f"错误：Tai数据库不存在 - {db_path}")
            return
        
        # 读取数据库
        print(f"开始读取Tai数据库：{db_path}")
        db_data = read_sqlite_database(db_path)
        if not db_data:
            print("读取Tai数据库失败")
            return
        
        # 发送使用时长数据
        # 直接发送完整的数据库数据，包括所有表
        print(f"发送Tai使用时长数据：包含 {len(db_data.keys())} 个表的数据")
        await send_tai_usage_data(db_data)
        
        # 上传图标
        if os.path.exists(app_icons_path):
            print(f"上传Tai应用图标：{app_icons_path}")
            await upload_tai_icons(app_icons_path, 'png')
        
        if os.path.exists(web_favicons_path):
            print(f"上传Tai网站图标：{web_favicons_path}")
            await upload_tai_icons(web_favicons_path, 'ico')
        
    except Exception as e:
        print(f"处理Tai数据失败：{e}")

async def send_tai_usage_data(db_data):
    """
    发送Tai使用时长数据到服务器
    """
    try:
        url = f'{SERVER}/plugin/screen_usage_time/usage'
        
        # 直接发送完整的数据库数据，包括所有表
        data = db_data
        
        # 发送请求
        headers = {
            'Content-Type': 'application/json',
            'Sleepy-Secret': SECRET
        }
        
        if PROXY:
            async with httpx.AsyncClient(proxy=PROXY, timeout=30.0) as client:
                resp = await client.post(url, json=data, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, json=data, headers=headers)
        
        debug(f'Tai使用时长数据发送响应：{resp.status_code} - {resp.text}')
        if resp.status_code == 200:
            print("Tai使用时长数据发送成功")
        else:
            print(f"Tai使用时长数据发送失败：{resp.status_code} - {resp.text}")
            
    except Exception as e:
        print(f"发送Tai使用时长数据失败：{e}")

async def upload_tai_icons(icons_path, file_type):
    """
    上传Tai图标到服务器（单个文件上传，带base64编码的文件名）
    """
    try:
        url = f'{SERVER}/plugin/screen_usage_time/icons'
        
        # 获取所有图标文件
        icon_files = []
        for root, dirs, files in os.walk(icons_path):
            for file in files:
                if file.endswith(f'.{file_type}'):
                    icon_files.append(os.path.join(root, file))
        
        print(f"找到 {len(icon_files)} 个{file_type}图标文件")
        
        # 上传每个图标
        success_count = 0
        for icon_file in icon_files:
            try:
                with open(icon_file, 'rb') as f:
                    icon_data = f.read()
                
                # 获取文件名
                filename = os.path.basename(icon_file)
                
                # 对文件名进行 base64 编码，避免中文文件名问题
                encoded_filename = base64.b64encode(filename.encode('utf-8')).decode('utf-8')
                
                # 发送请求
                headers = {
                    'Content-Type': f'image/{file_type}',
                    'Sleepy-Secret': SECRET,
                    'filename': encoded_filename
                }
                
                if PROXY:
                    async with httpx.AsyncClient(proxy=PROXY, timeout=30.0) as client:
                        resp = await client.post(url, content=icon_data, headers=headers)
                else:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        resp = await client.post(url, content=icon_data, headers=headers)
                
                debug(f'图标上传响应：{resp.status_code} - {resp.text}')
                if resp.status_code == 200:
                    success_count += 1
                    debug(f"图标上传成功：{filename}")
                else:
                    debug(f"图标上传失败：{filename} - {resp.status_code} - {resp.text}")
                    
            except Exception as e:
                print(f"上传图标失败：{icon_file} - {e}")
        
        print(f"Tai图标上传完成：成功 {success_count} 个，失败 {len(icon_files) - success_count} 个")
        
    except Exception as e:
        print(f"上传Tai图标失败：{e}")
# ----- Part: Send status


Url = f'{SERVER}/api/device/set'
last_window = ''


async def send_status(using: bool = True, status: str = '', id: str = DEVICE_ID, show_name: str = DEVICE_SHOW_NAME, timeout: float = 7.5, **kwargs):
    '''
    httpx.AsyncClient.post 发送设备状态信息
    设置了 headers 和 proxies
    '''
    json_data = {
        'secret': SECRET,
        'id': id,
        'show_name': show_name,
        'using': using,
        'status': status
    }

    if PROXY:
        async with httpx.AsyncClient(proxy=PROXY, timeout=timeout) as client:  # type: ignore
            return await client.post(
                url=Url,
                json=json_data,
                headers={
                    'Content-Type': 'application/json'
                },
                timeout=timeout,
                **kwargs
            )
    else:
        async with httpx.AsyncClient(timeout=timeout) as client:
            return await client.post(
                url=Url,
                json=json_data,
                headers={
                    'Content-Type': 'application/json'
                },
                timeout=timeout,
                **kwargs
            )

# ----- Part: Shutdown handler


def on_shutdown(hwnd, msg, wparam, lparam):
    '''
    关机监听回调
    '''
    if msg == win32con.WM_QUERYENDSESSION:
        print("Received logout event, sending not using...")
        try:
            # 在新的事件循环中运行异步函数
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            resp = loop.run_until_complete(send_status(
                using=False,
                status="要关机了喵",
                id=DEVICE_ID,
                show_name=DEVICE_SHOW_NAME
            ))
            loop.close()
            debug(f'Response: {resp.status_code} - {resp.json()}')
            if resp.status_code != 200:
                print(f'Error! Response: {resp.status_code} - {resp.json()}')
        except Exception as e:
            print(f'Exception: {e}')
        return True  # 允许关机或注销
    return 0  # 其他消息


# 注册窗口类
wc = win32gui.WNDCLASS()
wc.lpfnWndProc = on_shutdown  # type: ignore - 设置回调函数
wc.lpszClassName = "ShutdownListener"  # type: ignore
wc.hInstance = win32api.GetModuleHandle(None)  # type: ignore

# 创建窗口类并注册
class_atom = win32gui.RegisterClass(wc)

# 创建窗口
hwnd = win32gui.CreateWindow(
    class_atom,  # className
    "Sleepy Shutdown Listener",  # windowTitle
    0,  # style
    0,  # x
    0,  # y
    0,  # width
    0,  # height
    0,  # parent
    0,  # menu
    wc.hInstance,  # hinstance
    None  # reserved
)


def message_loop():
    '''
    (需异步执行) 用于在后台启动消息循环
    '''
    win32gui.PumpMessages()


# 创建并启动线程
message_thread = threading.Thread(target=message_loop, daemon=True)
message_thread.start()

# ----- Part: Mouse idle

# 鼠标状态相关变量
last_mouse_pos = win32api.GetCursorPos()
last_mouse_move_time = time.time()
is_mouse_idle = False
cached_window_title = ''  # 缓存窗口标题, 用于恢复


def check_mouse_idle() -> bool:
    '''
    检查鼠标是否静止
    返回 True 表示鼠标静止超时
    '''
    global last_mouse_pos, last_mouse_move_time, is_mouse_idle

    try:
        current_pos = win32api.GetCursorPos()
    except pywinerror as e:
        print(f'Check mouse pos error: {e}')
        return is_mouse_idle
    current_time = time.time()

    # 计算鼠标移动距离的平方（避免开平方运算）
    dx = abs(current_pos[0] - last_mouse_pos[0])
    dy = abs(current_pos[1] - last_mouse_pos[1])
    distance_squared = dx * dx + dy * dy

    # 阈值的平方，用于比较
    threshold_squared = MOUSE_MOVE_THRESHOLD * MOUSE_MOVE_THRESHOLD

    # 打印详细的鼠标状态信息（为了保持日志一致性，仍然显示计算后的距离）
    distance = distance_squared ** 0.5 if DEBUG else 0  # 仅在需要打印日志时计算
    debug(f'Mouse: current={current_pos}, last={last_mouse_pos}, distance={distance:.1f}px')

    # 如果移动距离超过阈值（使用平方值比较）
    if distance_squared > threshold_squared:
        last_mouse_pos = current_pos
        last_mouse_move_time = current_time
        if is_mouse_idle:
            is_mouse_idle = False
            actual_distance = distance_squared ** 0.5  # 仅在状态变化时计算实际距离用于日志
            print(
                f'Mouse wake up: moved {actual_distance:.1f}px > {MOUSE_MOVE_THRESHOLD}px')
        else:
            debug(f'Mouse moving: {distance:.1f}px > {MOUSE_MOVE_THRESHOLD}px')
        return False

    # 检查是否超过静止时间
    idle_time = current_time - last_mouse_move_time
    debug(f'Idle time: {idle_time:.1f}s / {MOUSE_IDLE_TIME*60:.1f}s')

    if idle_time > MOUSE_IDLE_TIME * 60:
        if not is_mouse_idle:
            is_mouse_idle = True
            print(f'Mouse entered idle state after {idle_time/60:.1f} minutes')
        return True

    return is_mouse_idle  # 保持当前状态

# ----- Part: Main interval check


last_media_playing = False  # 跟踪上一次的媒体播放状态
last_media_content = ''  # 跟踪上一次的媒体内容


async def do_update():
    # 全局变量
    global last_window, cached_window_title, is_mouse_idle, last_media_playing, last_media_content

    # --- 窗口名称 / 媒体信息 (prefix) 部分

    # 获取当前窗口标题和鼠标状态
    current_window = win32gui.GetWindowText(win32gui.GetForegroundWindow())
    # 如果启用了反转应用名称功能，则反转窗口标题
    if REVERSE_APP_NAME and ' - ' in current_window:
        current_window = reverse_app_name(current_window)
    mouse_idle = check_mouse_idle()
    debug(f'--- Window: `{current_window}`, mouse_idle: {mouse_idle}')

    # 始终保持同步的状态变量
    window = current_window
    using = True

    # 获取电池信息
    if BATTERY_INFO_ENABLED:
        battery_percent, battery_status = get_battery_info()
        if battery_percent > 0:
            window = f"[🔋{battery_percent}%{battery_status}] {window}"

    # 获取媒体信息
    prefix_media_info = None
    standalone_media_info = None

    if MEDIA_INFO_ENABLED:
        is_playing, title, artist, album = await get_media_info()
        if is_playing and (title or artist):
            # 为 prefix 模式创建格式化后的媒体信息 [♪歌曲名]
            if title:
                prefix_media_info = f"[♪{title}]"
            else:
                prefix_media_info = "[♪]"

            # 为 standalone 模式创建格式化后的媒体信息 ♪歌曲名-歌手-专辑
            parts = []
            if title:
                parts.append(f"♪{title}")
            if (artist and artist != title):
                parts.append(artist)
            if (album and album != title and album != artist):
                parts.append(album)

            standalone_media_info = " - ".join(parts) if parts else "♪播放中"

            print(f"独立媒体信息: {standalone_media_info}")

    # 处理媒体信息 (prefix 模式)
    if MEDIA_INFO_ENABLED and prefix_media_info and MEDIA_INFO_MODE == 'prefix':
        # 作为前缀添加到窗口名称
        window = f"{prefix_media_info} {window}"

    # 鼠标空闲状态处理（优先级最高）
    if mouse_idle:
        # 缓存非空闲时的窗口标题
        if not is_mouse_idle:
            cached_window_title = current_window
            print('Caching window title before idle')
        # 设置空闲状态
        using = False
        window = ''
        is_mouse_idle = True
    else:
        # 从空闲恢复
        if is_mouse_idle:
            window = cached_window_title
            using = True
            is_mouse_idle = False
            print('Restoring window title from idle')

    # 是否需要发送更新
    should_update = (
        mouse_idle != is_mouse_idle or  # 鼠标状态改变
        window != last_window or  # 窗口改变
        not BYPASS_SAME_REQUEST  # 强制更新模式
    )

    if should_update:
        # 窗口名称检查 (未使用列表)
        if current_window in NOT_USING_NAMES:
            using = False
            debug(f'* not using: `{current_window}`')

        # 窗口名称检查 (跳过列表)
        if current_window in SKIPPED_NAMES:
            if mouse_idle == is_mouse_idle:
                # 鼠标状态未改变 -> 直接跳过
                debug(f'* in skip list: `{current_window}`, skipped')
                return
            else:
                # 鼠标状态改变 -> 将窗口名称设为上次 (非未在使用) 的名称
                debug(f'* in skip list: `{current_window}`, set app name to last window: `{last_window}`')
                window = last_window

        # 发送状态更新
        print(
            f'Sending update: using = {using}, status = "{window}", idle = {mouse_idle}')
        try:
            resp = await send_status(
                using=using,
                status=window,
                id=DEVICE_ID,
                show_name=DEVICE_SHOW_NAME
            )
            debug(f'Response: {resp.status_code} - {resp.json()}')
            if resp.status_code != 200 and not DEBUG:
                print(f'Error! Response: {resp.status_code} - {resp.json()}')
            last_window = window
        except Exception as e:
            print(f'Error: {e}')
    else:
        debug('No state change, skipping window name update')

    # --- 媒体信息 (standalone) 部分

    # 如果使用独立设备模式展示媒体信息
    if MEDIA_INFO_ENABLED and MEDIA_INFO_MODE == 'standalone':
        try:
            # 确定当前媒体状态
            current_media_playing = bool(standalone_media_info)
            current_media_content = standalone_media_info if standalone_media_info else ''

            # 检测播放状态或歌曲内容是否变化
            media_changed = (current_media_playing != last_media_playing) or (current_media_playing and current_media_content != last_media_content)

            if media_changed:
                print(f'Media changed: status: {last_media_playing} -> {current_media_playing}, content: {last_media_content != current_media_content} - `{standalone_media_info}`')

                if current_media_playing:
                    # 从不播放变为播放或歌曲内容变化
                    media_resp = await send_status(
                        using=True,
                        status=standalone_media_info,
                        id=MEDIA_DEVICE_ID,
                        show_name=MEDIA_DEVICE_SHOW_NAME
                    )
                else:
                    # 从播放变为不播放
                    media_resp = await send_status(
                        using=False,
                        status='没有媒体播放',
                        id=MEDIA_DEVICE_ID,
                        show_name=MEDIA_DEVICE_SHOW_NAME
                    )
                debug(f'Media Response: {media_resp.status_code}')

                # 更新上一次的媒体状态和内容
                last_media_playing = current_media_playing
                last_media_content = current_media_content
        except Exception as e:
            debug(f'Media Info Error: {e}')


def tai_data_thread():
    '''
    在单独线程中处理Tai数据的函数
    '''
    if not TAI_ENABLED:
        return
    
    # 在新线程中创建事件循环
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    last_tai_check = time.time()
    
    try:
        while True:
            current_time = time.time()
            if current_time - last_tai_check >= TAI_CHECK_INTERVAL:
                # 执行Tai数据处理
                loop.run_until_complete(process_tai_data())
                last_tai_check = current_time
            
            # 等待一段时间后再次检查
            time.sleep(1)  # 每1秒检查一次
    except Exception as e:
        print(f'Tai数据线程错误: {e}')
    finally:
        loop.close()

async def main():
    '''
    主程序异步函数
    '''
    try:
        # 创建并启动Tai数据处理线程
        if TAI_ENABLED:
            tai_thread = threading.Thread(target=tai_data_thread, daemon=True)
            tai_thread.start()
            print(f'Tai数据处理线程已启动，检查间隔: {TAI_CHECK_INTERVAL}秒')
        
        # 主循环：处理状态更新
        while True:
            await do_update()
            await asyncio.sleep(CHECK_INTERVAL)
    except (KeyboardInterrupt, SystemExit, asyncio.CancelledError) as e:
        # 如果中断或被 taskkill 则发送未在使用
        debug(f'Interrupted / Cancelled: {e}')
        try:
            resp = await send_status(
                using=False,
                status='未在使用',
                id=DEVICE_ID,
                show_name=DEVICE_SHOW_NAME
            )
            debug(f'Response: {resp.status_code} - {resp.json()}')

            # 如果启用了独立媒体设备，也发送该设备的退出状态
            if MEDIA_INFO_ENABLED and MEDIA_INFO_MODE == 'standalone':
                media_resp = await send_status(
                    using=False,
                    status='未在使用',
                    id=MEDIA_DEVICE_ID,
                    show_name=MEDIA_DEVICE_SHOW_NAME
                )
                debug(f'Media Response: {media_resp.status_code}')

            if resp.status_code != 200:
                print(f'Error! Response: {resp.status_code} - {resp.json()}')
        except Exception as e:
            print(f'Error sending not using: {e}')
        finally:
            print(f'Bye.')


if __name__ == '__main__':
    asyncio.run(main())
