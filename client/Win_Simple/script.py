# coding: utf-8
import os
import sys
import configparser
import requests
import logging
import threading
import ctypes
import win32gui,win32con,win32api # type: ignore
from time import time, sleep
import pystray
from PIL import Image

#cd client/Win_Simple
#pyinstaller -F -n Win_Simple.exe --icon=zmal.ico --hidden-import=win32gui --hidden-import=win32con --hidden-import=win32api --hidden-import=requests --hidden-import=pystray --hidden-import=PIL.Image --hidden-import=PIL.ImageDraw script.py

# --------------------------
# 配置管理类
# --------------------------
class AppConfig:
    """应用程序配置管理"""
    _DEFAULT_CONFIG = """\
[settings]
# 服务地址, 末尾不带 /
SERVER = http://localhost:7860
# 密钥，不要引号！
SECRET = 
DEVICE_ID = Win_Simple
# 前台显示名称
DEVICE_SHOW_NAME = MyComputer
# 检查间隔，以秒为单位
CHECK_INTERVAL = 2
# 控制台输出所用编码(utf-8选一个gb18030)
ENCODING = utf-8
# 当窗口标题为其中任意一项时将不更新（|分隔）
SKIPPED_NAMES = | 系统托盘溢出窗口。| 新通知| 任务切换| 快速设置| 通知中心| 搜索| Flow.Launcher| 任务视图| 任务栏| 「开始」菜单| Win_Simple.exe| 示例窗口1| 示例窗口2
# 当窗口标题为其中任意一项时视为未在使用
NOT_USING_NAMES = 我们喜欢这张图片，因此我们将它与你共享。| 示例窗口1| 示例窗口2
# 是否反转窗口标题
REVERSE_APP_NAME = False
# 鼠标静止判定时间(分钟)
MOUSE_IDLE_TIME = 15
# 鼠标移动检测的最小距离（像素）
MOUSE_MOVE_THRESHOLD = 3
#日志等级(DEBUG,INFO,WARNING,ERROR)DEBUG->ERROR日志依次减少
LOGLEVEL = INFO
#日志是否写入文件
LOG_FILE = False
# 黑名单配置（竖线分隔）
BLACKLIST = ExampleApp|Privacy Information
"""
    
    def __init__(self):
        self.config_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "config.ini")
        self._ensure_config_exists()
        self._load_config()
    
    def _ensure_config_exists(self):
        """创建默认配置文件"""
        if not os.path.exists(self.config_path):
            logging.warning("⚠️ 配置文件不存在，正在创建默认 config.ini...")
            with open(self.config_path, "w", encoding="utf-8") as f:
                f.write(self._DEFAULT_CONFIG)
            sys.exit(f"✅ 默认配置文件已创建: {self.config_path}, 可以冲了")
    
    def _load_config(self):
        """加载并验证配置"""
        self.config = configparser.ConfigParser()
        self.config.read(self.config_path, encoding='utf-8')
        
        try:
            # 基本配置
            self.server = self.config.get('settings', 'SERVER', fallback='localhost:7860')
            self.secret = self.config.get('settings', 'SECRET', fallback='')
            self.device_id = self.config.get('settings', 'DEVICE_ID', fallback='Win_Simple')
            self.device_show_name = self.config.get('settings', 'DEVICE_SHOW_NAME', fallback='Computer')
            self.check_interval = self.config.getint('settings', 'CHECK_INTERVAL', fallback=60)
            
            # 窗口处理配置
            self.skipped_names = self._parse_list('SKIPPED_NAMES', fallback=['Window1', 'Window2'])
            self.not_using_names = self._parse_list('NOT_USING_NAMES', fallback=['App1', 'App2'])
            self.reverse_app_name = self.config.getboolean('settings', 'REVERSE_APP_NAME', fallback=False)
            
            # 鼠标配置
            self.mouse_idle_time = self.config.getint('settings', 'MOUSE_IDLE_TIME', fallback=300)
            self.mouse_move_threshold = self.config.getint('settings', 'MOUSE_MOVE_THRESHOLD', fallback=10)
            
            # 日志配置
            self.log_level = self._get_log_level(fallback='INFO')
            self.log_file = self.config.getboolean('settings', 'LOG_FILE', fallback=True)
            
            # 黑名单配置
            self.blacklist = self._parse_list('BLACKLIST', fallback=['User1', 'User2'])
        
        except Exception as e:
            logging.error(f'配置文件打不开惹: {e}')
            sys.exit(1)
    
    def _parse_list(self, key: str, fallback="") -> list:
        """解析竖线分隔的配置项"""
        value = self.config.get('settings', key, fallback=fallback)
        return [item.strip() for item in value.split('|') if item.strip()]
    
    def _get_log_level(self, fallback='INFO'):
        """获取日志等级"""
        level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR
        }
        return level_map.get(self.config.get('settings', 'LOGLEVEL', fallback=fallback), logging.INFO)

# --------------------------
# 设备状态管理
# --------------------------
class DeviceState:
    """设备状态跟踪管理"""
    def __init__(self, config: AppConfig):
        self.config = config
        self.last_window = ''
        self.cached_window = ''
        self.last_mouse_pos = win32api.GetCursorPos()
        self.last_mouse_time = time()
        self.is_mouse_idle = False

    def check_mouse_idle(self) -> bool:
        """检测鼠标空闲状态"""
        current_pos = win32api.GetCursorPos()
        current_time = time()
        
        # 计算移动距离
        dx = abs(current_pos[0] - self.last_mouse_pos[0])
        dy = abs(current_pos[1] - self.last_mouse_pos[1])
        distance = (dx ** 2 + dy ** 2) ** 0.5
        
        # 超过阈值视为活动
        if distance > self.config.mouse_move_threshold:
            self.last_mouse_pos = current_pos
            self.last_mouse_time = current_time
            if self.is_mouse_idle:
                logging.debug('你起了？饭被我吃完了~')
                self.is_mouse_idle = False
            return False
        
        # 检测空闲超时
        if (current_time - self.last_mouse_time) > (self.config.mouse_idle_time * 60):
            if not self.is_mouse_idle:
                logging.debug('主人睡着了吗，那我要偷吃惹')
                self.is_mouse_idle = True
            return True
        return self.is_mouse_idle

    def process_window_title(self, raw_title: str) -> str:
        """处理窗口标题格式"""
        title = raw_title.strip()
        if self.config.reverse_app_name:
            parts = title.split(' - ')
            return ' - '.join(reversed(parts)) if len(parts) > 1 else title
        return title

# --------------------------
# 设备监控核心逻辑
# --------------------------
class DeviceMonitor:
    """设备状态监控器"""
    def __init__(self, config: AppConfig, state: DeviceState):
        self.config = config
        self.state = state
        self._setup_logging()
    
    def _setup_logging(self):
        """初始化日志配置"""
        handlers = [logging.StreamHandler()]
        if self.config.log_file:
            handlers.append(logging.FileHandler('mirror.log', encoding='utf-8'))
            
        logging.basicConfig(
            level=self.config.log_level,
            datefmt="%Y-%m-%d %H:%M:%S",
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=handlers
        )
    
    def send_state(self, using: bool, window: str = None):
        """发送状态到服务器"""
        if any(blacklisted in window for blacklisted in self.config.blacklist):
            logging.debug(f'应用 {window} 在黑名单中，忽略上报')
            return
        try:
            resp = requests.post(
                url=f'{self.config.server}/api/device/set',
                json={
                    'secret': self.config.secret,
                    'id': self.config.device_id,
                    'show_name': self.config.device_show_name,
                    'using': using,
                    'status': window
                },
                headers={'Content-Type': 'application/json'},
                timeout=5
            )
            resp.raise_for_status()
            self.state.last_window = window
        except requests.RequestException as e:
            logging.warning(f'主人反省一下自己干了什么: {str(e)}')
    
    def _should_update(self, new_window: str, mouse_idle: bool) -> bool:
        """判断是否需要更新状态"""
        return (mouse_idle != self.state.is_mouse_idle) or (new_window != self.state.last_window)
    
    def _handle_skipped_window(self, window: str) -> str:
        """处理需要跳过的窗口"""
        if window not in self.config.skipped_names:
            return window
        
        logging.debug(f'不要~ {window}')
        # 使用上次有效窗口
        fallback = self.state.last_window if self.state.last_window not in self.config.skipped_names else ''
        return fallback if fallback else None
    
    def update_state(self):
        """执行状态检测和更新"""
        try:
            # 获取当前窗口
            raw_window = win32gui.GetWindowText(win32gui.GetForegroundWindow())
            current_window = self.state.process_window_title(raw_window)
            mouse_idle = self.state.check_mouse_idle()
            
            # 处理跳过窗口
            processed_window = self._handle_skipped_window(current_window)
            if not processed_window:
                return
            
            # 判断使用状态
            using = not (processed_window in self.config.not_using_names or mouse_idle)
            
            # 发送更新
            if self._should_update(processed_window, mouse_idle):
                logging.info(f'{using},主人在 {processed_window}')
                self.send_state(using, processed_window)
        except Exception as e:
            self.send_state(False, [str(e)])
            logging.error(f'呼呼呼~{str(e)}')

# --------------------------
# 系统功能模块
# --------------------------

# 控制台窗口控制
_console_visible = True

def get_console_window():
    """获取控制台窗口句柄"""
    return ctypes.windll.kernel32.GetConsoleWindow()

def hide_console():
    """隐藏控制台窗口"""
    global _console_visible
    hwnd = get_console_window()
    if hwnd:
        win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
        _console_visible = False

def show_console():
    """显示控制台窗口"""
    global _console_visible
    hwnd = get_console_window()
    if hwnd:
        win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
        win32gui.SetForegroundWindow(hwnd)
        _console_visible = True

def toggle_console():
    """切换控制台窗口显示状态"""
    if _console_visible:
        hide_console()
    else:
        show_console()

def check_network():
    """检测网络连接"""
    try:
        response = requests.get('https://www.baidu.com/', timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False

# --------------------------
# 托盘图标管理
# --------------------------
class TrayIconManager:
    """系统托盘图标管理器"""
    def __init__(self, icon_path: str = None):
        self.icon_path = icon_path
        self.icon = None
        self._setup_icon()

    def _load_icon(self) -> Image.Image:
        """加载托盘图标"""
        # 尝试加载图标文件
        if self.icon_path and os.path.exists(self.icon_path):
            try:
                return Image.open(self.icon_path)
            except Exception as e:
                logging.warning(f'加载图标失败: {e}，使用默认图标')

        # 创建默认图标（简单的圆形图标）
        return self._create_default_icon()

    def _create_default_icon(self) -> Image.Image:
        """创建默认托盘图标"""
        # 创建一个64x64的图标
        size = 64
        image = Image.new('RGBA', (size, size), (0, 0, 0, 0))

        # 简单的实现：创建一个蓝色圆形图标
        from PIL import ImageDraw
        draw = ImageDraw.Draw(image)
        draw.ellipse([4, 4, size-4, size-4], fill=(52, 152, 219, 255), outline=(41, 128, 185, 255))

        return image

    def _setup_icon(self):
        """设置托盘图标"""
        icon_image = self._load_icon()

        # 创建菜单项
        menu = pystray.Menu(
            pystray.MenuItem(
                lambda text: '隐藏日志' if _console_visible else '显示日志',
                self._toggle_console_wrapper,
                default=True  # 双击托盘图标触发
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('退出', self._exit_app)
        )

        self.icon = pystray.Icon(
            'Win_Simple',
            icon_image,
            'Win_Simple 监控',
            menu
        )

    def _toggle_console_wrapper(self):
        """切换控制台窗口（菜单回调）"""
        toggle_console()
        # 更新菜单显示
        self.icon.menu = pystray.Menu(
            pystray.MenuItem(
                lambda text: '隐藏日志' if _console_visible else '显示日志',
                self._toggle_console_wrapper,
                default=True
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('退出', self._exit_app)
        )

    def _exit_app(self):
        """退出应用"""
        logging.info("用户通过托盘退出")
        self.icon.stop()
        os._exit(0)

    def run(self):
        """启动托盘图标"""
        # 在单独线程中运行托盘
        threading.Thread(target=self.icon.run, daemon=True).start()
        logging.info('托盘图标已启动')

def message_loop(monitor):
    """(需异步执行) 窗口消息循环"""
    def create_window():
        wc = win32gui.WNDCLASS()
        wc.lpfnWndProc = on_shutdown
        wc.lpszClassName = "LoggingWindow"
        wc.hInstance = win32api.GetModuleHandle(None)
        class_atom = win32gui.RegisterClass(wc)
        return win32gui.CreateWindow(class_atom, "状态监控", win32con.WS_OVERLAPPEDWINDOW,
                                     100, 100, 600, 400, 0, 0, wc.hInstance, None)
    
    def on_shutdown(hwnd, msg, wparam, lparam):
        """窗口事件处理"""
        if msg == win32con.WM_QUERYENDSESSION or msg == win32con.WM_CLOSE:
            logging.info("结束了喵...?")
            try:
                resp = monitor.send_state(False,"结束了喵")
                logging.debug(f'Response: {resp.status_code} - {resp.json()}')
                if resp.status_code != 200:
                    logging.warning(f'阿巴阿巴，{resp.status_code} - {resp.json()}')
            except Exception as e:
                logging.warning(f'玛卡巴卡，{e}')
            return True  # 允许关机或注销
           
        return 0
    
    hwnd = create_window()
    # logging.info("启动")
    win32gui.PumpMessages()

# --------------------------
# 主程序入口
# --------------------------
def main():
    config = AppConfig()
    state = DeviceState(config)
    monitor = DeviceMonitor(config, state)

    # 启动托盘图标
    icon_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), 'zmal.ico')
    tray = TrayIconManager(icon_path)
    tray.run()

    # 启动消息循环线程
    threading.Thread(target=message_loop, args=(monitor,), daemon=True).start()

    # 等待网络连接
    while not check_network():
        logging.warning('网络被主人冲坏了喵~，5秒后重试...')
        sleep(5)

    # 主监控循环
    while True:
        try:
            monitor.update_state()
            sleep(config.check_interval)
        except KeyboardInterrupt:
            monitor.send_state(False, "主人要抛弃人家了吗~呜")
            logging.info("主人要抛弃人家了吗~呜")
            sys.exit(0)
        except Exception as e:
            logging.error(f'梦梦不知道哦: {e}')
            monitor.send_state(False, [str(e)])
            sleep(10)


if __name__ == '__main__':
    main()