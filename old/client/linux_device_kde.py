# coding: utf-8
'''
linux_device_kde.py
在 Linux (KDE) 上获取窗口名称
by: @RikkaNaa
依赖: kdotool, requests
'''

from requests import post
from datetime import datetime
from time import sleep
from sys import stdout, exit
from io import TextIOWrapper
import subprocess
import signal


# --- config start
SERVER = 'http://localhost:9010'  # 服务地址, 末尾还是不带 /
SECRET = 'wyf9test'  # 密钥
DEVICE_ID = 'device-1'  # 设备标识符
DEVICE_SHOW_NAME = 'MyDevice1'  # 前台显示名称
CHECK_INTERVAL = 2  # 检查间隔，以秒为单位
BYPASS_SAME_REQUEST = True  # 是否忽略重复请求
ENCODING = 'utf-8'  # 控制台输出所用编码，避免编码出错，可选 utf-8 或 gb18030
SKIPPED_NAMES = ['', 'plasmashell']  # 当窗口名为其中任意一项时将不更新
NOT_USING_NAMES = ['[FAILED]']  # 当窗口名为其中任意一项时视为未在使用
# --- config end

stdout = TextIOWrapper(stdout.buffer, encoding=ENCODING)  # https://stackoverflow.com/a/3218048/28091753
_print_ = print


def print(msg: str, **kwargs):
    '''
    修改后的 `print()` 函数，解决不刷新日志的问题
    原: `_print_()`
    '''
    _print_(f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {msg}', flush=True, **kwargs)


def get_active_window_title():
    '''
    获取窗口标题, 如检测失败则为 `[FAILED]`
    '''
    # window_title = subprocess.check_output(["kdotool", "getactivewindow", "getwindowname"]).strip()
    # return window_title.decode()
    result = subprocess.run(["kdotool", "getactivewindow", "getwindowname"], capture_output=True, text=True)
    if result.returncode == 0:
        window_name = result.stdout.replace("\n", "")
        return window_name
    else:
        print(f'Return code isn\'t 0: {result.returncode}!')
        return '[FAILED]'


Url = f'{SERVER}/api/device/set'
last_window = ''


def do_update():
    '''
    进行更新
    '''
    global last_window
    window = get_active_window_title()
    print(f'--- Window: `{window}`')

    # 检测重复名称
    if (BYPASS_SAME_REQUEST and window == last_window):
        print('window not change, bypass')
        return

    # 检查跳过名称
    for i in SKIPPED_NAMES:
        if i == window:
            print(f'* skipped: `{i}`')
            return

    # 判断是否在使用
    using = True
    for i in NOT_USING_NAMES:
        if i == window:
            print(f'* not using: `{i}`')
            using = False

    # POST to api
    print(f'POST {Url}')
    try:
        resp = post(url=Url, json={
            'secret': SECRET,
            'id': DEVICE_ID,
            'show_name': DEVICE_SHOW_NAME,
            'using': using,
            'status': window
        }, headers={
            'Content-Type': 'application/json'
        })
        print(f'Response: {resp.status_code} - {resp.json()}')
    except Exception as e:
        print(f'Error: {e}')
    last_window = window


def interrupt_req():
    '''
    在中断时发送 未在使用 请求
    '''
    try:
        resp = post(url=Url, json={
            'secret': SECRET,
            'id': DEVICE_ID,
            'show_name': DEVICE_SHOW_NAME,
            'using': False,
            'status': 'Kill or Shutdown'
        }, headers={
            'Content-Type': 'application/json'
        })
        print(f'Response: {resp.status_code} - {resp.json()}')
    except Exception as e:
        print(f'Error: {e}')


def sigterm_handler(signum, frame):
    '''
    处理 SIGTERM
    '''
    print('SIGTERM received')
    interrupt_req()
    exit(0)


def main():
    '''
    主循环
    '''
    while True:
        do_update()
        sleep(CHECK_INTERVAL)


if __name__ == '__main__':
    try:
        signal.signal(signal.SIGTERM, sigterm_handler)  # 注册 handler
        main()
    except KeyboardInterrupt as e:
        # 如果中断则发送未在使用
        print(f'Interrupt: {e}')
        interrupt_req()
