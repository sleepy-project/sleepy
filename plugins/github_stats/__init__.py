from urllib.parse import urlencode

from pydantic import BaseModel

from plugin import Plugin


class _StatsConfig(BaseModel):
    '''
    GitHub Stats - /api
    '''
    _api_path: str = ''
    enabled: bool = True
    params: dict[str, str | int | bool | list[str]] = {
        'username': 'wyf9',
        'count_private': True,
        'show_icons': True,
        'theme': 'solarized-dark',
        'cache_seconds': 3600,
        'hide_border': True,
        'show': ['reviews', 'discussions_started', 'discussions_answered', 'prs_merged', 'prs_merged_percentage']
    }
    raw_params: str | None = None
    alt: str = 'GitHub Stats'


class _TopLangsConfig(BaseModel):
    '''
    GitHub Top Langs - /api/top-langs
    '''
    _api_path = '/top-langs'
    enabled: bool = True
    params: dict[str, str | int | bool | list[str]] = {
        'username': 'wyf9',
        'count_private': True,
        'show_icons': True,
        'theme': 'solarized-dark',
        'cache_seconds': 3600,
        'hide_border': True
    }
    raw_params: str | None = None
    alt: str = 'Top Langs'


class _WakatimeConfig(BaseModel):
    '''
    Wakatime - /api/wakatime
    '''
    _api_path = '/wakatime'
    enabled: bool = True
    params: dict[str, str | int | bool | list[str]] = {
        'username': '11095',
        'api_domain': 'hackatime.hackclub.com',
        'custom_title': 'Hackatime Stats (last year)',
        'layout': 'compact',
        'cache_seconds': 3600,
        'langs_count': 8,
        'theme': 'solarized-dark',
        'hide_border': True
    }
    raw_params: str | None = None
    alt: str = 'Wakatime Stats'


class GitHubStatsConfig(BaseModel):
    '''
    GitHub Readme Stats API 地址 (一般以 /api 结尾, 不带 /)
    - 自部署: https://github.com/anuraghazra/github-readme-stats
    '''
    base_url: str = 'https://gh-readme-stats.siiway.top/api'

    stats: _StatsConfig = _StatsConfig()
    top_langs: _TopLangsConfig = _TopLangsConfig()
    wakatime: _WakatimeConfig = _WakatimeConfig()

pl = Plugin(
    __name__,
    require_version_min=(5, 0, 0),
    require_version_max=(6, 0, 0),
    config=GitHubStatsConfig
)

c: GitHubStatsConfig = pl.config

def init():
    parts = []
    for pn in ('stats', 'top_langs', 'wakatime'):
        p = getattr(c, pn)
        if p.enabled:
            if p.raw_params:
                params = p.raw_params
            else:
                params = urlencode(p.params)
            parts.append(f'<img src="{c.base_url}{p._api_path}?{params}" alt="{p.alt}" style="display:inline-block; margin-right:10px; vertical-align:top;">')

    if parts:
        content = f'<h3 style="text-align:center;">GitHub Stats</h3><div style="text-align:center;">' + ''.join(parts) + '</div>'
        pl.add_index_card('github-stats', content)

pl.init = init