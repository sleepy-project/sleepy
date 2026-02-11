import os
import json
import logging
import asyncio
import base64
from datetime import datetime
from flask import request, jsonify, send_from_directory, render_template_string
from werkzeug.utils import secure_filename
import utils as u
import plugin as pl
from plugin import Plugin

l = logging.getLogger(__name__)

class ScreenUsageTimePlugin(Plugin):
    def __init__(self):
        super().__init__(
            name=__name__,
            data={
                'app_usage': {},
                'website_usage': {},
                'last_updated': None
            },
            config={
                'top_apps': 5,
                'top_websites': 5
            },
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
        import asyncio
        
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
        webfavicons_dir = os.path.join(data_dir, 'WebFavicons')
        appicons_dir = os.path.join(data_dir, 'AppIcons')
        
        os.makedirs(webfavicons_dir, exist_ok=True)
        os.makedirs(appicons_dir, exist_ok=True)
    
    async def handle_usage_data(self):
        try:
            # 获取JSON数据
            data = request.get_json()
            if not data:
                return jsonify({'success': False, 'message': 'No JSON data received'}), 400
            
            # 处理数据
            app_usage = {}
            website_usage = {}
            daily_usage = {}
            
            # 处理AppModels
            if 'AppModels' in data:
                for app in data['AppModels']:
                    app_name = app.get('Description', '')
                    icon_file = app.get('IconFile', '')
                    total_time = app.get('TotalTime', 0)
                    
                    # 处理图标路径
                    if icon_file:
                        icon_file = os.path.basename(icon_file)
                    
                    app_usage[app_name] = {
                        'icon': icon_file,
                        'total_time': total_time
                    }
            
            # 处理DailyLogModels（每天的使用时间记录）
            if 'DailyLogModels' in data:
                for daily_log in data['DailyLogModels']:
                    # 提取日期部分（YYYY-MM-DD）
                    date_str = daily_log.get('Date', '')
                    if not date_str:
                        continue
                    
                    # 格式化日期为YYYY-MM-DD
                    try:
                        date = date_str.split(' ')[0]  # 去掉时间部分
                    except:
                        date = date_str
                    
                    app_id = daily_log.get('AppModelID', '')
                    duration = daily_log.get('Time', 0)
                    
                    # 查找对应的应用名称
                    app_name = ''
                    icon_file = ''
                    if 'AppModels' in data:
                        for app in data['AppModels']:
                            if app.get('ID') == app_id:
                                app_name = app.get('Description', '')
                                icon_file = app.get('IconFile', '')
                                if icon_file:
                                    icon_file = os.path.basename(icon_file)
                                break
                    
                    if app_name:
                        if date not in daily_usage:
                            daily_usage[date] = {'app_usage': {}, 'website_usage': {}}
                        daily_usage[date]['app_usage'][app_name] = {
                            'icon': icon_file,
                            'total_time': duration
                        }
            
            # 处理WebBrowseLogModels（网站浏览记录）
            if 'WebBrowseLogModels' in data:
                # 创建site_id到网站名称的映射
                site_id_to_name = {}
                site_id_to_icon = {}
                
                # 检查是否存在WebSiteModels表
                if 'WebSiteModels' in data:
                    for website in data['WebSiteModels']:
                        site_id = website.get('ID', '')
                        website_name = website.get('Title', '')
                        icon_file = website.get('IconFile', '')
                        
                        if site_id and website_name:
                            site_id_to_name[site_id] = website_name
                            if icon_file:
                                if 'WebFavicons' in icon_file:
                                    icon_file = icon_file.split('WebFavicons')[-1]
                                    if icon_file.startswith(os.sep):
                                        icon_file = icon_file[1:]
                            site_id_to_icon[site_id] = icon_file
                
                # 按日期和网站ID分组统计
                web_logs_by_date = {}
                for web_log in data['WebBrowseLogModels']:
                    # 提取日期部分（YYYY-MM-DD）
                    log_time = web_log.get('LogTime', '')
                    if not log_time:
                        continue
                    
                    # 格式化日期为YYYY-MM-DD
                    try:
                        date = log_time.split(' ')[0]  # 去掉时间部分
                    except:
                        date = log_time
                    
                    site_id = web_log.get('SiteId', '')
                    duration = web_log.get('Duration', 0)
                    
                    if date not in web_logs_by_date:
                        web_logs_by_date[date] = {}
                    if site_id not in web_logs_by_date[date]:
                        web_logs_by_date[date][site_id] = 0
                    web_logs_by_date[date][site_id] += duration
                
                # 使用网站名称或SiteId作为网站名称
                for date, site_logs in web_logs_by_date.items():
                    if date not in daily_usage:
                        daily_usage[date] = {'app_usage': {}, 'website_usage': {}}
                    for site_id, total_duration in site_logs.items():
                        # 优先使用WebSiteModels中的网站名称
                        if site_id in site_id_to_name:
                            website_name = site_id_to_name[site_id]
                            icon_file = site_id_to_icon.get(site_id, '')
                        else:
                            # 如果没有网站名称，使用SiteId作为网站名称
                            website_name = f'Site {site_id}'
                            icon_file = ''
                        
                        # 将反斜杠替换
                        strip_icon_file = (icon_file or '').replace('\\', '').replace(os.sep, '')
                        
                        daily_usage[date]['website_usage'][website_name] = {
                            'icon': strip_icon_file,
                            'total_time': total_duration
                        }
            
            # 合并数据库操作，减少阻塞
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._update_usage_data, app_usage, website_usage, daily_usage)
            
            return jsonify({'success': True, 'message': 'Usage data received successfully'})
        except Exception as e:
            l.error(f'Error handling usage data: {e}')
            return jsonify({'success': False, 'message': str(e)}), 500
    
    def _update_usage_data(self, app_usage, website_usage, daily_usage=None):
        """在后台线程中更新使用时间数据"""
        with self.data_context() as d:
            if app_usage:
                d['app_usage'] = app_usage
            if website_usage:
                d['website_usage'] = website_usage
            if daily_usage:
                d['daily_usage'] = daily_usage
            d['last_updated'] = datetime.now().isoformat()
    
    async def handle_icons(self):
        try:
            saved_files = []
            
            # 检查是否有文件字段（multipart/form-data格式）
            if request.files:
                # 遍历所有文件字段
                for field_name, files in request.files.items():
                    # 处理多个文件
                    if isinstance(files, list):
                        for file in files:
                            if file.filename:
                                # 直接使用文件对象的 filename 属性，Flask 会自动处理编码
                                filename = secure_filename(file.filename)
                                file_ext = os.path.splitext(filename)[1].lower()
                                
                                # 根据文件类型保存到不同目录
                                if file_ext == '.ico':
                                    save_dir = u.get_path(f'plugins/{self.name}/data/WebFavicons')
                                elif file_ext == '.png':
                                    save_dir = u.get_path(f'plugins/{self.name}/data/AppIcons')
                                else:
                                    continue  # 只处理ico和png文件
                                
                                save_path = os.path.join(save_dir, filename)
                                # 使用异步文件写入
                                content = file.read()
                                loop = asyncio.get_event_loop()
                                await loop.run_in_executor(None, self._save_file, save_path, content)
                                saved_files.append(filename)
                    else:
                        # 处理单个文件
                        file = files
                        if file.filename:
                            # 直接使用文件对象的 filename 属性，Flask 会自动处理编码
                            filename = secure_filename(file.filename)
                            file_ext = os.path.splitext(filename)[1].lower()
                            
                            # 根据文件类型保存到不同目录
                            if file_ext == '.ico':
                                save_dir = u.get_path(f'plugins/{self.name}/data/WebFavicons')
                            elif file_ext == '.png':
                                save_dir = u.get_path(f'plugins/{self.name}/data/AppIcons')
                            else:
                                continue  # 只处理ico和png文件
                            
                            save_path = os.path.join(save_dir, filename)
                            # 使用异步文件写入
                            content = file.read()
                            loop = asyncio.get_event_loop()
                            await loop.run_in_executor(None, self._save_file, save_path, content)
                            saved_files.append(filename)
            
            # 检查是否有请求体和filename请求头（直接发送文件内容格式）
            elif request.data and request.headers.get('filename'):
                # 对文件名进行 base64 解码
                encoded_filename = request.headers.get('filename', '')
                try:
                    # 解码 base64 编码的文件名
                    filename = base64.b64decode(encoded_filename).decode('utf-8')
                    # 保存原始文件名，不使用 secure_filename，确保中文文件名正确保存
                    # 如果文件名包含路径，只取文件名部分
                    filename = os.path.basename(filename)
                except:
                    # 如果解码失败，使用原始文件名
                    filename = encoded_filename
                    filename = os.path.basename(filename)
                file_ext = os.path.splitext(filename)[1].lower()
                
                # 根据文件类型保存到不同目录
                if file_ext == '.ico':
                    save_dir = u.get_path(f'plugins/{self.name}/data/WebFavicons')
                elif file_ext == '.png':
                    save_dir = u.get_path(f'plugins/{self.name}/data/AppIcons')
                else:
                    return jsonify({'success': False, 'message': 'Only .ico and .png files are allowed'}), 400
                
                save_path = os.path.join(save_dir, filename)
                # 使用异步文件写入
                content = request.data
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._save_file, save_path, content)
                saved_files.append(filename)
            
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
            
            # 检查是否包含目录前缀
            if '/' in cleaned_filename:
                # 分离目录和文件名
                parts = cleaned_filename.split('/')
                dir_name = parts[-2]
                file_name = parts[-1]
            else:
                dir_name = ''
                file_name = cleaned_filename
            
            # 尝试从相应的目录提供
            if dir_name == 'WebFavicons' or dir_name == 'AppIcons':
                # 使用指定的目录
                icon_path = u.get_path(f'plugins/{self.name}/data/{dir_name}')
                # 使用异步方式检查文件是否存在
                loop = asyncio.get_event_loop()
                file_exists = await loop.run_in_executor(None, os.path.exists, os.path.join(icon_path, file_name))
                if file_exists:
                    return send_from_directory(icon_path, file_name)
            else:
                # 尝试从WebFavicons目录提供
                webfavicons_path = u.get_path(f'plugins/{self.name}/data/WebFavicons')
                # 使用异步方式检查文件是否存在
                loop = asyncio.get_event_loop()
                webfavicons_exists = await loop.run_in_executor(None, os.path.exists, os.path.join(webfavicons_path, cleaned_filename))
                if webfavicons_exists:
                    return send_from_directory(webfavicons_path, cleaned_filename)
                
                # 尝试从AppIcons目录提供
                appicons_path = u.get_path(f'plugins/{self.name}/data/AppIcons')
                # 使用异步方式检查文件是否存在
                appicons_exists = await loop.run_in_executor(None, os.path.exists, os.path.join(appicons_path, cleaned_filename))
                if appicons_exists:
                    return send_from_directory(appicons_path, cleaned_filename)
            
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
            return f'{hours}小时{minutes}分{secs}秒'
        elif minutes > 0:
            return f'{minutes}分{secs}秒'
        else:
            return f'{secs}秒'
    
    def handle_query_access_event(self, event):
        """处理查询访问事件，添加设备使用时间统计数据"""
        try:
            # 获取当天日期，格式为YYYY-MM-DD
            today = datetime.now().strftime('%Y-%m-%d')
            
            # 优先使用当天的使用时间数据
            daily_usage = self.data.get('daily_usage', {})
            today_usage = daily_usage.get(today, {})
            
            # 如果当天没有数据，则使用总时间数据
            app_usage = today_usage.get('app_usage', self.data.get('app_usage', {}))
            website_usage = today_usage.get('website_usage', self.data.get('website_usage', {}))
            
            # 计算应用使用时间的最大值，用于进度条
            app_times = [data.get('total_time', 0) for data in app_usage.values()]
            app_max_time = max(app_times) if app_times else 1
            
            # 计算网站使用时间的最大值，用于进度条
            website_times = [data.get('total_time', 0) for data in website_usage.values()]
            website_max_time = max(website_times) if website_times else 1
            
            # 格式化应用使用时间数据
            formatted_app_usage = {}
            for app_name, app_data in app_usage.items():
                total_time = app_data.get('total_time', 0)
                progress = (total_time / app_max_time) * 100 if app_max_time > 0 else 0
                formatted_app_usage[app_name] = {
                    'icon': app_data.get('icon', ''),
                    'total_time': total_time,
                    'formatted_time': self.format_time(total_time),
                    'progress': min(progress, 100)  # 确保进度不超过100%
                }
            
            # 格式化网站使用时间数据
            formatted_website_usage = {}
            for website_name, website_data in website_usage.items():
                total_time = website_data.get('total_time', 0)
                progress = (total_time / website_max_time) * 100 if website_max_time > 0 else 0
                formatted_website_usage[website_name] = {
                    'icon': website_data.get('icon', ''),
                    'total_time': total_time,
                    'formatted_time': self.format_time(total_time),
                    'progress': min(progress, 100)  # 确保进度不超过100%
                }
            
            # 按使用时间排序
            sorted_app_usage = dict(sorted(formatted_app_usage.items(), key=lambda x: x[1]['total_time'], reverse=True))
            sorted_website_usage = dict(sorted(formatted_website_usage.items(), key=lambda x: x[1]['total_time'], reverse=True))
            
            # 根据配置项过滤，只显示排名前几个的应用和网站
            top_apps = self.config.get('top_apps', 5)
            top_websites = self.config.get('top_websites', 5)
            
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
            
            # 将使用时间统计数据添加到查询响应中
            event.query_response['screen_usage_time'] = {
                'app_usage': filtered_app_usage,
                'website_usage': filtered_website_usage,
                'last_updated': self.data.get('last_updated'),
                'current_date': today,
                'using_daily_data': bool(today_usage)
            }
            
            return event
        except Exception as e:
            l.error(f'Error handling query access event: {e}')
            return event

# 初始化插件
plugin = ScreenUsageTimePlugin()