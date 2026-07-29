# coding: utf-8
import os
import sys
import configparser
import requests
import logging
import threading
import ctypes
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import win32gui, win32con, win32api
from time import time, sleep
import pystray
from PIL import Image, ImageDraw

#cd client/Win_Simple
#pyinstaller -F -w -n Win_Simple.exe --icon=zmal.ico ^
#  --hidden-import=win32gui --hidden-import=win32con --hidden-import=win32api ^
#  --hidden-import=requests --hidden-import=pystray --hidden-import=PIL.Image ^
#  --hidden-import=tkinter ^
#  --exclude-module=numpy --exclude-module=psutil --exclude-module=matplotlib ^
#  --exclude-module=pandas --exclude-module=IPython --exclude-module=jupyter ^
#  script.py --clean

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
# 启动时最小化到托盘
MINIMIZE_TO_TRAY = False
"""
    
    def __init__(self):
        self.config_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "config.ini")
        self._ensure_config_exists()
        self._load_config()
    
    def _ensure_config_exists(self):
        """创建默认配置文件"""
        if not os.path.exists(self.config_path):
            with open(self.config_path, "w", encoding="utf-8") as f:
                f.write(self._DEFAULT_CONFIG)
            logging.warning(f"配置文件已创建: {self.config_path}")
    
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

            # 界面配置
            self.minimize_to_tray = self.config.getboolean('settings', 'MINIMIZE_TO_TRAY', fallback=False)

            # 黑名单配置
            self.blacklist = self._parse_list('BLACKLIST', fallback=['User1', 'User2'])
        
        except Exception as e:
            logging.error(f'配置文件打不开惹: {e}')
    
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

    def save(self):
        """保存配置到文件"""
        self.config.set('settings', 'SERVER', self.server)
        self.config.set('settings', 'SECRET', self.secret)
        self.config.set('settings', 'DEVICE_ID', self.device_id)
        self.config.set('settings', 'DEVICE_SHOW_NAME', self.device_show_name)
        self.config.set('settings', 'CHECK_INTERVAL', str(self.check_interval))
        self.config.set('settings', 'REVERSE_APP_NAME', str(self.reverse_app_name))
        self.config.set('settings', 'MOUSE_IDLE_TIME', str(self.mouse_idle_time))
        self.config.set('settings', 'MOUSE_MOVE_THRESHOLD', str(self.mouse_move_threshold))
        self.config.set('settings', 'LOGLEVEL', self.config.get('settings', 'LOGLEVEL', fallback='INFO'))
        self.config.set('settings', 'LOG_FILE', str(self.log_file))
        self.config.set('settings', 'MINIMIZE_TO_TRAY', str(self.minimize_to_tray))
        
        with open(self.config_path, 'w', encoding='utf-8') as f:
            self.config.write(f)

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
        
        dx = abs(current_pos[0] - self.last_mouse_pos[0])
        dy = abs(current_pos[1] - self.last_mouse_pos[1])
        distance = (dx ** 2 + dy ** 2) ** 0.5
        
        if distance > self.config.mouse_move_threshold:
            self.last_mouse_pos = current_pos
            self.last_mouse_time = current_time
            if self.is_mouse_idle:
                self.is_mouse_idle = False
            return False
        
        if (current_time - self.last_mouse_time) > (self.config.mouse_idle_time * 60):
            if not self.is_mouse_idle:
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
    def __init__(self, config: AppConfig, state: DeviceState, log_callback=None):
        self.config = config
        self.state = state
        self.log_callback = log_callback
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
    
    def log(self, message, level='info'):
        """输出日志"""
        if self.log_callback:
            self.log_callback(message, level)
        if level == 'error':
            logging.error(message)
        elif level == 'warning':
            logging.warning(message)
        else:
            logging.info(message)
    
    def send_state(self, using: bool, window: str = None):
        """发送状态到服务器"""
        if any(blacklisted in window for blacklisted in self.config.blacklist):
            self.log(f'应用 {window} 在黑名单中，忽略上报', 'debug')
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
            self.log(f'网络错误: {str(e)}', 'warning')
    
    def _should_update(self, new_window: str, mouse_idle: bool) -> bool:
        """判断是否需要更新状态"""
        return (mouse_idle != self.state.is_mouse_idle) or (new_window != self.state.last_window)
    
    def _handle_skipped_window(self, window: str) -> str:
        """处理需要跳过的窗口"""
        if window not in self.config.skipped_names:
            return window
        
        fallback = self.state.last_window if self.state.last_window not in self.config.skipped_names else ''
        return fallback if fallback else None
    
    def update_state(self):
        """执行状态检测和更新"""
        try:
            raw_window = win32gui.GetWindowText(win32gui.GetForegroundWindow())
            current_window = self.state.process_window_title(raw_window)
            mouse_idle = self.state.check_mouse_idle()
            
            processed_window = self._handle_skipped_window(current_window)
            if not processed_window:
                return
            
            using = not (processed_window in self.config.not_using_names or mouse_idle)
            
            if self._should_update(processed_window, mouse_idle):
                self.log(f'{using}, 主人在 {processed_window}')
                self.send_state(using, processed_window)
        except Exception as e:
            self.send_state(False, [str(e)])
            self.log(f'错误: {str(e)}', 'error')

# --------------------------
# GUI 应用
# --------------------------
class AppGUI:
    """图形界面应用"""
    MAX_LOG_LINES = 1000  # 最大日志行数，防止内存溢出

    def __init__(self, config: AppConfig, monitor: DeviceMonitor):
        self.config = config
        self.monitor = monitor
        self.root = tk.Tk()
        self.tray_icon = None
        self._exit_flag = threading.Event()
        self._log_lock = threading.Lock()  # 日志线程锁
        self._setup_window()
        self._setup_widgets()
        self._setup_tray()

    def _setup_window(self):
        """设置窗口"""
        self.root.title("Win_Simple 监控")
        self.root.geometry("600x500")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 设置窗口图标
        icon_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), 'zmal.ico')
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except:
                pass

    def _setup_widgets(self):
        """设置界面控件"""
        # 创建标签页
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True, padx=5, pady=5)

        # 日志标签页
        log_frame = ttk.Frame(notebook)
        notebook.add(log_frame, text='日志')

        self.log_text = scrolledtext.ScrolledText(log_frame, state='disabled', wrap='word')
        self.log_text.pack(fill='both', expand=True, padx=5, pady=5)

        # 设置日志回调
        self.monitor.log_callback = self._append_log

        # 配置标签页
        config_frame = ttk.Frame(notebook)
        notebook.add(config_frame, text='配置')

        # 配置表单
        self._setup_config_form(config_frame)

        # 状态栏
        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill='x', side='bottom')
        self.status_label = ttk.Label(status_frame, text="就绪")
        self.status_label.pack(side='left', padx=5)

    def _setup_config_form(self, parent):
        """设置配置表单"""
        # 创建滚动区域
        canvas = tk.Canvas(parent)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 配置项
        row = 0
        config_fields = [
            ('服务器地址:', 'server'),
            ('密钥:', 'secret'),
            ('设备ID:', 'device_id'),
            ('显示名称:', 'device_show_name'),
            ('检查间隔(秒):', 'check_interval'),
            ('鼠标空闲时间(分钟):', 'mouse_idle_time'),
            ('鼠标移动阈值(像素):', 'mouse_move_threshold'),
        ]

        self.config_vars = {}

        for label_text, key in config_fields:
            ttk.Label(scrollable_frame, text=label_text).grid(row=row, column=0, sticky='w', padx=5, pady=2)
            var = tk.StringVar(value=str(getattr(self.config, key)))
            entry = ttk.Entry(scrollable_frame, textvariable=var, width=40)
            entry.grid(row=row, column=1, sticky='w', padx=5, pady=2)
            self.config_vars[key] = var
            row += 1

        # 复选框配置
        ttk.Label(scrollable_frame, text='启动时最小化到托盘:').grid(row=row, column=0, sticky='w', padx=5, pady=2)
        self.minimize_var = tk.BooleanVar(value=self.config.minimize_to_tray)
        ttk.Checkbutton(scrollable_frame, variable=self.minimize_var).grid(row=row, column=1, sticky='w', padx=5, pady=2)
        row += 1

        # 保存按钮
        ttk.Button(scrollable_frame, text='保存配置', command=self._save_config).grid(row=row, column=0, columnspan=2, pady=10)

    def _setup_tray(self):
        """设置托盘图标"""
        icon_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), 'zmal.ico')

        # 创建图标
        icon_image = self._create_tray_icon(icon_path)

        # 创建菜单
        menu = pystray.Menu(
            pystray.MenuItem('显示窗口', self._show_window, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('退出', self._exit_app)
        )

        self.tray_icon = pystray.Icon('Win_Simple', icon_image, 'Win_Simple 监控', menu)

    def _create_tray_icon(self, icon_path: str) -> Image.Image:
        """创建托盘图标"""
        if icon_path and os.path.exists(icon_path):
            try:
                return Image.open(icon_path)
            except:
                pass

        # 创建默认图标
        size = 64
        image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse([4, 4, size-4, size-4], fill=(52, 152, 219, 255), outline=(41, 128, 185, 255))
        return image

    def _append_log(self, message: str, level: str = 'info'):
        """添加日志到文本框（线程安全）"""
        with self._log_lock:
            try:
                self.log_text.config(state='normal')
                from datetime import datetime
                time_str = datetime.now().strftime("%H:%M:%S")
                self.log_text.insert('end', f"[{time_str}] {message}\n")

                # 限制日志行数，防止内存溢出
                line_count = int(self.log_text.index('end-1c').split('.')[0])
                if line_count > self.MAX_LOG_LINES:
                    self.log_text.delete('1.0', f'{line_count - self.MAX_LOG_LINES}.0')

                self.log_text.see('end')
                self.log_text.config(state='disabled')
            except tk.TclError:
                pass  # 窗口已关闭

    def _save_config(self):
        """保存配置"""
        try:
            self.config.server = self.config_vars['server'].get()
            self.config.secret = self.config_vars['secret'].get()
            self.config.device_id = self.config_vars['device_id'].get()
            self.config.device_show_name = self.config_vars['device_show_name'].get()
            self.config.check_interval = int(self.config_vars['check_interval'].get())
            self.config.mouse_idle_time = int(self.config_vars['mouse_idle_time'].get())
            self.config.mouse_move_threshold = int(self.config_vars['mouse_move_threshold'].get())
            self.config.minimize_to_tray = self.minimize_var.get()

            self.config.save()
            self._append_log('配置已保存')
            messagebox.showinfo('成功', '配置已保存')
        except ValueError as e:
            messagebox.showerror('错误', f'请输入有效的数值: {e}')
        except Exception as e:
            messagebox.showerror('错误', f'保存失败: {e}')

    def _show_window(self, icon=None, item=None):
        """显示窗口"""
        try:
            self.root.deiconify()
            self.root.state('normal')
            self.root.focus_force()
        except:
            pass

    def _hide_window(self):
        """隐藏窗口到托盘"""
        try:
            self.root.withdraw()
        except:
            pass

    def _on_close(self):
        """窗口关闭事件"""
        self._hide_window()

    def _exit_app(self, icon=None, item=None):
        """退出应用"""
        # 退出前发送离线状态
        try:
            self.monitor.send_state(False, "已离线")
            self.monitor.log("程序已退出，发送离线状态")
        except:
            pass

        self._exit_flag.set()
        if self.tray_icon:
            self.tray_icon.stop()
        try:
            self.root.quit()
        except:
            pass

    def run(self):
        """运行应用"""
        # 启动托盘图标
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

        # 如果配置为最小化启动，则隐藏窗口
        if self.config.minimize_to_tray:
            self.root.after(100, self._hide_window)

        self.root.mainloop()

# --------------------------
# 网络检测
# --------------------------
def check_network():
    """检测网络连接"""
    try:
        response = requests.get('https://www.baidu.com/', timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False

# --------------------------
# 主程序入口
# --------------------------
def main():
    config = AppConfig()
    state = DeviceState(config)
    monitor = DeviceMonitor(config, state)
    
    app = AppGUI(config, monitor)
    
    # 启动监控线程
    def monitor_loop():
        while not check_network():
            monitor.log('网络连接失败，5秒后重试...', 'warning')
            sleep(5)
        
        monitor.log('网络连接成功，开始监控')
        
        while True:
            try:
                monitor.update_state()
                sleep(config.check_interval)
            except Exception as e:
                monitor.log(f'监控错误: {e}', 'error')
                sleep(10)
    
    threading.Thread(target=monitor_loop, daemon=True).start()
    
    app.run()

if __name__ == '__main__':
    main()