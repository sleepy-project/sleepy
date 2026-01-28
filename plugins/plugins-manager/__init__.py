# coding: utf-8

import os
import shutil
import subprocess
import argparse
import urllib.request
import json
import zipfile
import io
import tempfile
import asyncio
from pathlib import Path
from packaging.version import parse as parse_version
from loguru import logger as l

from plugin import PluginBase, PluginMetadata, plugin_manager

# 路径配置
DATA_DIR = Path('data')
CONFIG_FILE = DATA_DIR / 'manager_config.json'
AUTO_INSTALL_FILE = DATA_DIR / 'auto_install.json'

DEFAULT_REGISTRY_URL = "https://sleepy-plugins.siiway.org"

class Plugin(PluginBase):
    def __init__(self, metadata: PluginMetadata):
        super().__init__(metadata)
        # 确保 data 目录存在
        if not DATA_DIR.exists():
            DATA_DIR.mkdir(parents=True, exist_ok=True)
        
        self.config = self._load_config()
        self.registry_url = self.config.get('url', DEFAULT_REGISTRY_URL)
        self.auto_self_update = self.config.get('auto_self_update', False)

    def on_load(self):
        l.info(f"{self.metadata.name} loaded.")

    async def on_startup(self):
        l.info(f"{self.metadata.name} starting background tasks...")
        asyncio.create_task(self._startup_routine())

    async def _startup_routine(self):
        """启动时的后台任务：自更新检查和自动安装"""
        # 1. 自动安装缺失插件
        await self._process_auto_install()

        # 2. 检查自身更新
        if self.auto_self_update:
            await self._check_and_update_self()

    async def _process_auto_install(self):
        """读取 auto_install.json 并安装缺失插件"""

        l.info("[AutoInstall] Processing auto_install.json...")

        if not AUTO_INSTALL_FILE.exists():
            # 创建默认空文件
            with open(AUTO_INSTALL_FILE, 'w') as f:
                json.dump([], f, indent=2)
            return

        try:
            with open(AUTO_INSTALL_FILE, 'r') as f:
                required_plugins = json.load(f)
                l.debug(f"[AutoInstall] Required plugins: {required_plugins}")
            
            if not isinstance(required_plugins, list):
                l.warning(f"Invalid format in {AUTO_INSTALL_FILE}, expected a list.")
                return

            plugin_dir = self._get_plugins_dir()

            for plugin_id in required_plugins:
                l.info(f"[AutoInstall] Checking plugin '{plugin_id}'...")
                if not (plugin_dir / plugin_id).exists():
                    l.info(f"[AutoInstall] Plugin '{plugin_id}' is missing. Installing...")
                    # 在线程中运行安装逻辑，避免阻塞事件循环
                    await asyncio.to_thread(self._install_recursive, plugin_id, set())
        except Exception as e:
            l.error(f"[AutoInstall] Error processing auto install list: {e}")

    async def _check_and_update_self(self):
        """检查并更新自身"""
        l.info("[SelfUpdate] Checking for updates...")
        try:
            # 获取远程元数据
            # 运行在线程中以防阻塞
            meta = await asyncio.to_thread(self._fetch_metadata, "plugins-manager")
            if not meta: return

            latest_ver_str = meta.get('latest')
            if not latest_ver_str: return

            current_ver = parse_version(self.metadata.version)
            latest_ver = parse_version(latest_ver_str)

            if latest_ver > current_ver:
                l.warning(f"[SelfUpdate] New version found: {latest_ver} (Current: {current_ver}). Updating...")
                await asyncio.to_thread(
                    self._install_recursive, 
                    "plugins-manager", 
                    visited=set(), 
                    force_update=True
                )
                l.success("[SelfUpdate] Plugins Manager updated. Please restart the server to apply changes.")
            else:
                l.debug("[SelfUpdate] Plugins Manager is up to date.")

        except Exception as e:
            l.error(f"[SelfUpdate] Failed check: {e}")


    def on_register_cli(self, subparsers: argparse._SubParsersAction):
        parser = subparsers.add_parser('plugins', help='Manage plugins')
        sub = parser.add_subparsers(dest='plugin_action', required=True, help='Action')

        # Config
        p_cfg = sub.add_parser('config', help='Configure Plugin Manager')
        p_cfg.add_argument('--url', help='Set registry URL')
        p_cfg.add_argument('--auto-update', choices=['true', 'false'], help='Enable/Disable auto self-update on startup')
        p_cfg.set_defaults(func=self.handle_config)

        # List
        sub.add_parser('list', help='List installed plugins').set_defaults(func=self.handle_list)

        # Add
        p_add = sub.add_parser('add', help='Install a plugin via ID')
        p_add.add_argument('id', help='Plugin ID (registry) or URL')
        p_add.add_argument('-y', '--yes', action='store_true', help='Skip confirmation')
        p_add.set_defaults(func=self.handle_add)

        # Remove
        p_rm = sub.add_parser('remove', aliases=['rm'], help='Remove a plugin')
        p_rm.add_argument('id', help='Plugin ID')
        p_rm.add_argument('-y', '--yes', action='store_true', help='Skip confirmation')
        p_rm.set_defaults(func=self.handle_remove)

        # Update
        p_up = sub.add_parser('update', help='Update a plugin')
        p_up.add_argument('id', help='Plugin ID')
        p_up.set_defaults(func=self.handle_update)

        # Self Update
        sub.add_parser('self-update', help='Update the plugin manager itself').set_defaults(func=self.handle_self_update)

    def _load_config(self) -> dict:
        if not CONFIG_FILE.exists():
            return {}
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}

    def _save_current_config(self):
        cfg = {
            'url': self.registry_url,
            'auto_self_update': self.auto_self_update
        }
        with open(CONFIG_FILE, 'w') as f:
            json.dump(cfg, f, indent=2)

    # --- CLI Handlers ---

    def handle_config(self, args):
        changed = False
        if args.url:
            self.registry_url = args.url.rstrip('/')
            print(f"Registry URL set to: {self.registry_url}")
            changed = True
        
        if args.auto_update:
            self.auto_self_update = (args.auto_update.lower() == 'true')
            print(f"Auto self-update set to: {self.auto_self_update}")
            changed = True

        if changed:
            self._save_current_config()
        else:
            print("Current Configuration:")
            print(f"  Registry URL: {self.registry_url}")
            print(f"  Auto Self-Update: {self.auto_self_update}")
            print(f"  Config File: {CONFIG_FILE}")

    def handle_list(self, args):
        print(f"\n{'NAME':<25} {'VERSION':<10} {'STATUS':<10} {'AUTHOR'}")
        print("-" * 60)
        for _, p in plugin_manager.plugins.items():
            meta = p.metadata
            status = "Enabled" if meta.enabled else "Disabled"
            print(f"{meta.name:<25} {meta.version:<10} {status:<10} {meta.author}")
        print("")

    def handle_add(self, args):
        if "://" in args.id or args.id.endswith(".git"):
            l.warning("Direct URL installation is deprecated. Please use Registry ID.")
            return
        self._install_recursive(args.id, visited=set())
        
        # 询问是否添加到 auto_install.json
        if not args.yes:
            # 简单判断是否已在列表中
            try:
                with open(AUTO_INSTALL_FILE, 'r') as f:
                    current_list = json.load(f)
            except:
                current_list = []
            
            if args.id not in current_list:
                l.info(f"Tip: Add '{args.id}' to {AUTO_INSTALL_FILE} to ensure it installs on new deployments.")

    def handle_remove(self, args):
        path = self._get_plugins_dir() / args.id
        if not path.exists():
            l.error(f"Plugin {args.id} not found.")
            return
        
        if not args.yes:
            if input(f"Delete {args.id}? [y/N] ").lower() != 'y': return
        
        try:
            shutil.rmtree(path)
            l.success(f"Removed {args.id}")
        except Exception as e:
            l.error(f"Failed to remove: {e}")

    def handle_update(self, args):
        l.info(f"Checking updates for {args.id}...")
        self._install_recursive(args.id, visited=set(), force_update=True)

    def handle_self_update(self, args):
        l.info("Self-updating plugins-manager...")
        self._install_recursive("plugins-manager", visited=set(), force_update=True)
        l.success("Self-update complete. Please restart the server immediately.")

    def _get_plugins_dir(self) -> Path:
        return Path(plugin_manager.plugin_dir)

    def _fetch_metadata(self, plugin_id: str) -> dict | None:
        url = f"{self.registry_url}/{plugin_id}.json"
        l.debug(f"Fetching metadata from {url}")
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Sleepy-PM/2.0'})
            with urllib.request.urlopen(req, timeout=10) as res:
                if res.status == 200:
                    return json.loads(res.read())
        except Exception as e:
            l.warning(f"Failed to fetch metadata for '{plugin_id}': {e}")
        return None

    def _install_recursive(self, plugin_id: str, visited: set, force_update=False):
        """
        递归安装插件及其依赖
        """
        if plugin_id in visited:
            return
        visited.add(plugin_id)

        target_path = self._get_plugins_dir() / plugin_id
        is_installed = target_path.exists()

        if is_installed and not force_update:
            l.info(f"Plugin '{plugin_id}' already installed. Skipping.")

        # 1. 获取 Registry 信息
        meta = self._fetch_metadata(plugin_id)
        if not meta:
            if is_installed:
                l.warning(f"Could not find '{plugin_id}' in registry, skipping dependency check.")
                return
            else:
                l.error(f"Plugin '{plugin_id}' not found in registry.")
                return

        latest_ver = meta.get('latest')
        version_info = meta.get('versions', {}).get(latest_ver)

        if not version_info:
            l.error(f"Version info for {plugin_id} {latest_ver} is missing.")
            return

        # 2. 检查是否需要安装/更新
        should_install = False
        if not is_installed:
            l.info(f"Installing {plugin_id} v{latest_ver}...")
            should_install = True
        elif force_update:
            # 读取本地版本进行对比
            local_ver = self._get_local_version(plugin_id)
            if local_ver != latest_ver:
                l.info(f"Updating {plugin_id}: {local_ver} -> {latest_ver}")
                should_install = True
            else:
                l.info(f"{plugin_id} is already up to date ({local_ver}).")

        # 3. 处理依赖 (先于自身安装，防止依赖缺失报错)
        dependencies = version_info.get('dependencies', {})
        for dep_id, dep_req in dependencies.items():
            l.info(f"Checking dependency '{dep_id}' ({dep_req}) for '{plugin_id}'...")
            self._install_recursive(dep_id, visited, force_update=False)

        # 4. 执行安装
        if should_install:
            success = self._download_and_extract(
                url=version_info['url'],
                type=version_info.get('type', 'zip'),
                target_path=target_path
            )
            if success:
                l.success(f"Successfully installed/updated {plugin_id}")
            else:
                l.error(f"Failed to install {plugin_id}")

    def _get_local_version(self, plugin_id: str) -> str:
        try:
            # 尝试通过 plugin_manager 读取已加载的，或者直接读文件
            if plugin_id in plugin_manager.plugins:
                return plugin_manager.plugins[plugin_id].metadata.version

            # 如果没加载（比如刚启动），手动读 toml
            toml_path = self._get_plugins_dir() / plugin_id / 'pyproject.toml'
            if toml_path.exists():
                from pyproject_parser import PyProject
                pyproject = PyProject.load(str(toml_path))
                if pyproject and pyproject.project:
                    return str(pyproject.project.get('version', '0.0.0'))
        except:
            pass
        return "0.0.0"

    def _download_and_extract(self, url: str, type: str, target_path: Path) -> bool:
        # 使用临时目录，防止下载一半失败导致插件损坏
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_extract_path = Path(temp_dir) / "extract"

            try:
                if type == 'git':
                    subprocess.check_call(['git', 'clone', url, str(temp_extract_path)])
                    # 移除 .git 减小体积
                    shutil.rmtree(temp_extract_path / '.git', ignore_errors=True)

                elif type == 'zip':
                    l.debug(f"Downloading {url}...")
                    req = urllib.request.Request(url, headers={'User-Agent': 'Sleepy-PM'})
                    with urllib.request.urlopen(req) as res:
                        zip_data = res.read()

                    with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
                        top_level = {x.split('/')[0] for x in z.namelist() if '/' in x}
                        if len(top_level) == 1:
                            root = list(top_level)[0]
                            for member in z.infolist():
                                if member.filename.startswith(root + '/') and not member.filename.endswith('/'):
                                    # remove prefix
                                    rel_path = member.filename[len(root) + 1:]
                                    if not rel_path:
                                        continue
                                    target_file = temp_extract_path / rel_path
                                    target_file.parent.mkdir(parents=True, exist_ok=True)
                                    with open(target_file, 'wb') as f:
                                        f.write(z.read(member))
                        else:
                            z.extractall(temp_extract_path)

                else:
                    l.error(f"Unknown download type: {type}")
                    return False

                # 验证 pyproject.toml
                if not (temp_extract_path / 'pyproject.toml').exists():
                    l.error("Invalid plugin: pyproject.toml not found in downloaded archive.")
                    return False

                if target_path.exists():
                    try:
                        shutil.rmtree(target_path)
                    except OSError:
                        # 如果删除失败（例如 plugins-manager 自己），尝试直接覆盖文件
                        l.warning(f"Could not remove {target_path}, attempting overwrite copy...")
                        shutil.copytree(temp_extract_path, target_path, dirs_exist_ok=True)
                        return True

                shutil.copytree(temp_extract_path, target_path)
                return True

            except Exception as e:
                l.error(f"Install error: {e}")
                return False
