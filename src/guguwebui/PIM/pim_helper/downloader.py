import logging
import os
import shutil
import uuid

import requests


class ReleaseDownloader:
    """发布下载器"""

    def __init__(self, server=None, pim_helper=None):
        self.server = server
        self.pim_helper = pim_helper
        self.logger = logging.getLogger('PIM.Downloader')
        self.session = requests.Session()
        # 设置默认 User-Agent
        self.session.headers.update({
            'User-Agent': 'MCDR-PIM-Downloader/1.0'
        })

    def download(self, url: str, target_path: str, timeout: int = 30) -> bool:
        """下载文件到指定路径"""
        try:
            temp_dir = None
            if self.pim_helper:
                temp_dir = self.pim_helper.get_temp_dir()
            else:
                temp_dir = os.path.join(os.getcwd(), '.pim_temp')

            os.makedirs(temp_dir, exist_ok=True)
            temp_filename = f"download_{str(uuid.uuid4())}.tmp"
            temp_path = os.path.join(temp_dir, temp_filename)

            with self.session.get(url, stream=True, timeout=timeout) as r:
                r.raise_for_status()
                with open(temp_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)

            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            if os.path.exists(target_path):
                os.remove(target_path)
            shutil.move(temp_path, target_path)
            return True
        except Exception as e:
            self.logger.error(f"下载文件失败: {e}, URL: {url}")
            if 'temp_path' in locals() and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
            return False
