# coding: utf-8

from logging import getLogger
from threading import Thread
from time import sleep, time

from pydantic import BaseModel

import plugin as pl

l = getLogger(__name__)


class AutoDeadConfig(BaseModel):
    '''插件配置'''
    check_interval: int = 60  # 检查间隔(秒), 默认每分钟检查一次
    timeout_minutes: int = 15  # 超时时间(分钟), 默认15分钟
    dead_status_id: int = 1    # 超时后设置的状态ID, 默认为1


# 初始化插件实例
plugin = pl.Plugin(
    name='auto_dead',
    require_version_min=(5, 0, 0),
    require_version_max=(6, 0, 0),
    config=AutoDeadConfig
)

# 获取配置
config: AutoDeadConfig = plugin.config
data = plugin.global_data


def check_and_update_status():
    '''
    检查最后更新时间,如果超时则自动设置状态为"似了"
    - 获取所有设备的最后更新时间,取最新的一个
    - 检查设备状态,如果设备"未在使用"且超时也触发状态更新
    '''
    try:
        current_time = time()
        timeout_seconds = config.timeout_minutes * 60

        # 获取所有设备
        devices = data._raw_device_list

        if not devices:
            # 没有设备,使用主数据的 last_updated
            last_updated = data.last_updated
            time_diff = current_time - last_updated

            if time_diff > timeout_seconds:
                current_status = data.status_id
                if current_status != config.dead_status_id:
                    old_status_name = data.status[1].name if data.status[0] else "Unknown"
                    data.status_id = config.dead_status_id
                    new_status = data.status[1]
                    l.info(
                        f'[auto_dead] 无设备,主数据超时 {time_diff:.0f}秒 ({time_diff/60:.1f}分钟), '
                        f'状态已从 "{old_status_name}" 自动更新为 "{new_status.name}"'
                    )
            else:
                # 未超时,记录信息
                remaining_minutes = (timeout_seconds - time_diff) / 60
                l.info(
                    f'[auto_dead] 无设备模式 - 距离超时还有 {remaining_minutes:.1f} 分钟 '
                    f'(已过 {time_diff/60:.1f} 分钟 / {config.timeout_minutes} 分钟)'
                )
            return

        # 找出最新更新的设备
        latest_device = None
        latest_time = 0
        not_using_devices = []

        for device_id, device in devices.items():
            device_time = device.last_updated

            # 记录最新更新的设备
            if device_time > latest_time:
                latest_time = device_time
                latest_device = device_id

            # 记录"未在使用"的设备
            if device.using == False:
                not_using_devices.append({
                    'id': device_id,
                    'name': device.show_name,
                    'last_updated': device_time
                })

        # 计算最新设备的时间差
        time_diff = current_time - latest_time

        # 检查是否超时
        should_update = False
        reason = ""

        if time_diff > timeout_seconds:
            # 最新设备超时
            should_update = True
            reason = f"最新设备 {latest_device} 超时 {time_diff:.0f}秒 ({time_diff/60:.1f}分钟)"
        else:
            # 检查"未在使用"的设备是否超时
            for device_info in not_using_devices:
                device_time_diff = current_time - device_info['last_updated']
                if device_time_diff > timeout_seconds:
                    should_update = True
                    reason = f"未在使用设备 {device_info['name']} 超时 {device_time_diff:.0f}秒 ({device_time_diff/60:.1f}分钟)"
                    break

        # 执行状态更新
        if should_update:
            current_status = data.status_id
            if current_status != config.dead_status_id:
                old_status_name = data.status[1].name if data.status[0] else "Unknown"
                data.status_id = config.dead_status_id
                new_status = data.status[1]
                l.info(
                    f'[auto_dead] {reason}, '
                    f'状态已从 "{old_status_name}" 自动更新为 "{new_status.name}"'
                )
        else:
            # 未超时,记录调试信息
            remaining_minutes = (timeout_seconds - time_diff) / 60
            l.debug(
                f'[auto_dead] 距离超时还有 {remaining_minutes:.1f} 分钟 '
                f'(最新设备: {latest_device}, 已过 {time_diff/60:.1f} 分钟 / {config.timeout_minutes} 分钟, '
                f'设备总数: {len(devices)}, 未在使用: {len(not_using_devices)})'
            )

    except Exception as e:
        l.error(f'[auto_dead] 检查状态时发生错误: {e}')


def background_checker():
    '''
    后台检查线程
    '''
    l.info(f'[auto_dead] 后台检查线程已启动, 每 {config.check_interval} 秒检查一次, '
           f'超时阈值: {config.timeout_minutes} 分钟')

    while True:
        try:
            check_and_update_status()
        except Exception as e:
            l.error(f'[auto_dead] 后台检查线程发生错误: {e}')

        # 等待下一次检查
        sleep(config.check_interval)


@plugin.event_handler(pl.DeviceSetEvent)
def on_device_set(event: pl.DeviceSetEvent, request):
    '''
    当有设备更新时,如果当前状态是"似了",自动复活为"活着"
    '''
    current_status = data.status_id
    if current_status == config.dead_status_id:
        alive_status = data.get_status(0)
        alive_name = alive_status[1].name if alive_status[0] else "活着"
        dead_name = data.status[1].name if data.status[0] else "似了"
        data.status_id = 0
        l.info(
            f'[auto_dead] 检测到设备 {event.device_id} 更新, '
            f'状态已从 "{dead_name}" 自动恢复为 "{alive_name}"'
        )
    return event


def init():
    '''插件初始化'''
    # 启动后台检查线程(daemon=True,主线程退出时自动结束)
    checker_thread = Thread(target=background_checker, daemon=True)
    checker_thread.start()

    l.info(f'[auto_dead] 插件已加载 - 超时 {config.timeout_minutes} 分钟后将自动设置状态为 ID={config.dead_status_id}')
    l.info('[auto_dead] 设备更新时将自动恢复状态为"活着"')


# 覆盖默认的 init 方法
plugin.init = init