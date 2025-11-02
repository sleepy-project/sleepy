# coding: utf-8

class APIUnsuccessful(Exception):
    '''
    api 接口调用失败异常
    '''
    codes = {
        # 4xx - 客户端错误
        400: 'Bad Request',
        401: 'Unauthorized',
        402: 'Payment Required',
        403: 'Forbidden',
        404: 'Not Found',
        405: 'Method Not Allowed',
        406: 'Not Acceptable',
        407: 'Proxy Authentication Required',
        408: 'Request Timeout',
        409: 'Conflict',
        410: 'Gone',
        411: 'Length Required',
        412: 'Precondition Failed',
        413: 'Payload Too Large',
        414: 'URI Too Long',
        415: 'Unsupported Media Type',
        416: 'Range Not Satisfiable',
        417: 'Expectation Failed',
        418: "I'm a Teapot",  # RFC 2324
        422: 'Unprocessable Entity',  # WebDAV
        423: 'Locked',  # WebDAV
        424: 'Failed Dependency',  # WebDAV
        425: 'Too Early',  # RFC 8470
        426: 'Upgrade Required',
        428: 'Precondition Required',
        429: 'Too Many Requests',
        431: 'Request Header Fields Too Large',
        451: 'Unavailable For Legal Reasons',  # RFC 7725

        # 5xx - 服务器错误
        500: 'Internal Server Error',
        501: 'Not Implemented',
        502: 'Bad Gateway',
        503: 'Service Unavailable',
        504: 'Gateway Timeout',
        505: 'HTTP Version Not Supported',
        506: 'Variant Also Negotiates',  # RFC 2295
        507: 'Insufficient Storage',  # WebDAV
        508: 'Loop Detected',  # WebDAV
        510: 'Not Extended',
        511: 'Network Authentication Required',
    }
    '''
    http code 对应表, 由 DeepSeek 扩充
    '''

    def __init__(self, code: int = 500, detail: str | None = None, headers: dict[str, str] = {}):
        '''
        创建 APIUnsuccessful 异常

        :param code: HTTP 状态码\n
            常用状态码:
            - 400 - 错误的请求 (Bad Request)
            - 401 - 未授权 (Unauthorized)
            - 403 - 禁止访问 (Forbidden)
            - 404 - 未找到 (Not Found)
            - 405 - 方法被禁止 (Method Not Allowed)
            - 429 - 请求过多 (Too Many Requests)
            - 500 - 服务器内部错误 (Internal Server Error)
            - 503 - 服务不可用 (Service Unavailable)

            *完整列表参考 `codes`*

        :param detail: 错误详细信息
        :param headers: 额外的 HTTP 头
        '''
        self.code = code
        self.message = self.codes.get(code, f'HTTP Error {code}')
        self.detail = detail
        self.headers = headers

    def __str__(self):
        return f'{self.code} {self.message} ({self.detail})'
