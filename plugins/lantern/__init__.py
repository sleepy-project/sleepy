# coding: utf-8

from logging import getLogger

from pydantic import BaseModel

import plugin as pl
from utils import get_path

name = __name__.split('.')[-1]
l = getLogger(__name__)


class LanternConfig(BaseModel):
    left_close: str = '欢'
    '左侧外处灯笼'
    left: str = '度'
    '左侧灯笼'
    right: str = '新'
    '右侧灯笼'
    right_close: str = '春'
    '右侧外处灯笼'


p = pl.Plugin(
    name,
    require_version_min=(5, 0, 0),
    require_version_max=(6, 0, 0),
    config=LanternConfig
)

c: LanternConfig = p.config


def init():
    try:
        # load static files
        with open(get_path(f'plugins/{name}/inject.html'), 'r', encoding='utf-8') as f:
            html = f.read()
        with open(get_path(f'plugins/{name}/inject.css'), 'r', encoding='utf-8') as f:
            css = f.read()

        # replace chars
        html = html.format(
            left_close=c.left_close,
            left=c.left,
            right=c.right,
            right_close=c.right_close
        )

        p.add_index_inject(f'''
{html}
<style>
{css}
</style>
'''[1:-1])

    except Exception as e:
        l.error(f'Cannot load lantern asset: {e}')

p.init = init
