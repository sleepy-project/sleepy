# coding: utf-8

# region init

from logging import getLogger
from datetime import datetime

import pytz
from objtyping import to_primitive
import flask
from markupsafe import escape

import plugin as pl
from .utils import require_secret, APIUnsuccessful

l = getLogger(__name__)
p = pl.Plugin(
    name='v4_compatible',
    require_version_min=(5, 0, 0)
)
tz = pytz.timezone(p.global_config.main.timezone)

c = p.global_config
d = p.global_data
datefmt = '%Y-%m-%d %H:%M:%S'


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


@p.global_route('/status_list')
def status_list():
    return [
        to_primitive(i) for i in c.status.status_list
    ]


if c.metrics.enabled:
    @p.global_route('/metrics')
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

# region end


def init():
    l.info('Version 4 API Compatible Loaded!')

p.init = init

# endregion end
