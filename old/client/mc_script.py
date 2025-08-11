# coding: utf-8
'''
mc_script.py

使用 Minescript 获取 MC 游戏中信息
by: @wyf9
依赖: requests, minescript (MOD)
'''

# 不要使用格式化!!! 会打乱顺序!!!
import time
from system.lib import minescript as mc  # type: ignore / 写好记得把 system 前面的 . 去掉, 否则会报错
import sys
# sys.path.append(r'C:\Users\wyf01\AppData\Roaming\Python\Python312\site-packages')  # 如提示找不到库, 在此将你的 site-packages 目录添加至局部 PATH
from requests import post

# --- config start
SERVER = 'https://sleepy.example.com'  # 服务器地址, 末尾不带 /
SECRET = 'this_is_a_strong_key'  # 密钥
DEVICE_ID = 'device-1'  # 设备 id, 唯一
DEVICE_SHOW_NAME = 'MyDevice1'  # 设备前台显示名称
CHECK_INTERVAL = 10  # 监测间隔 (秒)
BYPASS_SAME_REQUEST = True  # 是否忽略相同请求
DEBUG = False  # 调试模式, 开启以获得更多输出
# --- config end


def log(msg: str, important: bool = False) -> None:
    if DEBUG or important:
        print(f'[sleepy] {msg}')


Url = f'{SERVER}/api/device/set'

try:
    if sys.argv[1].lower() == 'stop':
        log('Stopping.', important=True)
        self_id = 0
        # kill jobs (except self)
        for i in mc.job_info():
            if str(i.command).startswith('[\'sleepy') and i.status == 'RUNNING':
                if i.self:
                    self_id = i.job_id
                else:
                    mc.execute(f'\\killjob {i.job_id}')
        # send stop request
        error_info = ''
        for i in range(3):
            try:
                resp = post(url=Url, json={
                    'secret': SECRET,
                    'id': DEVICE_ID,
                    'show_name': DEVICE_SHOW_NAME,
                    'using': False,
                    'status': '[Stopped]'
                }, headers={
                    'Content-Type': 'application/json'
                })
                Json = resp.json()
                log(f'Response: {resp.status_code} - {Json}')
                if Json['success'] == True:
                    break
                else:
                    log(f'return not success: {Json}')
                    error_info = f'(Response) {resp.status_code} {Json}'
                    continue
            except Exception as e:
                log(f'Error: {e}')
                error_info = f'(Exception) {e}'
                continue
        if not error_info:
            log(f'WARNING: send request failed: {error_info}')
        if self_id:
            # kill self
            mc.execute(f'\\killjob {self_id}')
        else:
            log('get self id failed, exit manually', important=True)
        exit(0)
except:
    pass
# -----


def get_info():
    '''
    获取游戏内信息, 拼接为完整 status 并返回

    :return: `status` 字符串
    '''
    _version_info = mc.version_info()
    _world_info = mc.world_info()

    # --- get info start
    player_name = mc.player_name()  # 当前玩家名字 (str)
    pos_x, pos_y, pos_z = mc.player_position()  # 玩家当前位置 (float)
    player_health = mc.player_health()  # 玩家当前生命值 (float)
    mc_ver = _version_info.minecraft  # Minecraft 版本 (str)
    minescript_ver = _version_info.minescript  # Minescript mod 版本 (str)
    mod_loader_name = _version_info.mod_loader  # Mod 加载器名称, 如 "Fabric" (str)
    launcher = _version_info.launcher  # 未知
    os_name = _version_info.os_name  # 系统名称, 如 "Windows 11" (str)
    os_version = _version_info.os_version  # 系统版本, 如 "10.0", 可能有误? (str)
    world_ticks = _world_info.game_ticks  # 世界已过 ticks (int)
    day_ticks = _world_info.day_ticks  # 今日 (游戏日) 已过 ticks (int)
    raining = _world_info.raining  # 是否正在下普通雨 (bool)
    thundering = _world_info.thundering  # 是否正在下雷雨 (bool)
    # 已知问题: 可能无法正确获取下雨状态
    world_name = _world_info.name  # 世界名称, 如服务器则为本地别名 (str)
    server_address = _world_info.address  # 服务器地址 (str)
    weather: str  # 当前天气 - 晴 / 雨 / 雷暴 (str)
    if thundering:
        weather = '雷暴'
    elif raining:
        weather = '雨'
    else:
        weather = '晴'
    return f'{mc_ver} {mod_loader_name} - {player_name} @ {world_name} - 血量: {player_health} - 天气: {weather}'  # 最终上报的应用名
    # --- get info end


last_status = ''


def do_update(status):
    '''
    进行一次更新

    :param status: 从 `get_info()` 获取
    :return 0: 成功
    :return 1: 请求时出错
    :return 2: 返回中 `success` 不为 `true`
    '''
    # POST to api
    log(f'POST {Url}')
    try:
        resp = post(url=Url, json={
            'secret': SECRET,
            'id': DEVICE_ID,
            'show_name': DEVICE_SHOW_NAME,
            'using': True,
            'status': status
        }, headers={
            'Content-Type': 'application/json'
        })
        Json = resp.json()
        log(f'Response: {resp.status_code} - {Json}')
        if Json['success'] == True:
            return 0  # 成功
        else:
            log(f'Warning: return not success: {Json}')
            return 2  # 返回中 `success` 不为 `true`
    except Exception as e:
        log(f'Error: {e}', important=True)
        return 1  # 请求时出错


log('Started')

while True:
    status = get_info()
    if status != last_status:
        # 与上次不同, 更新
        log(f'Status: {status}')
        ret = do_update(status=status)
        if not ret:
            # 失败时不更新上次信息, 以便 interval 后重试
            last_status = status
    time.sleep(CHECK_INTERVAL)
