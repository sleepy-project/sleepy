# coding: utf-8

import os
import shutil
import subprocess
import argparse
import urllib.request
import zipfile
import io
from pathlib import Path
from loguru import logger as l

from plugin import PluginBase, PluginMetadata, plugin_manager

class Plugin(PluginBase):
    def __init__(self, metadata: PluginMetadata):
        super().__init__(metadata)

    def on_load(self):
        pass

    def on_register_cli(self, subparsers: argparse._SubParsersAction):
        # Register the main 'plugins' command
        parser = subparsers.add_parser('plugins', help='Manage plugins')
        
        # Create subparsers for 'plugins' (add, rm, list, etc.)
        plugin_subparsers = parser.add_subparsers(dest='plugin_action', required=True, help='Action')

        # Command: list
        parser_list = plugin_subparsers.add_parser('list', help='List installed plugins')
        parser_list.set_defaults(func=self.handle_list)

        # Command: add <url>
        parser_add = plugin_subparsers.add_parser('add', help='Install a plugin from URL (Git or Zip)')
        parser_add.add_argument('url', type=str, help='Git URL or URL to a zip file')
        parser_add.add_argument('--name', type=str, help='Optional directory name', default=None)
        parser_add.set_defaults(func=self.handle_add)

        # Command: remove <id> (alias: rm)
        parser_rm = plugin_subparsers.add_parser('remove', aliases=['rm'], help='Remove a plugin')
        parser_rm.add_argument('id', type=str, help='Plugin folder name (ID)')
        parser_rm.add_argument('-y', '--yes', action='store_true', help='Skip confirmation prompt')
        parser_rm.set_defaults(func=self.handle_remove)

        # Command: update <id>
        parser_up = plugin_subparsers.add_parser('update', help='Update a specific plugin (Git only)')
        parser_up.add_argument('id', type=str, help='Plugin folder name (ID)')
        parser_up.set_defaults(func=self.handle_update)

        # Command: update-all
        parser_upall = plugin_subparsers.add_parser('update-all', help='Update all git-based plugins')
        parser_upall.set_defaults(func=self.handle_update_all)

    def _get_plugins_dir(self) -> Path:
        return Path(plugin_manager.plugin_dir)

    def handle_list(self, args):
        print(f"\n{'NAME':<25} {'VERSION':<10} {'STATUS':<10} {'AUTHOR'}")
        print("-" * 60)
        
        for name, p in plugin_manager.plugins.items():
            meta = p.metadata
            status = "Enabled" if meta.enabled else "Disabled"
            print(f"{meta.name:<25} {meta.version:<10} {status:<10} {meta.author}")
        print("")

    def handle_remove(self, args):
        plugin_dir = self._get_plugins_dir()
        target_path = plugin_dir / args.id

        if not target_path.exists():
            l.error(f"Plugin '{args.id}' not found in {plugin_dir}")
            return

        if not args.yes:
            # Simple confirmation
            try:
                confirm = input(f"Are you sure you want to DELETE plugin '{args.id}'? [y/N] ")
                if confirm.lower() != 'y':
                    print("Operation cancelled.")
                    return
            except KeyboardInterrupt:
                print("\nOperation cancelled.")
                return

        try:
            shutil.rmtree(target_path)
            l.success(f"Plugin '{args.id}' removed successfully. Restart server to apply.")
        except Exception as e:
            l.error(f"Failed to remove plugin: {e}")

    def handle_add(self, args):
        url: str = args.url
        plugin_dir = self._get_plugins_dir()
        
        # Determine target folder name
        if args.name:
            target_name = args.name
        else:
            # Infer from URL
            basename = url.rstrip('/').split('/')[-1]
            if basename.endswith('.git'):
                target_name = basename[:-4]
            elif basename.endswith('.zip'):
                target_name = basename[:-4]
            else:
                target_name = basename
        
        target_path = plugin_dir / target_name
        if target_path.exists():
            l.error(f"Target directory '{target_name}' already exists.")
            return

        l.info(f"Installing plugin from {url} to {target_name}...")

        # Strategy 1: Git Clone
        if url.endswith('.git') or 'github.com' in url:
            try:
                subprocess.check_call(['git', 'clone', url, str(target_path)])
                l.success(f"Successfully cloned git repo to {target_path}")
                self._check_post_install(target_path)
            except FileNotFoundError:
                l.error("Git command not found. Please install git.")
            except subprocess.CalledProcessError as e:
                l.error(f"Git clone failed: {e}")
            return

        # Strategy 2: Download Zip
        try:
            l.info("Downloading zip file...")
            req = urllib.request.Request(url, headers={'User-Agent': 'Sleepy-Plugin-Manager'})
            with urllib.request.urlopen(req) as response:
                if response.status != 200:
                    l.error(f"Download failed with status code {response.status}")
                    return
                zip_data = response.read()

            l.info("Extracting...")
            with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
                # Handle GitHub zip folder structure (usually wraps in a root dir)
                # Check if all files are inside a single top-level folder
                top_level_dirs = {item.split('/')[0] for item in z.namelist() if '/' in item}
                
                if len(top_level_dirs) == 1:
                    root_folder = list(top_level_dirs)[0]
                    for member in z.infolist():
                        if member.filename.startswith(root_folder + '/'):
                            # Strip prefix
                            target_filename = member.filename[len(root_folder)+1:]
                            if not target_filename: continue 
                            
                            dest = target_path / target_filename
                            if member.is_dir():
                                dest.mkdir(parents=True, exist_ok=True)
                            else:
                                dest.parent.mkdir(parents=True, exist_ok=True)
                                with open(dest, 'wb') as f:
                                    f.write(z.read(member))
                else:
                    z.extractall(target_path)
            
            l.success(f"Successfully installed zip plugin to {target_path}")
            self._check_post_install(target_path)

        except Exception as e:
            l.error(f"Failed to install zip plugin: {e}")
            if target_path.exists():
                shutil.rmtree(target_path)

    def handle_update(self, args):
        self._update_plugin(args.id)

    def handle_update_all(self, args):
        plugin_dir = self._get_plugins_dir()
        count = 0
        for item in os.listdir(plugin_dir):
            if (plugin_dir / item).is_dir():
                self._update_plugin(item)
                count += 1
        l.info(f"Finished updating {count} plugins.")

    def _update_plugin(self, plugin_id: str):
        plugin_dir = self._get_plugins_dir()
        target_path = plugin_dir / plugin_id

        if not target_path.exists():
            l.error(f"Plugin {plugin_id} not found.")
            return

        # Check if git repo
        if (target_path / '.git').exists():
            l.info(f"Updating {plugin_id} via git...")
            try:
                subprocess.check_call(['git', 'pull'], cwd=target_path)
                l.success(f"Updated {plugin_id}.")
            except Exception as e:
                l.error(f"Failed to update {plugin_id}: {e}")
        else:
            l.debug(f"Plugin {plugin_id} is not a git repository. Skipping update.")

    def _check_post_install(self, path: Path):
        """Validates installation"""
        if not (path / 'pyproject.toml').exists():
            l.warning(f"Warning: {path.name} does not look like a valid Sleepy plugin (missing pyproject.toml).")
        else:
            l.info(f"Plugin {path.name} valid. Please restart server to load.")
