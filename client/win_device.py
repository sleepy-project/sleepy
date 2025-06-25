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
from datetime import datetime
import httpx
import threading
import win32api  # type: ignore - 勿删，用于强忽略非 windows 系统上 vscode 找不到模块的警告
import win32con  # type: ignore
import win32gui  # type: ignore
from pywintypes import error as pywinerror  # type: ignore

# ----- Part: Config

# --- config start
# 服务地址, 末尾同样不带 /
SERVER: str = 'http://localhost:9010'
# 密钥
SECRET: str = 'wyf9test'
# 设备标识符，唯一 (它也会被包含在 api 返回中, 不要包含敏感数据)
DEVICE_ID: str = 'device-1'
# 前台显示名称
DEVICE_SHOW_NAME: str = 'MyDevice1'
# 检查间隔，以秒为单位
CHECK_INTERVAL: int = 5
# 是否忽略重复请求，即窗口未改变时不发送请求
BYPASS_SAME_REQUEST: bool = True
# 控制台输出所用编码，避免编码出错，可选 utf-8 或 gb18030
ENCODING: str = 'gb18030'
# 当窗口标题为其中任意一项时将不更新
SKIPPED_NAMES: list = [
    '',  # 空字符串
    '系统托盘溢出窗口。', '新通知', '任务切换', '快速设置', '通知中心', '操作中心', '日期和时间信息', '网络连接', '电池信息', '搜索', '任务视图', '任务切换', 'Program Manager',  # 桌面组件
    'Flow.Launcher', 'Snipper - Snipaste', 'Paster - Snipaste'  # 其他程序
]
# 当窗口标题为其中任意一项时视为未在使用
NOT_USING_NAMES: list = [
    '启动', '「开始」菜单',  # 开始菜单
    '我们喜欢这张图片，因此我们将它与你共享。', '就像你看到的图像一样？选择以下选项', '喜欢这张图片吗?'  # 锁屏界面
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
# --- config end

# ----- Part: Functions

# stdout = TextIOWrapper(stdout.buffer, encoding=ENCODING)  # https://stackoverflow.com/a/3218048/28091753
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
_print_ = print


def print(msg: str, **kwargs):
    '''
    修改后的 `print()` 函数，解决不刷新日志的问题
    原: `_print_()`
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
# ----- Part: Send status


Url = f'{SERVER}/device/set'
last_window = ''


async def send_status(using: bool = True, app_name: str = '', id: str = DEVICE_ID, show_name: str = DEVICE_SHOW_NAME, timeout: float = 7.5, **kwargs):
    '''
    httpx.AsyncClient.post 发送设备状态信息
    设置了 headers 和 proxies
    '''
    json_data = {
        'secret': SECRET,
        'id': id,
        'show_name': show_name,
        'using': using,
        'app_name': app_name
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
                app_name="要关机了喵",
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
        print(f'Sending update: using = {using}, app_name = "{window}" (idle = {mouse_idle})')
        try:
            resp = await send_status(
                using=using,
                app_name=window,
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
                        app_name=standalone_media_info,
                        id=MEDIA_DEVICE_ID,
                        show_name=MEDIA_DEVICE_SHOW_NAME
                    )
                else:
                    # 从播放变为不播放
                    media_resp = await send_status(
                        using=False,
                        app_name='没有媒体播放',
                        id=MEDIA_DEVICE_ID,
                        show_name=MEDIA_DEVICE_SHOW_NAME
                    )
                debug(f'Media Response: {media_resp.status_code}')

                # 更新上一次的媒体状态和内容
                last_media_playing = current_media_playing
                last_media_content = current_media_content
        except Exception as e:
            debug(f'Media Info Error: {e}')


async def main():
    '''
    主程序异步函数
    '''
    try:
        while True:
            await do_update()
            await asyncio.sleep(CHECK_INTERVAL)
    except (KeyboardInterrupt, SystemExit) as e:
        # 如果中断或被 taskkill 则发送未在使用
        debug(f'Interrupt: {e}')
        try:
            resp = await send_status(
                using=False,
                app_name='未在使用',
                id=DEVICE_ID,
                show_name=DEVICE_SHOW_NAME
            )
            debug(f'Response: {resp.status_code} - {resp.json()}')

            # 如果启用了独立媒体设备，也发送该设备的退出状态
            if MEDIA_INFO_ENABLED and MEDIA_INFO_MODE == 'standalone':
                media_resp = await send_status(
                    using=False,
                    app_name='未在使用',
                    id=MEDIA_DEVICE_ID,
                    show_name=MEDIA_DEVICE_SHOW_NAME
                )
                debug(f'Media Response: {media_resp.status_code}')

            if resp.status_code != 200:
                print(f'Error! Response: {resp.status_code} - {resp.json()}')
        except Exception as e:
            print(f'Exception: {e}')


if __name__ == '__main__':
    asyncio.run(main())
