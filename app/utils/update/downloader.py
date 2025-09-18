import time
from pathlib import Path
import requests
from PySide6.QtCore import QThread, Signal

from app.models.config.global_config import global_config
from app.models.logging.log_manager import log_manager
from app.utils.update.models import UpdateInfo

logger = log_manager.get_app_logger()


class UpdateDownloader(QThread):
    """更新下载线程 (只负责下载)"""
    progress_updated = Signal(str, float, float)
    download_completed = Signal(UpdateInfo, str)
    download_failed = Signal(str, str)

    def __init__(self, update_info: UpdateInfo, output_dir: Path):
        super().__init__()
        self.update_info = update_info
        self.output_dir = output_dir
        self.is_cancelled = False
        logger.debug(
            f"UpdateDownloader 已为 '{self.update_info.resource_name}' 初始化，目标版本 '{self.update_info.new_version}'。")

    def run(self):
        resource_name = self.update_info.resource_name
        url = self.update_info.download_url
        version = self.update_info.new_version
        logger.debug(f"下载器线程已为 '{resource_name}' 启动。URL: {url}")

        try:
            if not url:
                raise ValueError("下载 URL 为空")

            filename = f"{resource_name}_{version}.zip"
            output_path = self.output_dir / filename
            self.output_dir.mkdir(parents=True, exist_ok=True)

            headers = {}
            github_token = global_config.app_config.github_token
            if "api.github.com" in url and github_token:
                headers["Authorization"] = f"token {github_token}"

            response = requests.get(url, stream=True, headers=headers, timeout=60)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))
            chunk_size = 8192

            with open(output_path, 'wb') as f:
                downloaded = 0
                start_time = time.time()
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if self.is_cancelled:
                        f.close()
                        if output_path.exists(): output_path.unlink()
                        logger.info(f"'{resource_name}' 的下载任务已被取消。")
                        return

                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        elapsed_time = time.time() - start_time
                        speed = downloaded / elapsed_time if elapsed_time > 0 else 0
                        speed_mb_per_sec = speed / 1024 / 1024
                        progress = (downloaded / total_size) * 100 if total_size > 0 else 0
                        self.progress_updated.emit(resource_name, progress, speed_mb_per_sec)

            logger.info(f"已成功下载 '{resource_name}' 到 '{output_path}'。")
            self.download_completed.emit(self.update_info, str(output_path))

        except Exception as e:
            logger.error(f"下载资源 {resource_name} 失败: {str(e)}")
            self.download_failed.emit(resource_name, str(e))

    def cancel(self):
        self.is_cancelled = True