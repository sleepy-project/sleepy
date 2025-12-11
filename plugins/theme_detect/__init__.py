# coding: utf-8

from logging import getLogger

from pydantic import BaseModel
import flask

import plugin as pl

class ThemeDetectConfig(BaseModel):
    light: str = 'default'
    dark: str= 'dark'

l = getLogger(__name__)

p = pl.Plugin(
    name='theme_detect',
    require_version_min=(5, 0, 0),
    require_version_max=(6, 0, 0),
    config=ThemeDetectConfig
)

c: ThemeDetectConfig = p.config

@p.event_handler(pl.BeforeRequestHook)
def on_before_request(event: pl.BeforeRequestHook, request):
    '''
    方案 1 - 检测 prefers-color-scheme 媒体查询（需要客户端支持）
    '''
    # 如果已有 theme cookie，跳过
    if flask.request.cookies.get('sleepy-theme'):
        return

    color_scheme = flask.request.headers.get('Sec-CH-Prefers-Color-Scheme')

    if color_scheme:
        theme = c.dark if color_scheme == 'dark' else c.light
        flask.g.theme = theme

    return event


@p.index_inject()
def inject_theme_detect():
    '''
    方案 2 - 注入脚本，发送用户系统暗色模式偏好
    '''
    return '''
    <script>
    // 检测系统暗色模式并重定向
    if (!document.cookie.includes('sleepy-theme') && window.matchMedia) {
        const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        const theme = isDark ? '{dark}' : '{light}';
        document.cookie = `sleepy-theme=${theme}; path=/; SameSite=Lax`;
        if (window.location.search.indexOf('theme=') === -1) {
            window.location.reload();
        }
    }
    </script>
    ''' \
    .replace('{dark}', c.dark) \
    .replace('{light}', c.light)