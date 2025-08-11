# coding: utf-8

import requests
from time import sleep

# --- config start
SERVER = 'https://sleepy.example.com'  # 部署地址，末尾不带 `/`
SECRET = '11111111-4444-5555-1111-444444444444'
PROXY: str = ''  # 代理地址 (<http/socks5>://host:port), 设置为空字符串禁用
# --- config end

# --- modifies

_print_ = print


def print(*args, **kwargs):
    '''
    modified `print()` function

    replaced secret to `[SECRET]`

    original: `_print_()`
    '''
    new_args = []
    for i in args:
        new_args.append(str(i).replace(str(SECRET), '[SECRET]'))
    _print_(*new_args, **kwargs)


def get(url: str, **kwargs):
    '''
    modified `requests.get()`
    '''
    retries = 5
    while True:
        try:
            if PROXY:
                return requests.get(
                    url=url,
                    proxies={
                        'all': PROXY
                    },
                    **kwargs
                )
            else:
                return requests.get(
                    url=url,
                    **kwargs
                )
        except Exception as e:
            retries -= 1
            if retries:
                print(f'ing - Request error: {e}, retrying... ({retries} left)')
                sleep(0.5)
                continue
            else:
                raise


def post(url: str, Json: dict, **kwargs):
    '''
    modified `requests.post()`
    '''
    retries = 5
    while True:
        try:
            if PROXY:
                return requests.post(
                    url=url,
                    json=Json,
                    proxies={
                        'all': PROXY
                    },
                    headers={
                        'Content-Type': 'application/json'
                    },
                    **kwargs
                )
            else:
                return requests.post(
                    url=url,
                    json=Json,
                    headers={
                        'Content-Type': 'application/json'
                    },
                    **kwargs
                )
        except Exception as e:
            retries -= 1
            if retries:
                print(f'ing - Request error: {e}, retrying... ({retries} left)')
                sleep(0.5)
                continue
            else:
                raise

# --- functions

# - public


def query():
    '''
    /query using GET
    - check status now
    '''
    resp = get(f'{SERVER}/query')
    print(f'[/query] Response: {resp.status_code} - {resp.text}')


def status_list():
    '''
    /status_list using GET
    - see status list
    '''
    resp = get(f'{SERVER}/status_list')
    print(f'[/status_list] Response: {resp.status_code} - {resp.text}')


def metrics():
    '''
    /metrics using GET
    - see metrics data
    '''
    resp = get(f'{SERVER}/metrics')
    print(f'[/metrics] Response: {resp.status_code} - {resp.text}')

# - status


def status(stat: int):
    '''
    /set using GET
    - set status manually
    '''
    resp = get(f'{SERVER}/set?secret={SECRET}&status={stat}')
    print(f'[/set] Response: {resp.status_code} - {resp.json()}')

# - device


def device_set(id: str, show_name: str, status: str, using: bool = True):
    '''
    /api/device/set using POST
    - set device status
    '''
    resp = post(f'{SERVER}/api/device/set', {
        'secret': SECRET,
        'id': id,
        'show_name': show_name,
        'using': using,
        'status': status
    })
    print(f'[/api/device/set] Response: {resp.status_code} - {resp.json()}')


def device_remove(id: str):
    '''
    /device/remove using GET
    - remove a device with it's status
    '''
    resp = get(f'{SERVER}/device/remove?secret={SECRET}&id={id}')
    print(f'[/device/remove] Response: {resp.status_code} - {resp.json()}')


def device_clear():
    '''
    /device/clear using GET
    - remove **all** devices with their statuses
    '''
    resp = get(f'{SERVER}/device/clear?secret={SECRET}')
    print(f'[/device/clear] Response: {resp.status_code} - {resp.json()}')


def private_mode(private: bool):
    '''
    /device/private using GET
    - open / close private mode *(don't show device status)*
    '''
    resp = get(f'{SERVER}/device/private?secret={SECRET}&private={private}')
    print(f'[/device/private] Response: {resp.status_code} - {resp.json()}')

# - custom


def left(
    num: int = 0,
    id: str = 'homework-left',
    show_name: str = 'Homework left'
):
    '''
    set how much homework left
    '''
    if num:
        device_set(
            id=id,
            show_name=show_name,
            status=f'{num}'
        )
    else:
        device_remove(id=id)


def writing(
    name: str = '',
    id: str = 'homework-writing',
    show_name: str = 'Homework writing'
):
    '''
    set what homework you're writing
    '''
    if name:
        device_set(
            id=id,
            show_name=show_name,
            status=name
        )
    else:
        device_remove(id=id)


# --- main loop

if __name__ == '__main__':
    try:
        while True:
            i = input('in  < ')
            try:
                o = eval(i)
                if not o is None:
                    print(f'out > {o}')
            except Exception as e:
                print(f'err - {e}')
    except KeyboardInterrupt:
        print('Exiting: ^C')
    except Exception as e:
        print(f'Exiting: {e}')
    exit()
