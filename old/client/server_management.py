#!/usr/bin/python3
# coding:utf-8

'''
一个 python 服务器设备，个人状态管理器
依赖: requests, argparse(传参需选), prettytable(可选)
by @Claude 3.7 Sonnet Thinking
因为太过抽象, 停止维护此客户端 -- wyf9
'''
#! SECRET出错不会报错，需要鉴权的操作都会失败，但是不显示失败
# * 传参用法在最后面

import requests
import json
import sys
import argparse
import shlex
from typing import Dict, List, Union, Any, Optional

# 尝试导入 PrettyTable，如果不可用则提供简易替代
try:
    from prettytable import PrettyTable  # type: ignore - 编辑器忽略未安装警告
    PRETTYTABLE_AVAILABLE = True
except ImportError:
    PRETTYTABLE_AVAILABLE = False
    print("警告: PrettyTable 库未安装，将使用简易格式化输出。")
    print("您可以通过 'pip install prettytable' 安装该库以获得更好的显示效果。")

# --- config start
# 密钥
SECRET = ''
# 服务地址, 末尾不加 `/`
SERVER = 'http://127.0.0.1:9010'
# 请求重试次数
RETRY = 3
# 是否显示原始 JSON 响应
SHOW_RAW_JSON = False
# --- config end


class SleepyManager:
    """Sleepy API 管理类，封装了所有 API 调用"""

    def __init__(self, server: str, secret: str, retry: int = 3):
        """初始化 SleepyManager"""
        self.server = server.rstrip('/')
        self.secret = secret
        self.retry = retry
        self._cached_devices = None
        self._cached_status_list = None

    def _request(self, method: str, path: str, params: Dict = None, json_data: Dict = None) -> Dict:
        """发送请求并处理重试逻辑"""
        url = f"{self.server}/{path.lstrip('/')}"

        # 如果是 GET 请求且没有 params，初始化一个空字典
        if method.upper() == 'GET' and params is None:
            params = {}

        # 如果需要身份验证且未在参数中指定密钥
        if params is not None and 'secret' not in params:
            params['secret'] = self.secret

        # 如果是 POST 请求且需要 JSON 数据
        if method.upper() == 'POST' and json_data is not None and 'secret' not in json_data:
            json_data['secret'] = self.secret

        for attempt in range(self.retry):
            try:
                response = requests.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data,
                    timeout=10
                )
                response.raise_for_status()
                return response.json()
            except requests.RequestException as e:
                if attempt == self.retry - 1:
                    print(f"请求失败 ({attempt + 1}/{self.retry}): {e}")
                    raise
                print(f"请求失败，正在重试 ({attempt + 1}/{self.retry}): {e}")

    # ------ Read-only APIs ------

    def query(self) -> Dict:
        """获取当前状态"""
        result = self._request('GET', 'api/status/query')
        self._cached_devices = result.get('device', {})
        return result

    def status_list(self) -> List[Dict]:
        """获取可用状态列表"""
        result = self._request('GET', 'api/status/list')
        self._cached_status_list = result.get('status_list', [])
        return result

    def get_cached_devices(self) -> Dict:
        """获取缓存的设备列表，如果没有则先查询"""
        if self._cached_devices is None:
            self.query()
        return self._cached_devices

    def get_cached_status_list(self) -> List[Dict]:
        """获取缓存的状态列表，如果没有则先查询"""
        if self._cached_status_list is None:
            self.status_list()
        return self._cached_status_list

    def metrics(self) -> Dict:
        """获取统计信息"""
        return self._request('GET', 'api/metrics')

    # ------ Status APIs ------

    def set_status(self, status: int) -> Dict:
        """设置当前状态"""
        return self._request('GET', 'api/status/set', params={'status': status})

    # ------ Device APIs ------

    def device_set(self, id: str, show_name: str, using: bool, status: str) -> Dict:
        """设置单个设备的状态"""
        data = {
            'id': id,
            'show_name': show_name,
            'using': using,
            'status': status
        }
        result = self._request('POST', 'api/device/set', json_data=data)
        # 更新设备缓存
        if self._cached_devices is not None:
            self._cached_devices[id] = {
                'show_name': show_name,
                'using': using,
                'status': status
            }
        return result

    def device_remove(self, device_id: str) -> Dict:
        """移除单个设备的状态"""
        result = self._request('GET', 'api/device/remove', params={'id': device_id})
        # 更新设备缓存
        if self._cached_devices is not None and device_id in self._cached_devices:
            del self._cached_devices[device_id]
        return result

    def device_clear(self) -> Dict:
        """清除所有设备的状态"""
        result = self._request('GET', 'api/device/clear')
        # 清空设备缓存
        self._cached_devices = {}
        return result

    def device_private_mode(self, is_private: bool) -> Dict:
        """设置隐私模式"""
        return self._request('GET', 'api/device/private', params={'private': str(is_private).lower()})


class SimplePrinter:
    """用于格式化输出结果的类，支持表格和标准输出"""

    @staticmethod
    def print_table(data: List[Dict], headers: Dict[str, str]) -> None:
        """将数据以表格形式输出

        Args:
            data: 包含字典的列表
            headers: 字段名到显示标题的映射
        """
        if not data:
            print("没有数据可显示")
            return

        if PRETTYTABLE_AVAILABLE:
            table = PrettyTable()
            # 添加表头
            for field, title in headers.items():
                table.add_column(title, [])

            # 添加数据行
            for row in data:
                table.add_row([row.get(field, "") for field in headers.keys()])

            print(table)
        else:
            # 简易表格显示
            # 打印表头
            header_line = " | ".join(headers.values())
            print(header_line)
            print("-" * len(header_line))

            # 打印数据行
            for row in data:
                values = []
                for field in headers.keys():
                    values.append(str(row.get(field, "")))
                print(" | ".join(values))

    @staticmethod
    def format_device_status(device_data: Dict) -> List[Dict]:
        """将设备数据格式化为表格数据"""
        result = []
        for device_id, info in device_data.items():
            row = {
                'id': device_id,
                'show_name': info.get('show_name', ''),
                'using': "使用中" if info.get('using', False) else "空闲",
                'status': info.get('status', '')
            }
            result.append(row)
        return result

    @staticmethod
    def format_status_list(status_list: List[Dict]) -> List[Dict]:
        """将状态列表格式化为表格数据"""
        result = []
        for status in status_list:
            row = {
                'id': status.get('id', ''),
                'name': status.get('name', ''),
                'description': status.get('description', '')
            }
            result.append(row)
        return result

    @staticmethod
    def print_status(status: Optional[Dict]) -> None:
        """打印当前状态信息"""
        if status is None:
            print("无法获取状态信息")
            return

        print(f"\n当前状态: {status.get('name', '未知')} (ID: {status.get('id', '未知')})")
        print(f"描述: {status.get('description', '无描述')}")
        print(f"开始时间: {status.get('start_time', '未知')}")
        print(f"是否隐私模式: {'是' if status.get('is_private', False) else '否'}")

    @staticmethod
    def print_devices(devices: Dict) -> None:
        """打印设备信息"""
        if not devices:
            print("目前没有设备信息")
            return

        device_list = SimplePrinter.format_device_status(devices)
        headers = {
            'id': '设备ID',
            'show_name': '显示名称',
            'using': '是否正在使用',
            'status': '设备状态文本'
        }
        SimplePrinter.print_table(device_list, headers)

    @staticmethod
    def print_status_list(status_list: List[Dict]) -> None:
        """打印可用状态列表"""
        if not status_list:
            print("未找到可用状态")
            return

        formatted_list = SimplePrinter.format_status_list(status_list)
        headers = {
            'id': '状态ID',
            'name': '状态名称',
            'description': '说明'
        }
        SimplePrinter.print_table(formatted_list, headers)

    @staticmethod
    def print_metrics(metrics: Dict) -> None:
        """打印统计信息"""
        if not metrics:
            print("无法获取统计信息")
            return

        print("\n统计信息:")
        print(f"总运行时间: {metrics.get('uptime', '未知')}")
        print(f"API总调用次数: {metrics.get('total_api_calls', 0)}")

        # 状态统计
        status_stats = metrics.get('status_stats', {})
        if status_stats:
            print("\n状态使用统计:")
            for status_id, info in status_stats.items():
                print(f"  - {info.get('name', status_id)}: {info.get('time', '0')} ({info.get('percentage', '0%')})")

    @staticmethod
    def print_api_result(result: Dict, title: str = "操作结果") -> None:
        """打印API调用结果"""
        print(f"\n{title}:")
        if SHOW_RAW_JSON:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            if "msg" in result:
                print(f"消息: {result.get('msg', '无消息')}")
            if "device" in result:
                print("\n设备信息:")
                SimplePrinter.print_devices(result["device"])
            if "status" in result and isinstance(result["status"], dict):
                SimplePrinter.print_status(result["status"])
            if "status_list" in result:
                print("\n可用状态列表:")
                SimplePrinter.print_status_list(result["status_list"])
            if "metrics" in result:
                SimplePrinter.print_metrics(result["metrics"])


class SleepyManagerCLI:
    """命令行交互界面类"""

    def __init__(self, manager: SleepyManager = None):
        """初始化CLI界面"""
        if manager is None:
            manager = SleepyManager(SERVER, SECRET, RETRY)
        self.manager = manager

        # 预加载可用状态和设备信息以用于命令提示
        try:
            self.manager.query()
            self.manager.status_list()
        except:
            pass


class SleepyManagerCLI:
    """命令行交互界面类"""

    def __init__(self, manager: SleepyManager = None):
        """初始化CLI界面"""
        if manager is None:
            manager = SleepyManager(SERVER, SECRET, RETRY)
        self.manager = manager

        # 预加载可用状态和设备信息以用于命令提示
        try:
            self.manager.query()
            self.manager.status_list()
        except:
            pass

        # 命令处理映射
        self.commands = {
            # 基本信息查询命令
            'query': self.cmd_query,
            'status_list': self.cmd_status_list,
            'metrics': self.cmd_metrics,

            # 状态设置命令
            'set': self.cmd_set_status,

            # 设备管理命令
            'device_set': self.cmd_device_set,
            'device_remove': self.cmd_device_remove,
            'device_clear': self.cmd_device_clear,
            'device_private_mode': self.cmd_device_private_mode,

            # 帮助
            'help': self.cmd_help,
            '?': self.cmd_help,
        }

    def show_status_options(self) -> None:
        """显示可用状态选项"""
        print("\n可用状态列表：")
        status_list = self.manager.get_cached_status_list()
        SimplePrinter.print_status_list(status_list)

    def show_device_options(self) -> None:
        """显示当前设备列表"""
        print("\n当前设备列表：")
        devices = self.manager.get_cached_devices()
        SimplePrinter.print_devices(devices)

    # ------ 命令处理函数 ------

    def cmd_query(self, args: List[str]) -> None:
        """查询当前状态"""
        if args and args[0] in ['-h', '--help']:
            print("用法: query")
            print("功能: 查询当前状态信息，包括状态、设备等")
            return

        try:
            result = self.manager.query()
            SimplePrinter.print_api_result(result, "当前系统状态")
        except Exception as e:
            print(f"查询失败: {e}")

    def cmd_status_list(self, args: List[str]) -> None:
        """获取可用状态列表"""
        if args and args[0] in ['-h', '--help']:
            print("用法: status_list")
            print("功能: 列出所有可用的状态选项")
            return

        try:
            result = self.manager.status_list()
            SimplePrinter.print_status_list(result)
        except Exception as e:
            print(f"获取状态列表失败: {e}")

    def cmd_metrics(self, args: List[str]) -> None:
        """获取统计信息"""
        if args and args[0] in ['-h', '--help']:
            print("用法: metrics")
            print("功能: 显示系统统计信息，包括运行时间和状态使用统计等")
            return

        try:
            result = self.manager.metrics()
            SimplePrinter.print_metrics(result)
        except Exception as e:
            print(f"获取统计信息失败: {e}")

    def cmd_set_status(self, args: List[str]) -> None:
        """设置当前状态"""
        if not args or args[0] in ['-h', '--help']:
            print("用法: set <状态ID>")
            print("功能: 设置当前状态")
            self.show_status_options()
            return

        try:
            status_id = int(args[0])
            result = self.manager.set_status(status_id)
            SimplePrinter.print_api_result(result, f"状态已设置为 ID: {status_id}")
        except ValueError:
            print("错误: 状态ID必须是数字")
            self.show_status_options()
        except Exception as e:
            print(f"设置状态失败: {e}")

    def cmd_device_set(self, args: List[str]) -> None:
        """设置设备状态"""
        if len(args) < 4 or args[0] in ['-h', '--help']:
            print("用法: device_set <设备ID> <显示名称> <是否使用中:true|false> <状态文本>")
            print("功能: 设置指定设备的状态信息")
            print("\n示例: device_set my_pc \"我的电脑\" true \"VS Code\"")

            # 显示当前设备列表以便参考
            if self.manager.get_cached_devices():
                print("\n当前设备列表供参考:")
                self.show_device_options()
            return

        try:
            device_id = args[0]
            show_name = args[1]
            using = args[2].lower() == 'true'
            status = args[3]

            result = self.manager.device_set(device_id, show_name, using, status)
            SimplePrinter.print_api_result(result, f"设备 {device_id} 状态已更新")
        except Exception as e:
            print(f"设置设备状态失败: {e}")

    def cmd_device_remove(self, args: List[str]) -> None:
        """移除设备"""
        if not args or args[0] in ['-h', '--help']:
            print("用法: device_remove <设备ID>")
            print("功能: 移除指定的设备")

            # 显示当前设备列表以便选择
            if self.manager.get_cached_devices():
                self.show_device_options()
            else:
                print("\n当前没有设备可移除")
            return

        try:
            device_id = args[0]
            result = self.manager.device_remove(device_id)
            SimplePrinter.print_api_result(result, f"设备 {device_id} 已移除")
        except Exception as e:
            print(f"移除设备失败: {e}")

    def cmd_device_clear(self, args: List[str]) -> None:
        """清除所有设备"""
        if args and args[0] in ['-h', '--help']:
            print("用法: device_clear")
            print("功能: 清除所有设备信息")
            return

        try:
            result = self.manager.device_clear()
            SimplePrinter.print_api_result(result, "所有设备已清除")
        except Exception as e:
            print(f"清除设备失败: {e}")

    def cmd_device_private_mode(self, args: List[str]) -> None:
        """设置隐私模式"""
        if not args or args[0] in ['-h', '--help']:
            print("用法: device_private_mode <true|false>")
            print("功能: 启用或禁用隐私模式")
            return

        try:
            is_private = args[0].lower() == 'true'
            result = self.manager.device_private_mode(is_private)
            mode_str = "启用" if is_private else "禁用"
            SimplePrinter.print_api_result(result, f"隐私模式已{mode_str}")
        except Exception as e:
            print(f"设置隐私模式失败: {e}")

    def cmd_help(self, args: List[str]) -> None:
        """显示帮助信息"""
        if args:
            # 显示特定命令的帮助
            cmd = args[0]
            if cmd in self.commands:
                # 调用对应命令的帮助
                self.commands[cmd](['-h'])
            else:
                print(f"未知命令: {cmd}")
            return

        print("\nSleepy管理器 命令帮助:")
        print("=====================")

        # 分类显示命令
        print("\n== 信息查询命令 ==")
        print("query              - 查询当前状态")
        print("status_list        - 列出所有可用状态")
        print("metrics           - 显示统计信息")

        print("\n== 状态设置命令 ==")
        print("set <状态ID>      - 设置当前状态")

        print("\n== 设备管理命令 ==")
        print("device_set <ID> <显示名称> <使用中> <状态信息>  - 设置设备状态")
        print("device_remove <ID>                       - 移除设备")
        print("device_clear                            - 清除所有设备")
        print("device_private_mode <true|false>        - 设置隐私模式")

        print("\n== 其他命令 ==")
        print("help              - 显示此帮助信息")
        print("help <命令>       - 显示指定命令的详细帮助")
        print("quit, exit        - 退出程序")

    # ------ 交互式命令行主循环 ------

    def run_interactive(self) -> None:
        """运行交互式命令行界面"""
        print("Sleepy 管理工具交互模式")
        print("输入 'help' 查看命令列表，输入 'exit' 或 'quit' 退出")

        while True:
            try:
                # 获取用户输入
                user_input = input("\n> ")

                # 处理退出命令
                if user_input.lower() in ['exit', 'quit']:
                    print("再见!")
                    break

                # 跳过空输入
                if not user_input.strip():
                    continue

                # 解析命令和参数
                parts = shlex.split(user_input)
                cmd = parts[0].lower()
                args = parts[1:] if len(parts) > 1 else []

                # 执行命令
                self.run_single_command(cmd, args)

            except KeyboardInterrupt:
                print("\n操作已中断")
                #! 控制台中断不会退出
                continue
            except Exception as e:
                print(f"错误: {e}")
                continue

    def run_single_command(self, cmd: str, args: List[str]) -> None:
        """执行单个命令"""
        if cmd in self.commands:
            self.commands[cmd](args)
        else:
            print(f"未知命令: {cmd}")
            print("输入 'help' 查看可用命令列表")

    # 运行单次命令（非交互式）
    def execute_command(self, cmd: str, args: List[str]) -> None:
        """执行单个命令并返回结果（用于非交互式模式）"""
        self.run_single_command(cmd, args)


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="Sleepy 管理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # 服务器和认证选项
    parser.add_argument("--server", "-s", default=SERVER,
                        help=f"服务器地址 (默认: {SERVER})")
    parser.add_argument("--secret", "-k", default=SECRET,
                        help=f"API密钥")
    parser.add_argument("--retry", "-r", type=int, default=RETRY,
                        help=f"API请求重试次数 (默认: {RETRY})")
    parser.add_argument("--raw-json", action="store_true",
                        help="显示原始JSON响应")

    # 运行模式
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("-i", "--interactive", action="store_true",
                            help="启动交互式命令行模式")
    mode_group.add_argument("-c", "--command",
                            help="执行单个命令并退出")

    # 解析参数
    args, unknown_args = parser.parse_known_args()

    # 处理 --command 后面的额外参数
    command_args = []
    if args.command:
        command_args = unknown_args

    return args, command_args


def main():
    """主函数"""
    # 解析命令行参数
    args, command_args = parse_arguments()

    # 更新全局配置
    global SERVER, SECRET, RETRY, SHOW_RAW_JSON
    if args.server:
        SERVER = args.server
    if args.secret:
        SECRET = args.secret
    if args.retry:
        RETRY = args.retry
    if args.raw_json:
        SHOW_RAW_JSON = True

    try:
        # 创建管理器实例
        manager = SleepyManager(SERVER, SECRET, RETRY)
        cli = SleepyManagerCLI(manager)

        # 根据参数决定运行模式
        if args.command:
            # 单命令模式
            cli.execute_command(args.command, command_args)
        else:
            # 交互式模式
            cli.run_interactive()

    except KeyboardInterrupt:
        print("\n操作已取消。")
        sys.exit(1)
    except Exception as e:
        print(f"发生错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
