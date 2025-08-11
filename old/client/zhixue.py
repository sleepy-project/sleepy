'''
zhixue.py
获取你的智学网成绩
by: @NiuFuyu855
基础依赖: 
 - os
 - requests
 - time (仅在自动更新模式下使用)
 - zhixuewang (https://github.com/anwenhu/zhixuewang-python)
     - Docs: https://zxdoc.risconn.com/
     - Adapted Version: 1.3.4
     * use command `pip install zhixuewang` to install
'''

'''
Todo List:
- [√] 支持智学网 Cookie 自动获取
- [√] 支持智学网 Cookie 手动设置
- [√] 支持智学网 Cookie 自动更新
- [√] 支持智学网选择自动更新和单次运行模式
'''

'''
更新日志:
- v1.0.0: 初始版本, 支持智学网 Cookie 自动获取和手动设置, 支持智学网 Cookie 自动更新, 支持智学网选择自动更新和单次运行模式
- v1.0.1: 适配了最新版本(1.3.4)zhixuewang库，修复了“ValueError: 在指定考试的情况下，应当指定学年”的逆天报错（这次库更新真的可有可无吧我觉得，真的太逆天了！），并修复了若干bug
'''

'''
⚠Warning
 * 目前仅支持智学网学生端, 暂不支持教师端
'''

# ----- Part: Import
import os
import requests
from zhixuewang.account import login_cookie

# ----- Part: Config
# --- config start
MODE: str = "auto" # 运行模式, auto: 自动更新模式, single: 单次运行模式
USERNAME: str = "" # 智学网用户名，必填!!!
PASSWORD: str = "" # 智学网密码，必填!!!
LOGIN_URL: str = 'https://www.zhixue.com/login.html' # 智学网登录 API, 一般情况下无需修改
LOGIN_PAGE_URL: str = 'https://www.zhixue.com/login.html' # 登录页面 URL, 一般情况下无需修改
TLSYSSESSIONID: str = "" # tlsysSessionId, 需自行浏览器Ctrl+Shift+I获取开发者工具获取, 必填!!!
COOKIE:  str = "" # 智学网 Cookie, 留空则自动获取
EXAM_ID: str = "" # 考试ID, 留空则为获取最新考试成绩
ACADEMIC_YEAR: str = "" #考试学年（不要瞎填！），填EXAM_ID后可选填此项，不填默认最新学年！！可通过zxw.get_academic_year()获取所有学年
# --- config end

# ----- Part: Main
def get_zhixue_cookie(username, password, tlsysSessionId):
    """
    通过智学网 API 获取 Cookie

    :param username: 智学网用户名
    :param password: 智学网密码
    :param tlsysSessionId: tlsysSessionId, 需自行浏览器Ctrl+Shift+I获取开发者工具获取
    :return: 包含登录 Cookie 的字符串
    """
    # 创建一个会话对象
    session = requests.Session()

    # 设置请求头，模拟浏览器行为
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36 Edg/134.0.0.0'}
    session.headers.update(headers)

    # 访问登录页面，获取初始 Cookie
    session.get(LOGIN_PAGE_URL)

    # 登录所需的表单数据
    payload = {
        'username': username,
        'password': password
    }

    # 发送登录请求
    response = session.post(LOGIN_URL, data=payload)

    # 检查登录是否成功
    if response.status_code == 200:
        print("登录成功，已获取 Cookie")
        # 将 cookies 字典转换为字符串
        cookie_str = "; ".join([f"{name}={value}" for name, value in session.cookies.get_dict().items()])
        # 正确拼接 loginUserName 和 tlsysSessionId
        cookie_str = f"{cookie_str}; loginUserName={username}; tlsysSessionId={tlsysSessionId}"
        return cookie_str
    else:
        print(f"登录失败，状态码: {response.status_code}")
        return None

def get_full_score():
    '''
    获取智学网总分

    :param EXAM_ID: 考试ID, 留空则为获取最新考试成绩
    :return: full_score: 智学网总分
    '''
    if not EXAM_ID:
        subjects = zxw.get_subjects()
    else:
        subjects = zxw.get_subjects(EXAM_ID)
    
    # 初始化 full_score 变量
    full_score = 0
    # 遍历 subjects 列表，累加 standard_score
    for subject in subjects:
        full_score += subject.standard_score
    
    return full_score

def get_mark(EXAM_ID, ACADEMIC_YEAR):
    '''
    获取智学网成绩
    并返回成绩字符串于/static/zhixue.txt中

    :param EXAM_ID: 考试ID, 留空则为获取最新考试成绩
    :return: mark: 智学网成绩
    '''
    if not EXAM_ID:
        mark = zxw.get_self_mark() # 获取最新考试
    else:
        if not ACADEMIC_YEAR:
            ACADEMIC_YEAR = zxw._get_latest_valid_academic_year()
        mark = zxw.get_self_mark(EXAM_ID, True, ACADEMIC_YEAR) # EXAM_ID 为指定考试ID时，需要指定 AcademicYear (!Important! 库版本1.3.4时新增)
    '''
    Example:
    XXX-扬州市第一中学2024-2025学年第二学期 3月教学质量调研评估 高二                                                              
    语文: 84.0 (班级第23名)                                                                                                   
    数学: 92.0 (班级第14名)
    英语: 99.5 (班级第11名)
    物理: 64.0 (班级第7名)
    化学: 46.0 (班级第14名)
    地理: 72.0 (班级第6名)
    总分: 457.5
    '''

    # 将 mark 转换为字符串
    mark_str = str(mark)
    # 提取多行文本中包含 - 的行中 - 后的内容，并保留无 - 的行原样
    processed_lines = []
    for line in mark_str.splitlines():
        if '-' in line:
            # 分割第一个 "-" 并提取后半部分，清理首尾空格
            _, content = line.split('-', 1)
            processed_lines.append(content.strip())
        else:
            # 无 "-" 的行原样保留
            processed_lines.append(line)
    # 合并结果
    marks = '\n'.join(processed_lines)
    '''
    Example:
    扬州市第一中学2024-2025学年第二学期 3月教学质量调研评估 高二                                                              
    语文: 84.0 (班级第23名)                                                                                                   
    数学: 92.0 (班级第14名)
    英语: 99.5 (班级第11名)
    物理: 64.0 (班级第7名)
    化学: 46.0 (班级第14名)
    地理: 72.0 (班级第6名)
    总分: 457.5
    '''

    # 如果"总分"不在获取的成绩中, 则将多行文本marks除了第一行的其余行":"后的成绩加起来作总分并添加到最后一行
    if "总分" not in marks:
        lines = marks.splitlines()
        total_score = 0
        for line in lines[1:]:  # 跳过第一行
            parts = line.split(":")
            if len(parts) > 1:
                try:
                    score = float(parts[1].split("(")[0].strip())
                    total_score += score
                except ValueError:
                    continue
        marks = marks + f"\n总分: {total_score}"
    '''
    Example:
    3.10高二英语周练（二）
    英语: 85.5
    总分: 85.5
    '''

    # 在最后一行添加"满分"
    full_score = get_full_score()
    marks = marks + f"\n满分: {full_score}"
    '''
    Example:
    3.10高二英语周练（二）
    英语: 85.5
    总分: 85.5
    满分: 110.0
    '''

    # 目标文件夹路径（如果不存在会自动创建）
    save_dir = "./static"
    os.makedirs(save_dir, exist_ok=True)  # 确保文件夹存在
    file_path = os.path.join(save_dir, "zhixue.txt")  # 构建完整的文件路径
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(marks)  # 写入文件
    except FileNotFoundError:
        print("The specified directory does not exist.")
    except PermissionError:
        print("You do not have permission to write to the file.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    if COOKIE == "":  # 如果没有设置 COOKIE 则自动获取
        COOKIE = get_zhixue_cookie(USERNAME, PASSWORD, TLSYSSESSIONID)
    # 将 cookie 字符串转换为字典
    cookies = dict(item.split("=") for item in COOKIE.split("; "))
    zxw = login_cookie(cookies)

    if MODE == "auto":  # 自动更新模式
        import time # 引入 time 模块, 不是必用就在用的时候导啦~
        # 初始化时间计数器
        cookie_update_time = 0
        while True:
            '''
            每 30 分钟更新一次 成绩
            每 60 分钟更新一次 Cookie
            '''
            # 检查是否需要更新 Cookie
            if cookie_update_time % 2 == 0 and cookie_update_time != 0:
                COOKIE = get_zhixue_cookie(USERNAME, PASSWORD, TLSYSSESSIONID)
                cookies = dict(item.split("=") for item in COOKIE.split("; "))
                zxw = login_cookie(cookies)
                print("Cookie 已更新")

            get_mark(EXAM_ID, ACADEMIC_YEAR)  # 获取成绩 并写入文件
            print("成绩已更新")
            # 等待 30 分钟
            time.sleep(30 * 60)
            cookie_update_time += 1

    elif MODE == "single":  # 单次运行模式
        get_mark(EXAM_ID, ACADEMIC_YEAR)  # 获取成绩 并写入文件
        print("Done!")

    else:
        print("Invalid MODE!")
