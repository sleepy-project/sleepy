#!/usr/bin/python3
# coding:utf-8

'''
一个 python 命令行示例 (多服务版，也就是旧的 cmd_console.py)
依赖: requests
by @wyf9
'''

import requests
import json
global server

# --- config start
# 密钥
SECRET = '11451419-1981-0114-5141-919810114514'
# 服务列表, 末尾不加 `/`
SERVER_LIST = ['https://sleepy.wyf9.top',
               'http://114.51.41.91:9010',
               'http://127.0.0.1:9010']
# 请求重试次数
RETRY = 3
# --- config end


def get(url):
    for t1 in range(RETRY):
        t = t1 + 1
        try:
            x = requests.get(url)
            return x.text
        except:
            print(f'Retrying... {t}/{RETRY}')
            if t >= RETRY:
                print('Max retry limit!')
                raise
            continue


def loadjson(url):
    raw = get(url)
    try:
        return json.loads(raw)
    except json.decoder.JSONDecodeError:
        print('Error decoding json!\nRaw data:\n"""')
        print(raw)
        print('"""')
        raise
    except:
        print('Error:')
        raise


def main():
    print('\n---\nSelect Server:')
    serverlst_show = ''
    for n1 in range(len(SERVER_LIST)):
        n = n1 + 1
        serverlst_show += f'    {n}. {SERVER_LIST[n1]}\n'
    print(f'''
    0. Quit
{serverlst_show}''')
    while True:
        try:
            inp = int(input('> '))
            if inp == 0:
                return 0
            else:
                server = SERVER_LIST[inp - 1]
                print(f'Selected server: {server}')
                break
        except:
            print('invaild input')

    print('\n---\nStatus now:')
    stnow = loadjson(f'{server}/query')
    try:
        print(f'success: [{stnow["success"]}], status: [{stnow["status"]}], info_name: [{stnow["info"]["name"]}], info_desc: [{stnow["info"]["desc"]}], info_color: [{stnow["info"]["color"]}]')
    except KeyError:
        print(f'RawData: {stnow}')

    print('\n---\nSelect status:')

    stlst = loadjson(f'{server}/status_list').get('status_list', [])
    for n in stlst:
        print(f'{n["id"]} - {n["name"]} - {n["desc"]}')

    st = input('\n> ')
    '''
    print(get())
    {
        "success": true, 
        "code": "OK", 
        "set_to": 0
    }
    '''
    ret = loadjson(f'{server}/set?secret={SECRET}&status={st}')
    try:
        print(
            f'success: [{ret["success"]}], code: [{ret["code"]}], set_to: [{ret["set_to"]}]')
    except:
        print(f'RawData: {ret}')
    return 0


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f'Main ERROR! {e}')
    input('\n---\nPress Enter to exit.')
