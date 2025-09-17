import platform
import re
import shutil
import time
from pathlib import Path

import git  # 确保 gitpython 已安装
import requests
import semver
from PySide6.QtCore import (Signal, QThread)

from app.models.config.global_config import global_config
from app.models.config.resource_config import ResourceConfig
from app.models.logging.log_manager import log_manager
from app.utils.notification_manager import notification_manager

# 获取应用程序日志记录器
logger = log_manager.get_app_logger()

class UpdateChecker(QThread):
    """资源更新检查线程"""
    # 信号定义
    update_found = Signal(str, str, str, str,str)  # resource_name, latest_version, current_version, download_url, update_type
    update_not_found = Signal(str)  # resource_name
    check_failed = Signal(str, str)  # resource_name, error_message
    check_completed = Signal(int, int)  # total_checked, updates_found

    def __init__(self, resources: ResourceConfig, single_mode=False):
        """
        初始化更新检查线程

        Args:
            resources: 单个资源或资源列表
            single_mode: 是否为单资源检查模式
        """
        super().__init__()
        self.resources = [resources] if single_mode else resources
        self.single_mode = single_mode
        # 注意：现在在循环内部获取更新方法，因为它可能对每个资源都不同
        self.mirror_base_url = "https://mirrorchyan.com/api"
        self.github_api_url = "https://api.github.com"
        self.is_cancelled = False
        logger.debug(f"UpdateChecker initialized. Single mode: {single_mode}. Resources to check: {len(self.resources)}.")

    def run(self):
        """执行更新检查"""
        updates_found = 0
        logger.debug("UpdateChecker thread started.")
        for resource in self.resources:
            if self.is_cancelled:
                logger.info("Update check was cancelled.")
                break
            try:
                logger.debug(f"Checking updates for resource: '{resource.resource_name}'.")
                # 动态获取每个资源的更新方法和频道
                app_config = global_config.get_app_config()
                update_method = app_config.get_resource_update_method(resource.resource_name)
                update_channel = app_config.get_resource_update_channel(resource.resource_name)
                logger.debug(f"Update method: '{update_method}', Update channel: '{update_channel}'.")

                if update_method.lower() == "mirrorchyan":
                    update_result = self._check_mirror_update(resource, update_channel)
                else:
                    update_result = self._check_github_update(resource, update_channel)

                if update_result:
                    updates_found += 1
            except Exception as e:
                logger.error(f"检查资源 {resource.resource_name} 更新时发生未知错误: {str(e)}")
                if self.single_mode:
                    self.check_failed.emit(resource.resource_name, str(e))

        if not self.single_mode:
            logger.info(f"Update check completed. Total checked: {len(self.resources)}, Updates found: {updates_found}.")
            self.check_completed.emit(len(self.resources), updates_found)
        logger.debug("UpdateChecker thread finished.")

    def cancel(self):
        """取消更新检查"""
        self.is_cancelled = True

    def _check_mirror_update(self, resource: ResourceConfig, channel: str):
        """检查 Mirror 酱更新 (已修改，接收 channel 参数)"""
        rid = resource.mirror_update_service_id
        logger.debug(f"Checking MirrorChyan update for '{resource.resource_name}' with service ID '{rid}'.")
        if not rid:
            if self.single_mode:
                self.check_failed.emit(resource.resource_name, "该资源没有mirror酱更新途径")
            return False

        cdk = global_config.get_app_config().CDK if hasattr(global_config.get_app_config(), 'CDK') else ""

        # 使用传入的 channel 参数
        api_url = f"{self.mirror_base_url}/resources/{rid}/latest"
        params = {
            "current_version": resource.resource_version,
            "cdk": cdk,
            "user_agent": "MaaYYsGUI",
            "channel": channel,  # 使用传入的频道
            "os": platform.system().lower(),
            "arch": platform.machine().lower(),
        }

        log_params = params.copy()
        log_params["cdk"] = "***"
        logger.debug(f"检查资源:{resource.resource_name}更新,api_url:{api_url},params:{log_params}")

        try:
            response = requests.get(api_url, params=params)
            logger.debug(f"MirrorChyan API response for '{resource.resource_name}': Status {response.status_code}, Body: {response.text}")

            # 错误码与说明映射
            error_map = {
                1001: "INVALID_PARAMS: 参数不正确",
                7001: "KEY_EXPIRED: CDK 已过期",
                7002: "KEY_INVALID: CDK 错误",
                7003: "RESOURCE_QUOTA_EXHAUSTED: CDK 今日下载次数已达上限",
                7004: "KEY_MISMATCHED: CDK 类型和待下载的资源不匹配",
                8001: "RESOURCE_NOT_FOUND: 对应架构和系统下的资源不存在",
                8002: "INVALID_OS: 错误的系统参数",
                8003: "INVALID_ARCH: 错误的架构参数",
                8004: "INVALID_CHANNEL: 错误的更新通道参数",
                1: "UNDIVIDED: 未区分的业务错误",
            }

            # 处理非 200 状态码
            if response.status_code != 200:
                self.check_failed.emit(resource.resource_name, f"API返回错误 ({response.status_code})")
                return False

            # 解析返回数据
            result = response.json()
            logger.info(result)
            # 处理错误码
            error_code = result.get("code")
            if error_code is not None and error_code != 0:
                if error_code > 0:
                    detail = error_map.get(error_code, result.get("msg", "未知业务错误"))
                    logger.warning(f"MirrorChyan API returned business error for '{resource.resource_name}': {detail} (Code: {error_code})")
                    if self.single_mode:
                        self.check_failed.emit(resource.resource_name, f"业务错误 ({error_code}): {detail}")
                else:
                    if self.single_mode:
                        self.check_failed.emit(resource.resource_name, "意料之外的严重错误，请联系技术支持")
                return False

            # 提取版本信息
            data = result.get("data", {})
            latest_version = data.get("version_name", "")
            download_url = data.get("url", "")
            update_type = data.get("update_type", "full")
            logger.debug(f"Parsed update data: version='{latest_version}', url='{download_url}', type='{update_type}'.")

            if latest_version and latest_version != resource.resource_version:
                # 发现新版本
                logger.info(f"New version found for '{resource.resource_name}': {latest_version} (current: {resource.resource_version}).")
                self.update_found.emit(
                    resource.resource_name,
                    latest_version,
                    resource.resource_version,
                    download_url,
                    update_type
                )
                return True
            else:
                logger.info(f"Resource '{resource.resource_name}' is up to date.")
                if self.single_mode: self.update_not_found.emit(resource.resource_name)
                return False
        except Exception as e:
            if self.single_mode: self.check_failed.emit(resource.resource_name, f"检查更新异常: {str(e)}")
            return False

    def _check_github_update(self, resource: ResourceConfig, channel: str):
        """
        【已重写】检查 GitHub 更新。
        通过 GitHub API 获取仓库的所有标签 (tags)，并根据 SemVer 规范和更新频道进行比较。
        """
        logger.info(f"正在以 '{channel}' 频道为资源 '{resource.resource_name}' 检查 GitHub 更新...")

        repo_url = resource.resource_rep_url
        if not repo_url or "github.com" not in repo_url:
            if self.single_mode: self.check_failed.emit(resource.resource_name, "未配置有效的 GitHub 仓库 URL")
            return False

        try:
            owner_repo = repo_url.rstrip("/").split("github.com/")[1].replace(".git", "")
            api_url = f"{self.github_api_url}/repos/{owner_repo}/tags"
            logger.debug(f"Constructed GitHub API URL: {api_url}")
            headers = {"Accept": "application/vnd.github.v3+json"}

            # 尝试使用配置中的 GitHub Token
            github_token = global_config.app_config.github_token
            if github_token:
                logger.debug("Using configured GitHub token for API request.")
                headers["Authorization"] = f"token {github_token}"

            response = requests.get(api_url, headers=headers)
            logger.debug(f"GitHub API response for '{resource.resource_name}': Status {response.status_code}")

            if response.status_code == 403:
                msg = "GitHub API 速率超限。请配置个人访问令牌以提高速率。"
                if self.single_mode: self.check_failed.emit(resource.resource_name, msg)
                return False
            if response.status_code != 200:
                msg = f"GitHub API 返回错误 ({response.status_code})"
                if self.single_mode: self.check_failed.emit(resource.resource_name, msg)
                return False

            tags = response.json()
            if not isinstance(tags, list):
                if self.single_mode: self.check_failed.emit(resource.resource_name, "未能获取有效的标签列表")
                return False
            logger.debug(f"Received {len(tags)} tags from GitHub API.")

            valid_tags = []
            for tag in tags:
                tag_name = tag.get("name", "").lstrip("v")
                try:
                    version_info = semver.VersionInfo.parse(tag_name)
                    valid_tags.append((version_info, tag))
                except ValueError:
                    logger.debug(f"Skipping non-SemVer tag: {tag.get('name')}")

            if not valid_tags:
                if self.single_mode: self.check_failed.emit(resource.resource_name,
                                                            "仓库中未找到任何有效的 SemVer 版本标签")
                return False
            logger.debug(f"Found {len(valid_tags)} valid SemVer tags.")

            # 按版本号从高到低排序
            valid_tags.sort(key=lambda item: item[0], reverse=True)

            latest_tag_data = None
            if channel == "stable":
                # 稳定版频道：寻找最新的、非预发布的版本
                logger.debug("Searching for the latest stable (non-prerelease) version.")
                for version_info, tag_data in valid_tags:
                    if version_info.prerelease is None:
                        latest_tag_data = tag_data
                        logger.info(f"稳定版频道找到最新版本: {latest_tag_data.get('name')}")
                        break
            else:  # beta 和 alpha 频道
                # 测试版/开发版频道：直接取最新的版本，包括预发布版
                logger.debug(f"Searching for the latest version in '{channel}' channel (including prereleases).")
                latest_tag_data = valid_tags[0][1]
                logger.info(f"'{channel}' 频道找到最新版本: {latest_tag_data.get('name')}")

            if not latest_tag_data:
                msg = f"在 '{channel}' 频道中未找到合适的更新"
                logger.warning(msg)
                if self.single_mode: self.check_failed.emit(resource.resource_name, msg)
                return False

            latest_version_str = latest_tag_data.get("name", "").lstrip("v")
            current_version_str = resource.resource_version.lstrip("v")
            logger.debug(f"Comparing versions - Latest: '{latest_version_str}', Current: '{current_version_str}'.")

            # --- 版本比较和信号发射 ---
            if semver.compare(latest_version_str, current_version_str) > 0:
                logger.info(
                    f"发现新版本: {resource.resource_name} (当前: {current_version_str}, 最新: {latest_version_str})")
                # 对于GitHub源，download_url现在是zip包地址，作为无法使用git时的备用方案
                download_url = latest_tag_data.get("zipball_url", "")
                logger.debug(f"Update download URL (fallback): {download_url}")
                self.update_found.emit(resource.resource_name, latest_version_str, resource.resource_version,
                                       download_url, "full")
                return True
            else:
                logger.info(f"资源 '{resource.resource_name}' 已是最新版本 ({current_version_str})")
                if self.single_mode: self.update_not_found.emit(resource.resource_name)
                return False

        except Exception as e:
            logger.error(f"检查 GitHub 更新时出错: {str(e)}")
            if self.single_mode: self.check_failed.emit(resource.resource_name, f"检查 GitHub 更新时出错: {str(e)}")
            return False


class UpdateDownloader(QThread):
    """更新下载线程"""
    # 信号定义
    progress_updated = Signal(str, float, float)  # resource_name, progress, speed
    download_completed = Signal(str, str, object)  # resource_name, file_path, resource/data
    download_failed = Signal(str, str)  # resource_name, error_message

    def __init__(self, resource_name, url, output_dir, data=None, resource=None, version=None):
        """
        初始化下载线程
        """
        super().__init__()
        self.resource_name = resource_name
        self.url = url
        self.output_dir = Path(output_dir)
        self.data = data
        self.resource = resource
        self.version = version or "1.0.0"
        self.is_cancelled = False
        logger.debug(f"UpdateDownloader initialized for '{resource_name}' to version '{self.version}'.")

    def run(self):
        """执行下载任务"""
        logger.debug(f"Downloader thread started for '{self.resource_name}'. URL: {self.url}")
        try:
            if not self.url:
                raise ValueError("下载 URL 为空")

            # 创建输出文件名
            filename = f"{self.resource_name}_{self.version}.zip"
            output_path = self.output_dir / filename
            logger.debug(f"Download destination path: {output_path}")
            self.output_dir.mkdir(parents=True, exist_ok=True)

            # 下载文件
            headers = {}
            github_token = global_config.app_config.github_token
            if "api.github.com" in self.url and github_token:
                logger.debug("Using GitHub token for download request.")
                headers["Authorization"] = f"token {github_token}"

            response = requests.get(self.url, stream=True, headers=headers)
            response.raise_for_status()
            logger.debug(f"Download request returned status {response.status_code}.")

            total_size = int(response.headers.get('content-length', 0)) or 1024 * 1024  # 默认 1MB
            chunk_size = max(4096, total_size // 100)
            logger.debug(f"Total download size: {total_size} bytes. Chunk size: {chunk_size} bytes.")

            with open(output_path, 'wb') as f:
                downloaded = 0
                last_update_time = time.time()

                for chunk in response.iter_content(chunk_size=chunk_size):
                    if self.is_cancelled:
                        f.close()
                        if output_path.exists():
                            logger.info(f"Download for '{self.resource_name}' cancelled. Deleting partial file.")
                            output_path.unlink()
                        return

                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        # 计算进度和速度
                        progress = (downloaded / total_size) * 100
                        current_time = time.time()
                        elapsed = current_time - last_update_time

                        if elapsed >= 0.5:
                            speed_bytes_per_sec = len(chunk) / elapsed
                            speed_mb_per_sec = speed_bytes_per_sec / 1024 / 1024
                            self.progress_updated.emit(self.resource_name, progress, speed_mb_per_sec)
                            last_update_time = time.time()

            logger.info(f"Successfully downloaded '{self.resource_name}' to '{output_path}'.")
            # 发送完成信号
            result_data = self.resource if self.resource else self.data
            if self.resource:
                logger.debug(f"Attaching temporary version '{self.version}' to resource object for installer.")
                setattr(self.resource, 'temp_version', self.version)
            self.download_completed.emit(self.resource_name, str(output_path), result_data)

        except Exception as e:
            logger.error(f"下载资源 {self.resource_name} 失败: {str(e)}")
            self.download_failed.emit(self.resource_name, str(e))

    def cancel(self):
        """取消下载"""
        self.is_cancelled = True


class GitInstallerThread(QThread):
    """
    在工作线程中通过 Git 克隆或 API 下载安装新资源的线程。
    """
    # 信号： 进度更新(状态文本), 安装成功(资源名称), 安装失败(错误信息)
    progress_updated = Signal(str)
    install_succeeded = Signal(str)
    install_failed = Signal(str)

    def __init__(self, repo_url, ref, parent=None):
        super().__init__(parent)
        self.repo_url = repo_url
        self.ref = ref
        self.repo_name = self._get_repo_name_from_url(repo_url)
        logger.debug(f"GitInstallerThread initialized for repo '{self.repo_url}' at ref '{self.ref}'.")

    def run(self):
        """线程主执行函数"""
        logger.debug(f"GitInstallerThread started for '{self.repo_name}'.")
        try:
            # 准备路径
            temp_dir = Path("assets/temp")
            resource_dir = Path("assets/resource")
            temp_dir.mkdir(parents=True, exist_ok=True)
            resource_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Paths prepared. Temp: '{temp_dir}', Resource: '{resource_dir}'.")

            final_path = resource_dir / self.repo_name
            if final_path.exists():
                raise FileExistsError(f"目标目录 'assets/resource/{self.repo_name}' 已存在。")

            # 检查 Git 环境并选择安装方式
            if self._is_git_installed():
                logger.info(f"Git executable found. Cloning '{self.repo_name}' via Git.")
                self.progress_updated.emit("Git 克隆中...")
                self._clone_with_git(temp_dir, resource_dir)
            else:
                logger.warning("Git executable not found in PATH. Falling back to API ZIP download.")
                notification_manager.show_info("未检测到 Git 环境，将使用 API 下载。")
                self.progress_updated.emit("API 下载中...")
                self._download_zip_from_github(temp_dir, resource_dir)

            logger.info(f"Successfully installed '{self.repo_name}' to '{final_path}'.")
            self.install_succeeded.emit(self.repo_name)

        except Exception as e:
            logger.error(f"Failed to install '{self.repo_name}': {e}")
            self.install_failed.emit(str(e))
        finally:
            # 清理临时的下载目录
            logger.debug(f"Cleaning up temporary files for '{self.repo_name}'.")
            shutil.rmtree(temp_dir / self.repo_name, ignore_errors=True)
            shutil.rmtree(temp_dir / "extracted", ignore_errors=True)
            zip_file = temp_dir / f"{self.repo_name}.zip"
            if zip_file.exists():
                zip_file.unlink()
            logger.debug("GitInstallerThread finished.")

    def _is_git_installed(self):
        """检查系统中是否安装了 Git 并可在 PATH 中找到"""
        git_path = shutil.which('git')
        logger.debug(f"Checking for git executable. Found at: {git_path}")
        return git_path is not None

    def _get_repo_name_from_url(self, url):
        """从 GitHub URL 中解析仓库名称"""
        name = url.split('/')[-1]
        if name.endswith('.git'):
            name = name[:-4]
        return name

    def _clone_with_git(self, temp_dir, resource_dir):
        """使用 GitPython 克隆仓库"""
        temp_clone_path = temp_dir / self.repo_name
        if temp_clone_path.exists():
            shutil.rmtree(temp_clone_path)

        # 克隆仓库
        logger.debug(f"Cloning '{self.repo_url}' (branch: {self.ref}) to '{temp_clone_path}'.")
        git.Repo.clone_from(self.repo_url, temp_clone_path, branch=self.ref, depth=1)

        # 移动到最终目录
        final_path = resource_dir / self.repo_name
        logger.debug(f"Moving cloned repository from '{temp_clone_path}' to '{final_path}'.")
        shutil.move(str(temp_clone_path), str(final_path))

    def _download_zip_from_github(self, temp_dir, resource_dir):
        """从 GitHub API 下载并解压 ZIP 压缩包"""
        parts = self.repo_url.split('github.com/')[1].split('/')
        owner, repo_name_git = parts[0], parts[1].replace('.git', '')

        zip_url = f"https://api.github.com/repos/{owner}/{repo_name_git}/zipball/{self.ref}"
        temp_zip_path = temp_dir / f"{self.repo_name}.zip"
        logger.debug(f"Downloading ZIP from API: {zip_url}")

        headers = {}
        github_token = global_config.app_config.github_token
        if github_token:
            logger.debug("Using GitHub token for ZIP download.")
            headers["Authorization"] = f"token {github_token}"
        # 下载
        with requests.get(zip_url, stream=True, timeout=60, headers=headers) as r:
            r.raise_for_status()
            with open(temp_zip_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        logger.debug(f"ZIP file downloaded to '{temp_zip_path}'.")

        # 解压
        temp_extract_path = temp_dir / "extracted"
        if temp_extract_path.exists():
            shutil.rmtree(temp_extract_path)
        logger.debug(f"Unpacking archive to '{temp_extract_path}'.")
        shutil.unpack_archive(temp_zip_path, temp_extract_path)

        # GitHub 的压缩包解压后会有一个带 commit hash 的目录名，需要找到它
        unzipped_folder = next(temp_extract_path.iterdir(), None)
        if not unzipped_folder or not unzipped_folder.is_dir():
            raise FileNotFoundError("解压失败或未找到解压后的目录。")
        logger.debug(f"Found extracted folder: '{unzipped_folder}'.")

        # 移动并重命名到最终目录
        final_path = resource_dir / self.repo_name
        logger.debug(f"Moving extracted folder from '{unzipped_folder}' to '{final_path}'.")
        shutil.move(str(unzipped_folder), str(final_path))