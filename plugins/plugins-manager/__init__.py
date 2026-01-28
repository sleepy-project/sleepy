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
from pathlib import Path
from packaging.version import parse as parse_version
from loguru import logger as l

from plugin import PluginBase, PluginMetadata, plugin_manager

CONFIG_FILE = 'data/manager_config.json'
DEFAULT_REGISTRY_URL = "https://sleepy-plugins.siiway.org"

class Plugin(PluginBase):
    def __init__(self, metadata: PluginMetadata):
        super().__init__(metadata)
        self.config_path = os.path.join(os.path.dirname(__file__), CONFIG_FILE)
        self.registry_url = self._load_config()

    def on_load(self):
        pass

    def on_register_cli(self, subparsers: argparse._SubParsersAction):
        parser = subparsers.add_parser('plugins', help='Manage plugins')
        sub = parser.add_subparsers(dest='plugin_action', required=True, help='Action')

        # Source
        p_src = sub.add_parser('source', help='Get or set registry URL')
        p_src.add_argument('url', nargs='?', help='New registry URL')
        p_src.add_argument('--reset', action='store_true', help='Reset to default')
        p_src.set_defaults(func=self.handle_source)

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

    def _load_config(self) -> str:
        if not os.path.exists(self.config_path):
            return DEFAULT_REGISTRY_URL
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f).get('url', DEFAULT_REGISTRY_URL)
        except:
            return DEFAULT_REGISTRY_URL

    def _save_config(self, url: str):
        self.registry_url = url
        with open(self.config_path, 'w') as f:
            json.dump({'url': url}, f)

    def handle_source(self, args):
        if args.reset:
            self._save_config(DEFAULT_REGISTRY_URL)
            l.success(f"Registry reset to {DEFAULT_REGISTRY_URL}")
        elif args.url:
            self._save_config(args.url.rstrip('/'))
            l.success(f"Registry updated to {self.registry_url}")
        else:
            print(f"Current Registry: {self.registry_url}")

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
            l.warning("Direct URL installation is deprecated in this version. Please use Registry ID.")
            return

        self._install_recursive(args.id, visited=set())

    def handle_remove(self, args):
        path = self._get_plugins_dir() / args.id
        if not path.exists():
            l.error(f"Plugin {args.id} not found.")
            return

        if not args.yes:
            if input(f"Delete {args.id}? [y/N] ").lower() != 'y':
                return

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
            l.error(f"Version info for {latest_ver} is missing/corrupt.")
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
