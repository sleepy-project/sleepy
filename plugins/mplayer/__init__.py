# coding: utf-8

from logging import getLogger

import plugin as pl
from utils import get_path

name = __name__.split('.')[-1]
l = getLogger(__name__)

p = pl.Plugin(
    name,
    require_version_min=(5, 0, 0),
    require_version_max=(6, 0, 0)
)

def init():
    try:
        # load static files
        with open(get_path(f'plugins/{name}/mplayer.css'), 'r', encoding='utf-8') as f:
            m_css = f.read()
        with open(get_path(f'plugins/{name}/mplayer.js'), 'r', encoding='utf-8') as f:
            m_js = f.read()
        with open(get_path(f'plugins/{name}/mplayer.html'), 'r', encoding='utf-8') as f:
            m_html = f.read()
        with open(get_path(f'plugins/{name}/aplayer.js'), 'r', encoding='utf-8') as f:
            a_js = f.read()

        p.add_index_inject(f'''
{m_html}
<style>
{m_css}
</style>
<script>
{m_js}
</script>
<script>
{a_js}
</script>
'''[1:-1])

    except Exception as e:
        l.error(f'Cannot load mplayer asset: {e}')

p.init = init
