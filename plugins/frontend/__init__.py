# coding: utf-8

import sys
import zipfile
import urllib.request
import json
import shutil
import subprocess
import os
import argparse
from pathlib import Path
from fastapi import Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger as l

from plugin import PluginBase, PluginMetadata

REPO_OWNER = "sleepy-project"
REPO_NAME = "sleepy-frontend"
ASSET_NAME = "dist.zip"
SRC_ZIP_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/archive/refs/heads/main.zip"


class Plugin(PluginBase):
    """
    Frontend Plugin with Smart Build/Download Logic
    """

    def __init__(self, metadata: PluginMetadata):
        super().__init__(metadata)

        self.plugin_dir = Path(__file__).parent.resolve()
        self.dist_path = self.plugin_dir / "dist"
        self.src_path = self.plugin_dir / "frontend-src"

        self.add_cli_command(
            command="sync",
            handler=self.cli_sync,
            help="Sync and build the frontend source code",
            arguments=[
                (['--force-download'], {'action': 'store_true', 'help': 'Force re-download source code'}),
            ]
        )

        self._ensure_frontend_ready()

        self._register_routes()

    def on_load(self):
        l.info(f'{self.metadata.name} plugin loaded!')

    def on_unload(self):
        l.info(f'{self.metadata.name} plugin unloaded!')

    async def cli_sync(self, args: argparse.Namespace):
        """
        CLI 命令处理函数：手动触发同步和构建
        """
        l.info("Starting frontend sync process...")
        if not self._is_pnpm_installed():
            l.error("pnpm is not installed. Cannot build from source.")
            return

        try:
            if args.force_download or not self.src_path.exists():
                self._download_and_extract_source()
            else:
                l.info("Source folder exists. Skipping download (use --force-download to overwrite).")

            self._build_frontend()
            l.info("Frontend sync and build completed successfully!")
        except Exception as e:
            l.error(f"Sync failed: {e}")

    def _ensure_frontend_ready(self):
        """
        初始化逻辑：
        1. dist 存在 -> 跳过
        2. dist 不存在:
           - 有 nodejs & pnpm -> 下载源码 -> 编译 -> 复制 dist
           - 无 nodejs & pnpm -> 下载 Release dist.zip
        """
        if self.dist_path.exists() and any(self.dist_path.iterdir()):
            l.info(f"Frontend dist found at: {self.dist_path}")
            return

        l.warning("Frontend dist not found. Starting setup...")

        if not self._is_node_installed():
            l.error("Node.js is not installed. Cannot build from source. Falling back to release download...")
            self._download_release_dist()
            return

        if not self._is_pnpm_installed():
            l.error("pnpm is not installed. Cannot build from source. Falling back to release download...")
            self._download_release_dist()
            return

        l.info("Node.js and pnpm detected. Attempting to build from source...")
        try:
            self._download_and_extract_source()
            self._build_frontend()
        except Exception as e:
            l.error(f"Build failed: {e}. Falling back to release download.")
            self._download_release_dist()

    def _is_node_installed(self) -> bool:
        return shutil.which("node") is not None or shutil.which("nodejs") is not None

    def _is_pnpm_installed(self) -> bool:
        return shutil.which("pnpm") is not None

    def _download_and_extract_source(self):
        """下载 main.zip 并解压到 frontend-src"""
        l.info(f"Downloading source from {SRC_ZIP_URL}...")

        # 清理旧源码
        if self.src_path.exists():
            shutil.rmtree(self.src_path)

        zip_path = self.plugin_dir / "source.zip"

        try:
            # 下载
            self._download_file(SRC_ZIP_URL, zip_path)

            # 解压
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                root_folder = zip_ref.namelist()[0].split('/')[0]
                zip_ref.extractall(self.plugin_dir)

            extracted_path = self.plugin_dir / root_folder
            if extracted_path.exists():
                extracted_path.rename(self.src_path)
                l.info(f"Source extracted to {self.src_path}")
            else:
                raise Exception(f"Failed to locate extracted folder: {root_folder}")

        finally:
            if zip_path.exists():
                zip_path.unlink()

    def _build_frontend(self):
        """Run pnpm install && pnpm build in frontend-src, then copy dist"""

        is_windows = sys.platform.startswith("win")

        # Command forms
        if is_windows:
            install_cmd = ["pnpm", "install"]
            build_cmd = ["pnpm", "build"]
            use_shell = False
        else:
            install_cmd = ["pnpm install"]
            build_cmd = ["pnpm build"]
            use_shell = True

        # Install dependencies
        l.info("Installing dependencies (pnpm install)...")
        subprocess.run(install_cmd, cwd=self.src_path, check=True, shell=use_shell)

        # Build frontend
        l.info("Building frontend (pnpm build)...")
        subprocess.run(build_cmd, cwd=self.src_path, check=True, shell=use_shell)

        # Check build output
        src_dist = self.src_path / "dist"
        if not src_dist.exists():
            raise Exception("Build finished but 'dist' folder not found in source.")

        # Copy to plugin root dist
        if self.dist_path.exists():
            shutil.rmtree(self.dist_path)

        shutil.copytree(src_dist, self.dist_path)
        l.info(f"Build artifacts copied to {self.dist_path}")

    def _get_latest_download_url(self) -> str:
        api_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"
        l.info(f"Fetching latest release info from: {api_url}")

        with urllib.request.urlopen(api_url) as response:
            if response.status != 200:
                raise Exception(f"GitHub API returned status {response.status}")

            data = json.loads(response.read().decode('utf-8'))
            tag_name = data.get("tag_name", "unknown")
            l.info(f"Latest release tag found: {tag_name}")

            for asset in data.get("assets", []):
                if asset["name"] == ASSET_NAME:
                    return asset["browser_download_url"]

            raise Exception(f"Asset '{ASSET_NAME}' not found in the latest release.")

    def _download_release_dist(self):
        """备用方案：直接下载编译好的 dist.zip"""
        zip_path = self.plugin_dir / "dist.zip"
        try:
            if self.dist_path.exists():
                shutil.rmtree(self.dist_path)

            download_url = self._get_latest_download_url()
            l.info(f"Downloading pre-built dist from: {download_url}")

            self._download_file(download_url, zip_path)

            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(self.plugin_dir)
            l.info("Pre-built dist extraction completed.")

        except Exception as e:
            l.error(f"Failed to download release dist: {e}")
        finally:
            if zip_path.exists():
                zip_path.unlink()

    def _download_file(self, url: str, target: Path):
        opener = urllib.request.build_opener()
        opener.addheaders = [('User-agent', 'Mozilla/5.0')]
        urllib.request.install_opener(opener)
        urllib.request.urlretrieve(url, target)

    def _register_routes(self):
        if not self.dist_path.exists():
            l.error(f"Dist folder missing. Frontend routes will not be registered.")
            return

        self.mount(
            path="/",
            app=StaticFiles(directory=self.dist_path, html=True),
            name="frontend_static"
        )

        async def root():
            return FileResponse(self.dist_path / "index.html")

        self.add_route(
            path='/',
            endpoint=root,
            methods=['GET'],
            tags=['frontend_plugin'],
            name='frontend_plugin_root',
            override=True
        )
