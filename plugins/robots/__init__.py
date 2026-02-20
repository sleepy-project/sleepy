# coding: utf-8

from fnmatch import fnmatch
from logging import getLogger

from pydantic import BaseModel
from flask import Response, request as flask_request

import plugin as pl


class _RobotsTextConfig(BaseModel):
    user_agent: str = '*'
    allow: list[str] | str = []
    disallow: list[str] | str = []
    crawl_delay: float | None = None


class RobotsConfig(BaseModel):
    robots_txt: list[_RobotsTextConfig] | str = []
    x_robots_rules: dict[str, str] = {}
    sitemaps: list[str] = []


p = pl.Plugin(
    __name__,
    require_version_min=(5, 0, 0),
    require_version_max=(6, 0, 0),
    config=RobotsConfig
)
c: RobotsConfig = p.config
l = getLogger(__name__)


def header_handler(event: pl.AfterRequestHook):
    if not flask_request:
        l.warning(f'No request argument in this AfterRequestHook event')
        return event

    for k, v in c.x_robots_rules.items():
        if fnmatch(flask_request.path, k):
            event.response.headers.setdefault('X-Robots-Tag', v)
            l.debug(f'Matched {k} -> {v}')
            return event

    l.debug('Didn\'t match any X-Robots-Tag rule.')
    return event


def txt_handler():
    return Response(robots_txt, 200, {'Content-Type': 'text/plain; charset=utf-8'})


def init():
    global robots_txt
    # generate robots.txt
    if isinstance(c.robots_txt, list):
        lines = []
        for r in c.robots_txt:
            allow = r.allow if isinstance(r.allow, list) else [r.allow]
            disallow = r.disallow if isinstance(r.disallow, list) else [r.disallow]

            lines.append(f'User-agent: {r.user_agent}')
            for a in allow:
                lines.append(f'Allow: {a}')
            for d in disallow:
                lines.append(f'Disallow: {d}')
            if r.crawl_delay:
                lines.append(f'Crawl-Delay: {r.crawl_delay}')
            lines.append('')

        for s in c.sitemaps:
            lines.append(f'Sitemap: {s}')

        robots_txt = '\n'.join(lines)

    else:
        robots_txt = c.robots_txt

    # add handler if needed
    if robots_txt:
        p.add_global_route(txt_handler, '/robots.txt')
        l.debug(f'registered global route')

    if c.x_robots_rules:
        p.register_event(pl.AfterRequestHook, header_handler)
        l.debug(f'registered AfterRequestHook event handler')


p.init = init
