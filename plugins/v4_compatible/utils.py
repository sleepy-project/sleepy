# coding: utf-8

from functools import wraps
from logging import getLogger

import flask

l = getLogger(__name__)

def require_secret():
    '''
    (装饰器) require_secret, 用于指定函数需要 secret 鉴权
    - v4 Legacy
    '''

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            # 1. body
            body: dict = flask.request.get_json(silent=True) or {}
            if body and body.get('secret') == flask.g.secret:
                l.debug('[Auth] Verify secret Success from Body')
                return view_func(*args, **kwargs)

            # 2. param
            elif flask.request.args.get('secret') == flask.g.secret:
                l.debug('[Auth] Verify secret Success from Param')
                return view_func(*args, **kwargs)

            # 3. header (Sleepy-Secret)
            elif flask.request.headers.get('Sleepy-Secret') == flask.g.secret:
                l.debug('[Auth] Verify secret Success from Header (Sleepy-Secret)')
                return view_func(*args, **kwargs)

            # 4. header (Authorization)
            auth_header = flask.request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer ') and auth_header[7:] == flask.g.secret:
                l.debug('[Auth] Verify secret Success from Header (Authorization)')
                return view_func(*args, **kwargs)

            # 5. cookie (sleepy-secret)
            elif flask.request.cookies.get('sleepy-secret') == flask.g.secret:
                l.debug('[Auth] Verify secret Success from Cookie (sleepy-secret)')
                return view_func(*args, **kwargs)

            # -1. no any secret
            else:
                l.debug('[Auth] Verify secret Failed')
                raise APIUnsuccessful(401, 'Wrong Secret')
        return wrapper
    return decorator


class APIUnsuccessful(Exception):
    '''
    api 接口调用失败异常
    - v4 Legacy
    '''

    def __init__(self, code: int = 500, message: str | None = None):
        '''
        创建 APIUnsuccessful 异常
        - v4 Legacy

        :param code: HTTP 状态码
        :param message: 错误信息
        '''
        self.code = code
        self.message = message

    def __str__(self):
        return f'{self.code} ({self.message})'
