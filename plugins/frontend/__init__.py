# coding: utf-8

import zipfile
import urllib.request
import json
from pathlib import Path
from fastapi import Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger as l

from plugin import PluginBase, PluginMetadata

# GitHub 仓库信息
REPO_OWNER = "sleepy-project"
REPO_NAME = "sleepy-frontend"
ASSET_NAME = "dist.zip"

class Plugin(PluginBase):
    """
    Frontend Plugin with Auto-Download from Latest Release
    """

    def __init__(self, metadata: PluginMetadata):
        super().__init__(metadata)
        
        self.plugin_dir = Path(__file__).parent.resolve()
        self.dist_path = self.plugin_dir / "dist"
        
        # 1. 检查并下载
        self._check_and_download_dist()
        
        # 2. 注册路由
        self._register_routes()

    def on_load(self):
        l.info(f'{self.metadata.name} plugin loaded!')

    def on_unload(self):
        l.info(f'{self.metadata.name} plugin unloaded!')

    def _get_latest_download_url(self) -> str:
        """
        通过 GitHub API 获取最新 Release 中 dist.zip 的真实下载链接
        """
        api_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"
        l.info(f"Fetching latest release info from: {api_url}")

        try:
            # 发送请求获取 JSON
            with urllib.request.urlopen(api_url) as response:
                if response.status != 200:
                    raise Exception(f"GitHub API returned status {response.status}")
                
                data = json.loads(response.read().decode('utf-8'))
                
                # 打印一下找到的版本，方便调试
                tag_name = data.get("tag_name", "unknown")
                l.info(f"Latest release tag found: {tag_name}")

                # 在 assets 列表中寻找名为 dist.zip 的文件
                for asset in data.get("assets", []):
                    if asset["name"] == ASSET_NAME:
                        return asset["browser_download_url"]
                
                raise Exception(f"Asset '{ASSET_NAME}' not found in the latest release ({tag_name}).")

        except Exception as e:
            l.error(f"Error fetching GitHub release info: {e}")
            raise e

    def _check_and_download_dist(self):
        """
        检查 dist 目录是否存在，不存在则动态获取链接下载并解压
        """
        # 如果目录存在且不为空，跳过
        if self.dist_path.exists() and any(self.dist_path.iterdir()):
            l.info(f"Frontend dist found at: {self.dist_path}")
            return

        zip_path = self.plugin_dir / "dist.zip"

        try:
            # 1. 获取真实下载链接
            download_url = self._get_latest_download_url()
            l.info(f"Downloading frontend from: {download_url}")

            # 2. 下载文件
            # 设置 User-Agent，防止 GitHub API 有时拒绝无 UA 的请求
            opener = urllib.request.build_opener()
            opener.addheaders = [('User-agent', 'Mozilla/5.0')]
            urllib.request.install_opener(opener)
            
            urllib.request.urlretrieve(download_url, zip_path)
            l.info("Download completed. Extracting...")

            # 3. 解压缩
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(self.plugin_dir)
            
            l.info("Extraction completed.")

        except Exception as e:
            l.error(f"Failed to set up frontend: {e}")
            # 出错时尝试清理
            if self.dist_path.exists():
                import shutil
                shutil.rmtree(self.dist_path, ignore_errors=True)
        finally:
            # 清理下载的 zip 文件
            if zip_path.exists():
                zip_path.unlink()

    def _register_routes(self):
        """
        Register plugin routes
        """
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
        