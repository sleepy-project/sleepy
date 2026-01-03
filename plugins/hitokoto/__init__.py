# coding: utf-8

from logging import getLogger

from pydantic import BaseModel

import plugin as pl
from utils import get_path

name = __name__.split('.')[-1]
l = getLogger(__name__)


class HitokotoConfig(BaseModel):
    standalone: bool = False


p = pl.Plugin(
    name=name,
    require_version_min=(5, 0, 0),
    require_version_max=(6, 0, 0),
    config=HitokotoConfig
)

c: HitokotoConfig = p.config


def init():
    # 加载前端 JS
    try:
        path = get_path(f'plugins/{name}/inject.js')
        with open(path, 'r', encoding='utf-8') as f:
            js = f.read()
        p.add_index_inject(f'''<script>{js}</script>''')
        p.add_panel_inject(f'''<script>{js}</script>''')
        l.debug('inject.js loaded')

        if c.standalone:
            l.info(f'mode: standalone')
            p.add_index_card('hitokoto', more_info_card)
        else:
            l.info(f'mode: append to more-info')
            p.add_index_card('more-info', more_info_append)

        p.add_panel_card('hitokoto', '一言', more_info_card)

    except Exception as e:
        l.error(f'Cannot load inject.js: {e}')


p.init = init


more_info_append = '''<span id="hitokoto-text">一言加载中...</span>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<a id="hitokoto-author" style="font-size: 0.75em;"></a>'''

more_info_card = '''
<div id="hitokoto">
    <p id="hitokoto-text">一言加载中...</p>
    <span style="font-size: 0.85em; display: block; margin-top: 8px;"><a href="#" target="_blank" rel="noopener" id="hitokoto-author"></a></span>
</div>
'''
