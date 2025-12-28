# coding: utf-8

# region init

from logging import getLogger
from datetime import datetime
import time
import json

import pytz
from objtyping import to_primitive
import flask
from flask_cors import cross_origin
from markupsafe import escape
from pydantic import BaseModel

import plugin as pl
from .utils import require_secret, APIUnsuccessful
import utils as u


class V4Config(BaseModel):
    simulate_save_data: bool = False
    '''
    是否模拟 /save_data 的正常返回
    - True: 正常返回 success & 模拟的 data.json 数据
    - False: 报错 Deprecated
    '''


p = pl.Plugin(
    name=__name__,
    require_version_min=(5, 0, 0),
    require_version_max=(6, 0, 0),
    config=V4Config
)

c = p.global_config
d = p.global_data
l = getLogger(__name__)
tz = pytz.timezone(p.global_config.main.timezone)
datefmt = '%Y-%m-%d %H:%M:%S'
conf: V4Config = p.config


@p._app.errorhandler(APIUnsuccessful)
def apiunsuccessful_handler(err: APIUnsuccessful):
    return {
        'success': False,
        'code': err.code,
        'message': err.message
    }, err.http

# endregion init

# region read-only


@p.global_route('/query')
@cross_origin(c.main.cors_origins)
def query_req():
    return query()


def query():
    status = d.status_dict[1]
    del status['id']
    devices = d.device_list
    for dev in devices.values():
        del dev['fields']
        dev['app_name'] = dev['status']
        del dev['status']
        del dev['last_updated']
        del dev['id']
    return {
        'time': datetime.now(tz).strftime(datefmt),
        'timezone': p.global_config.main.timezone,
        'success': True,
        'status': d.status_id,
        'info': status,
        'device': devices,
        'last_updated': datetime.fromtimestamp(d.last_updated, tz).strftime(datefmt),
        'refresh': c.status.refresh_interval,
        'device_status_slice': c.status.device_slice
    }


def _event_stream(ipstr: str):
    last_updated = None
    last_heartbeat = time.time()

    l.info(f'[SSE] Event stream connected: {ipstr}')
    while True:
        current_time = time.time()
        # 检查数据是否已更新
        current_updated = d.last_updated

        # 如果数据有更新, 发送更新事件并重置心跳计时器
        if last_updated != current_updated:
            last_updated = current_updated
            # 重置心跳计时器
            last_heartbeat = current_time

            # 获取 /query 返回数据
            update_data = json.dumps(query(), ensure_ascii=False)
            yield f'event: update\ndata: {update_data}\n\n'

        # 只有在没有数据更新的情况下才检查是否需要发送心跳
        elif current_time - last_heartbeat >= 30:
            timenow = datetime.now(tz)
            yield f"event: heartbeat\ndata: {timenow.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            last_heartbeat = current_time

        time.sleep(1)  # 每秒检查一次更新


@p.global_route('/events')
@cross_origin(c.main.cors_origins)
def events():
    '''
    SSE 事件流，用于推送状态更新
    - Method: **GET**
    '''
    evt = p.trigger_event(pl.StreamConnectedEvent(0))
    if evt.interception:
        return evt.interception
    ipstr: str = flask.g.ipstr

    response = flask.Response(_event_stream(ipstr), mimetype='text/event-stream', status=200)
    response.headers['Cache-Control'] = 'no-cache'  # 禁用缓存
    response.headers['X-Accel-Buffering'] = 'no'  # 禁用 Nginx 缓冲
    response.call_on_close(lambda: (
        l.info(f'[SSE] Event stream disconnected: {ipstr}'),
        p.trigger_event(pl.StreamDisconnectedEvent())
    ))
    return response


@p.global_route('/status_list')
@cross_origin(c.main.cors_origins)
def status_list():
    return [
        to_primitive(i) for i in c.status.status_list
    ]


if c.metrics.enabled:
    @p.global_route('/metrics')
    @cross_origin(c.main.cors_origins)
    def metrics():
        now = datetime.now(tz)
        metric = d.metrics_resp
        metric['time'] = f'{now.year}-{now.month:02d}-{now.day:02d} {now.hour:02d}:{now.minute:02d}:{now.second:02d}.{now.microsecond:06d}'
        del metric['time_local']
        metric['today'] = metric.pop('daily', {})
        metric['month'] = metric.pop('monthly', {})
        metric['year'] = metric.pop('yearly', {})
        del metric['weekly']
        del metric['success']
        metric['today_is'] = f'{now.year}-{now.month:}-{now.day}'
        metric['month_is'] = f'{now.year}-{now.month}'
        metric['year_is'] = f'{now.year}'
        del metric['enabled']
        return metric

# endregion read-only

# region status


@p.global_route('/set')
@cross_origin(c.main.cors_origins)
@require_secret()
def set_status():
    status = escape(flask.request.args.get('status'))
    try:
        status = int(status)
    except:
        raise APIUnsuccessful('bad request', "argument 'status' must be a number", 400)
    d.status

    if not status == d.status_id:
        old_status = d.status
        new_status = d.get_status(status)
        evt = p.trigger_event(pl.StatusUpdatedEvent(
            old_exists=old_status[0],
            old_status=old_status[1],
            new_exists=new_status[0],
            new_status=new_status[1]
        ))
        if evt.interception:
            return evt.interception
        status = evt.new_status.id

        d.status_id = status

    return {
        'success': True,
        'set_to': status
    }

# endregion status

# region device


@p.global_route('/device/set', methods=['GET', 'POST'])
@cross_origin(c.main.cors_origins)
@require_secret()
def device_set():
    # 分 get / post 从 params / body 获取参数
    if flask.request.method == 'GET':
        args = dict(flask.request.args)
        device_id = args.get('id', None)
        device_show_name = args.get('show_name', None)
        device_using = u.tobool(args.get('using', None))
        device_status = args.get('app_name', None)

        evt = p.trigger_event(pl.DeviceSetEvent(
            device_id=device_id,
            show_name=device_show_name,
            using=device_using,
            status=device_status,
            fields={}
        ))
        if evt.interception:
            return evt.interception

        d.device_set(
            id=evt.device_id,
            show_name=evt.show_name,
            using=evt.using,
            status=evt.status,
            fields=evt.fields
        )

    elif flask.request.method == 'POST':
        try:
            req: dict = flask.request.get_json()

            evt = p.trigger_event(pl.DeviceSetEvent(
                device_id=req.get('id'),
                show_name=req.get('show_name'),
                using=req.get('using'),
                status=req.get('app_name'),
                fields={}
            ))
            if evt.interception:
                return evt.interception

            d.device_set(
                id=evt.device_id,
                show_name=evt.show_name,
                using=evt.using,
                status=evt.status,
                fields=evt.fields
            )
        except Exception as e:
            if isinstance(e, u.APIUnsuccessful):
                raise e
            else:
                raise APIUnsuccessful('bad request', 'missing param or wrong param type', 400)

    return {
        'success': True,
        'code': 'OK'
    }


@p.global_route('/device/remove')
@cross_origin(c.main.cors_origins)
@require_secret()
def device_remove():
    device_id = flask.request.args.get('id')
    if not device_id:
        raise APIUnsuccessful('not found', 'cannot find item', 404)

    device = d.device_get(device_id)

    if device:
        evt = p.trigger_event(pl.DeviceRemovedEvent(
            exists=True,
            device_id=device_id,
            show_name=device.show_name,
            using=device.using,
            status=device.status,
            fields=device.fields
        ))
    else:
        raise APIUnsuccessful('not found', 'cannot find item', 404)

    if evt.interception:
        return evt.interception

    d.device_remove(evt.device_id)

    return {
        'success': True,
        'code': 'OK'
    }


@p.global_route('/device/clear')
@cross_origin(c.main.cors_origins)
@require_secret()
def device_clear():
    evt = p.trigger_event(pl.DeviceClearedEvent(d._raw_device_list))
    if evt.interception:
        return evt.interception

    d.device_clear()

    return {
        'success': True,
        'code': 'OK'
    }


@p.global_route('/device/private_mode')
@cross_origin(c.main.cors_origins)
@require_secret()
def device_private_mode():
    private = u.tobool(flask.request.args.get('private'))
    if private == None:
        raise APIUnsuccessful('invaild request', '"private" arg only supports boolean type', 400)
    elif not private == d.private_mode:
        evt = p.trigger_event(pl.PrivateModeChangedEvent(d.private_mode, private))
        if evt.interception:
            return evt.interception

        d.private_mode = evt.new_status

    return {
        'success': True,
        'code': 'OK'
    }

# endregion device

# region storage


@p.global_route('/save_data')
@cross_origin(c.main.cors_origins)
@require_secret()
def save_data():
    if conf.simulate_save_data:
        devices = d.device_list
        for dev in devices.values():
            del dev['fields']
            dev['app_name'] = dev['status']
            del dev['status']
            del dev['last_updated']
            del dev['id']
        return {
            'success': True,
            'code': 'OK',
            'data': {
                'status': d.status_id,
                'device_status': devices,
                'last_updated': datetime.fromtimestamp(d.last_updated, tz).strftime(datefmt)
            }
        }
    else:
        raise APIUnsuccessful('exception', 'Save data function is deprecated!', 500)

# endregion storage

# region end


def init():
    l.info('Version 4 API Compatible Loaded!')


p.init = init

# endregion end
