# coding: utf-8

from logging import getLogger

from pydantic import BaseModel

import plugin as pl

l = getLogger(__name__)


class SteamConfig(BaseModel):
    account_id: int = 76561199733292625
    vanity_id: str | None = 'bbdqz'
    app_id: int | None = 1144400
    lang: str | None = 'schinese'
    iframe_height: int = 300
    base_url: str = 'https://miniprofile.siiway.top'

p = pl.Plugin(
    __name__,
    require_version_min=(5, 0, 0),
    require_version_max=(6, 0, 0),
    config=SteamConfig
)

l.debug(p.config)
c: SteamConfig = p.config

def init():
    kv = [f'accountId={c.account_id}']
    if c.vanity_id:
        kv.append('interactive=true')
        kv.append(f'vanityId={c.vanity_id}')
    if c.app_id:
        kv.append(f'appId={c.app_id}')
    if c.lang:
        kv.append(f'lang={c.lang}')
    

    params = '&'.join(kv)

    p.add_index_card('steam', f'''
<h3><b>Steam Status</b></h3>
<div style="display: flex; justify-content: center; align-items: center; width: 100%;">
    <iframe
        src="{c.base_url}/?{params}"
        style="border: none; width: 100%; max-width: 350px; height: {c.iframe_height}px; transition: height 0.3s ease; display: block;"
        name="steam-iframe"
        scrolling="no"
        frameborder="0"
        allowfullscreen>
    </iframe>
</div>
'''[1:-1])

    p.add_index_inject('''
<style>
/* Steam Card */
#steam {
  text-align: center;
  overflow: visible !important;
}

#steam > div {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 100%;
  height: 100%;
}

#steam iframe {
  display: block !important;
  vertical-align: top !important;
}
</style>
'''[1:-1])

p.init = init
