import os
import re
import logging
import asyncio
import base64
from datetime import datetime

from flask import request, jsonify, send_from_directory
from werkzeug.datastructures import FileStorage
from pydantic import BaseModel

import utils as u
import plugin as pl
from plugin import Plugin

l = logging.getLogger(__name__)


def extract_filename(path):
    """跨平台提取文件名，处理 Windows 和 Unix 路径分隔符"""
    if not path:
        return ''
    path = path.replace('\\', '/')
    return path.split('/')[-1] if '/' in path else path


class ScreenUsageTimeConfig(BaseModel):
    top_apps: int = 5
    top_websites: int = 5

class ScreenUsageTimePlugin(Plugin):
    config: ScreenUsageTimeConfig

    def __init__(self):
        super().__init__(
            name=__name__,
            data={
                'app_usage': {},
                'website_usage': {},
                'last_updated': None
            },
            config=ScreenUsageTimeConfig,
            require_version_min=(5, 0, 0),
            require_version_max=(6, 0, 0)
        )

    def init(self):
        # 注册路由
        self.add_routes()
        # 确保目录存在
        self.ensure_directories()
        # 注册事件处理器
        self.register_event(pl.QueryAccessEvent, self.handle_query_access_event)
        # 注入前端 CSS 和 JavaScript 引用
        self.add_index_inject('<link rel="stylesheet" href="/plugin/screen_usage_time/static/screen_usage_time.css"><script src="/plugin/screen_usage_time/static/screen_usage_time.js"></script>')

    def add_routes(self):
        # 接收使用时间统计信息的路由
        @self.route('/usage', methods=['POST'])
        @u.require_secret()
        def receive_usage_data():
            return asyncio.run(self.handle_usage_data())

        # 接收图标文件的路由
        @self.route('/icons', methods=['POST'])
        @u.require_secret()
        def receive_icons():
            return asyncio.run(self.handle_icons())

        # 提供图标文件的路由
        @self.route('/icons/<path:filename>')
        def serve_icon(filename):
            return asyncio.run(self.serve_icon_file(filename))

        # 提供CSS文件的路由
        @self.route('/static/<path:filename>')
        def serve_static(filename):
            static_dir = u.get_path(f'plugins/{self.name}/static')
            return send_from_directory(static_dir, filename)

    def ensure_directories(self):
        # 确保数据目录存在
        data_dir = u.get_path(f'plugins/{self.name}/data')
        os.makedirs(data_dir, exist_ok=True)

    async def handle_usage_data(self):
        try:
            # 获取JSON数据
            data = request.get_json()
            if not data:
                return jsonify({'success': False, 'message': 'No JSON data received'}), 400

            # 按照example_json.json格式处理数据
            device_id = data.get('device-id')
            device_name = data.get('device-name')
            date = data.get('date')
            update_time = data.get('update-time')
            screen_usage_time = data.get('screen_usage_time', {})

            if not device_id:
                return jsonify({'success': False, 'message': 'Device ID is required'}), 400

            # 验证设备ID是否包含非法字符
            import string
            valid_chars = set(string.ascii_letters + string.digits + '-_')
            if not all(char in valid_chars for char in device_id):
                return jsonify({'success': False, 'message': 'Device ID contains invalid characters'}), 400

            # 构建设备目录路径
            data_dir = u.get_path(f'plugins/{self.name}/data')
            device_dir = os.path.join(data_dir, device_id)
            
            # 创建设备目录
            os.makedirs(device_dir, exist_ok=True)

            app_usage = screen_usage_time.get('app_usage', {})
            website_usage = screen_usage_time.get('website_usage', {})

            # 合并数据库操作，减少阻塞
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._update_usage_data, device_id, device_name, date, update_time, app_usage, website_usage)

            return jsonify({'success': True, 'message': 'Usage data received successfully'})
        except Exception as e:
            l.error(f'Error handling usage data: {e}')
            return jsonify({'success': False, 'message': str(e)}), 500

    def _update_usage_data(self, device_id, device_name, date, update_time, app_usage, website_usage):
        """在后台线程中更新使用时间数据"""
        with self.data_context() as d:
            # 初始化设备数据结构
            if 'devices' not in d:
                d['devices'] = {}
            
            # 更新设备数据
            device_data = {
                'device-name': device_name,
                'last-update': update_time or datetime.now().isoformat(),
                'screen_usage_time': {
                    'app_usage': app_usage,
                    'website_usage': website_usage
                }
            }
            
            if date:
                device_data['last-date'] = date
            
            d['devices'][device_id] = device_data
            d['last_updated'] = datetime.now().isoformat()

        self.global_data.last_updated = datetime.now().timestamp()

    async def handle_icons(self):
        try:
            saved_files = []

            # 获取设备ID
            device_id = request.headers.get('x-device-id') or request.form.get('x-device-id')
            if not device_id:
                return jsonify({'success': False, 'message': 'Device ID is required'}), 400

            # 验证设备ID是否包含非法字符
            import string
            valid_chars = set(string.ascii_letters + string.digits + '-_')
            if not all(char in valid_chars for char in device_id):
                return jsonify({'success': False, 'message': 'Device ID contains invalid characters'}), 400

            # 构建设备目录路径
            data_dir = u.get_path(f'plugins/{self.name}/data')
            device_dir = os.path.join(data_dir, device_id)
            webfavicons_dir = os.path.join(device_dir, 'WebFavicons')
            appicons_dir = os.path.join(device_dir, 'AppIcons')

            # 创建目录结构
            os.makedirs(webfavicons_dir, exist_ok=True)
            os.makedirs(appicons_dir, exist_ok=True)

            # 检查是否有文件字段（multipart/form-data格式）
            if request.files:
                # 遍历所有文件字段
                for field_name, files in request.files.items():
                    # 处理多个文件或单个文件
                    file_list = files if isinstance(files, list) else [files]
                    for file in file_list:  # type: ignore
                        file: FileStorage
                        if file.filename:
                            # 获取原始文件名，去除路径
                            original_filename = os.path.basename(file.filename)

                            # 检查文件名是否是base64编码
                            if not re.match(r'^[A-Za-z0-9+/]+={0,2}$', original_filename):
                                continue  # 跳过非base64编码的文件名

                            # 从文件名中提取扩展名
                            file_ext = os.path.splitext(original_filename)[1].lower()
                            # 如果没有扩展名，尝试从文件内容推断
                            if not file_ext:
                                # 检查文件内容的前几个字节来推断文件类型
                                content = file.read()
                                if content.startswith(b'\x00\x00\x01\x00'):
                                    file_ext = '.ico'
                                elif content.startswith(b'\x89PNG'):
                                    file_ext = '.png'
                                # 重置文件指针
                                file.seek(0)

                            # 只处理ico和png文件
                            if file_ext not in ['.ico', '.png']:
                                continue

                            # 构建新的文件名
                            base_name = os.path.splitext(original_filename)[0]
                            new_filename = f"{base_name}{file_ext}"

                            # 根据文件类型保存到不同目录
                            if file_ext == '.ico':
                                save_dir = webfavicons_dir
                            else:
                                save_dir = appicons_dir

                            save_path = os.path.join(save_dir, new_filename)
                            # 使用异步文件写入
                            content = file.read()
                            loop = asyncio.get_event_loop()
                            await loop.run_in_executor(None, self._save_file, save_path, content)
                            saved_files.append(new_filename)

            # 检查是否有请求体和filename请求头（直接发送文件内容格式）
            elif request.data and request.headers.get('filename'):
                # 获取文件名
                filename_header = request.headers.get('filename', '')
                # 去除路径
                filename_header = os.path.basename(filename_header)

                # 检查文件名是否是base64编码
                if not re.match(r'^[A-Za-z0-9+/]+={0,2}$', filename_header):
                    return jsonify({'success': False, 'message': 'Filename must be base64 encoded'}), 400

                # 从文件名中提取扩展名
                file_ext = os.path.splitext(filename_header)[1].lower()
                # 如果没有扩展名，尝试从文件内容推断
                if not file_ext:
                    if request.data.startswith(b'\x00\x00\x01\x00'):
                        file_ext = '.ico'
                    elif request.data.startswith(b'\x89PNG'):
                        file_ext = '.png'

                # 只处理ico和png文件
                if file_ext not in ['.ico', '.png']:
                    return jsonify({'success': False, 'message': 'Only .ico and .png files are allowed'}), 400

                # 构建新的文件名
                base_name = os.path.splitext(filename_header)[0]
                new_filename = f"{base_name}{file_ext}"

                # 根据文件类型保存到不同目录
                if file_ext == '.ico':
                    save_dir = webfavicons_dir
                else:
                    save_dir = appicons_dir

                save_path = os.path.join(save_dir, new_filename)
                # 使用异步文件写入
                content = request.data
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._save_file, save_path, content)
                saved_files.append(new_filename)

            # 检查是否有文件被保存
            if not saved_files:
                return jsonify({'success': False, 'message': 'No files received'}), 400

            return jsonify({'success': True, 'message': f'Saved {len(saved_files)} files', 'files': saved_files})
        except Exception as e:
            l.error(f'Error handling icons: {e}')
            return jsonify({'success': False, 'message': str(e)}), 500

    def _save_file(self, save_path, content):
        """在后台线程中保存文件"""
        with open(save_path, 'wb') as f:
            f.write(content)

    async def serve_icon_file(self, filename):
        try:
            # 清理文件名，处理双斜杠和路径前缀，去除开头和结尾的斜杠
            cleaned_filename = filename.strip('/')
            # 替换多个斜杠为单个斜杠
            cleaned_filename = '/'.join(filter(None, cleaned_filename.split('/')))

            # 检查是否包含设备ID和目录前缀
            parts = cleaned_filename.split('/')
            if len(parts) >= 2:
                # 格式: device-id/dir/filename 或 device-id/filename
                device_id = parts[0]
                encoded_filename = parts[-1]
                
                # 验证设备ID是否包含非法字符
                import string
                valid_chars = set(string.ascii_letters + string.digits + '-_')
                if not all(char in valid_chars for char in device_id):
                    return jsonify({'success': False, 'message': 'Invalid device ID'}), 400
                
                # 构建设备目录路径
                data_dir = u.get_path(f'plugins/{self.name}/data')
                device_dir = os.path.join(data_dir, device_id)
                
                # 尝试从设备的WebFavicons目录提供
                webfavicons_path = os.path.join(device_dir, 'WebFavicons')
                # 构建可能的文件名（添加.ico扩展名）
                ico_filename = f"{encoded_filename}.ico"
                # 使用异步方式检查文件是否存在
                loop = asyncio.get_event_loop()
                webfavicons_exists = await loop.run_in_executor(None, os.path.exists, os.path.join(webfavicons_path, ico_filename))
                if webfavicons_exists:
                    return send_from_directory(webfavicons_path, ico_filename)

                # 尝试从设备的AppIcons目录提供
                appicons_path = os.path.join(device_dir, 'AppIcons')
                # 构建可能的文件名（添加.png扩展名）
                png_filename = f"{encoded_filename}.png"
                # 使用异步方式检查文件是否存在
                appicons_exists = await loop.run_in_executor(None, os.path.exists, os.path.join(appicons_path, png_filename))
                if appicons_exists:
                    return send_from_directory(appicons_path, png_filename)
            else:
                # 兼容旧格式，尝试从默认目录提供
                encoded_filename = cleaned_filename
                
                # 尝试从默认WebFavicons目录提供
                webfavicons_path = u.get_path(f'plugins/{self.name}/data/WebFavicons')
                ico_filename = f"{encoded_filename}.ico"
                loop = asyncio.get_event_loop()
                webfavicons_exists = await loop.run_in_executor(None, os.path.exists, os.path.join(webfavicons_path, ico_filename))
                if webfavicons_exists:
                    return send_from_directory(webfavicons_path, ico_filename)

                # 尝试从默认AppIcons目录提供
                appicons_path = u.get_path(f'plugins/{self.name}/data/AppIcons')
                png_filename = f"{encoded_filename}.png"
                appicons_exists = await loop.run_in_executor(None, os.path.exists, os.path.join(appicons_path, png_filename))
                if appicons_exists:
                    return send_from_directory(appicons_path, png_filename)

            return jsonify({'success': False, 'message': 'Icon not found'}), 404
        except Exception as e:
            l.error(f'Error serving icon: {e}')
            return jsonify({'success': False, 'message': str(e)}), 500

    def format_time(self, seconds):
        """格式化时间，将秒数转换为时分秒格式"""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60

        if hours > 0:
            return f'{hours} 小时 {minutes} 分 {secs} 秒'
        elif minutes > 0:
            return f'{minutes} 分 {secs} 秒'
        else:
            return f'{secs} 秒'

    def handle_query_access_event(self, event):
        """处理查询访问事件，添加设备使用时间统计数据"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            devices = self.data.get('devices', {})
            formatted_devices = {}

            # 处理每个设备的数据
            for device_id, device_data in devices.items():
                device_name = device_data.get('device-name', 'Unknown Device')
                screen_usage_time = device_data.get('screen_usage_time', {})
                app_usage = screen_usage_time.get('app_usage', {})
                website_usage = screen_usage_time.get('website_usage', {})

                # 计算应用使用时间的最大值，用于进度条
                app_times = [data.get('total_time', 0) for data in app_usage.values()]
                app_max_time = max(app_times) if app_times else 1

                # 计算网站使用时间的最大值，用于进度条
                website_times = [data.get('total_time', 0) for data in website_usage.values()]
                website_max_time = max(website_times) if website_times else 1

                formatted_app_usage = {}
                for app_name, app_data in app_usage.items():
                    total_time = app_data.get('total_time', 0)
                    progress = (total_time / app_max_time) * 100 if app_max_time > 0 else 0
                    icon = app_data.get('icon', '')
                    if icon:
                        icon_filename = extract_filename(icon)
                        encoded_icon = base64.b64encode(icon_filename.encode('utf-8')).decode('utf-8')
                    else:
                        encoded_icon = ''
                    formatted_app_usage[app_name] = {
                        'icon': encoded_icon,
                        'total_time': total_time,
                        'formatted_time': self.format_time(total_time),
                        'progress': min(progress, 100)
                    }

                formatted_website_usage = {}
                for website_name, website_data in website_usage.items():
                    total_time = website_data.get('total_time', 0)
                    progress = (total_time / website_max_time) * 100 if website_max_time > 0 else 0
                    icon = website_data.get('icon', '')
                    if icon:
                        icon_filename = extract_filename(icon)
                        encoded_icon = base64.b64encode(icon_filename.encode('utf-8')).decode('utf-8')
                    else:
                        encoded_icon = ''
                    formatted_website_usage[website_name] = {
                        'icon': encoded_icon,
                        'total_time': total_time,
                        'formatted_time': self.format_time(total_time),
                        'progress': min(progress, 100)
                    }

                # 按使用时间排序
                sorted_app_usage = dict(sorted(formatted_app_usage.items(), key=lambda x: x[1]['total_time'], reverse=True))
                sorted_website_usage = dict(sorted(formatted_website_usage.items(), key=lambda x: x[1]['total_time'], reverse=True))

                # 根据配置项过滤，只显示排名前几个的应用和网站
                top_apps = self.config.top_apps
                top_websites = self.config.top_websites

                # 截取前N个应用
                filtered_app_usage = {}
                count = 0
                for app_name, app_data in sorted_app_usage.items():
                    if count < top_apps:
                        filtered_app_usage[app_name] = app_data
                        count += 1
                    else:
                        break

                # 截取前N个网站
                filtered_website_usage = {}
                count = 0
                for website_name, website_data in sorted_website_usage.items():
                    if count < top_websites:
                        filtered_website_usage[website_name] = website_data
                        count += 1
                    else:
                        break

                # 格式化设备数据
                formatted_devices[device_id] = {
                    'device-name': device_name,
                    'app_usage': filtered_app_usage,
                    'website_usage': filtered_website_usage,
                    'last-update': device_data.get('last-update'),
                    'last-date': device_data.get('last-date')
                }

            # 将使用时间统计数据添加到查询响应中
            event.query_response['screen_usage_time'] = {
                'devices': formatted_devices,
                'last_updated': self.data.get('last_updated'),
                'current_date': today
            }

            return event
        except Exception as e:
            l.error(f'Error handling query access event: {e}')
            return event


# 初始化插件
plugin = ScreenUsageTimePlugin()
