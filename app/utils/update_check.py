import platform
import re
import time
from pathlib import Path

import time
from pathlib import Path

import requests
import semver
from PySide6.QtCore import QThread, Signal

from app.models.config.global_config import global_config
from app.models.logging.log_manager import log_manager, app_logger

# 获取应用程序日志记录器
logger = log_manager.get_app_logger()

# 平台对应的资源文件名匹配规则
platform_patterns = {
    "windows": [r"windows.*\.zip$", r".*win.*\.zip$", r"\.zip$"],
    "linux": [r"linux.*\.tar\.gz$", r".*linux.*\.tar\.gz$", r"\.tar\.gz$"],
    "macos-arm64": [r"macos-arm64.*\.tar\.gz$", r".*arm64.*\.zip$", r".*arm64.*\.tar\.gz$"],
    "macos-x64": [r"macos-x64.*\.tar\.gz$", r".*x64.*\.zip$", r".*x64.*\.tar\.gz$"]
}


class UpdateChecker(QThread):
    """资源更新检查线程"""
    # 信号定义
    update_found = Signal(str, str, str, str,
                          str)  # resource_name, latest_version, current_version, download_url, update_type
    update_not_found = Signal(str)  # resource_name
    check_failed = Signal(str, str)  # resource_name, error_message
    check_completed = Signal(int, int)  # total_checked, updates_found

    def __init__(self, resources, single_mode=False):
        """
        初始化更新检查线程

        Args:
            resources: 单个资源或资源列表
            single_mode: 是否为单资源检查模式
        """
        super().__init__()
        self.resources = [resources] if single_mode else resources
        self.single_mode = single_mode
        self.update_method = global_config.get_app_config().update_method
        self.mirror_base_url = "https://mirrorchyan.com/api"
        self.github_api_url = "https://api.github.com"
        self.is_cancelled = False
        self.platform_patterns = platform_patterns

    def run(self):
        """执行更新检查"""
        updates_found = 0
        for resource in self.resources:
            if self.is_cancelled:
                break
            try:
                if self.update_method == "MirrorChyan":
                    update_result = self._check_mirror_update(resource)
                else:
                    update_result = self._check_github_update(resource)
                updates_found += 1 if update_result else 0
            except Exception as e:
                logger.error(f"检查资源 {resource.resource_name} 更新时出错: {str(e)}")
                if self.single_mode:
                    self.check_failed.emit(resource.resource_name, str(e))

        if not self.single_mode:
            self.check_completed.emit(len(self.resources), updates_found)

    def cancel(self):
        """取消更新检查"""
        self.is_cancelled = True

    def _check_mirror_update(self, resource):
        """检查 Mirror 酱更新"""
        # 获取资源更新服务 ID
        rid = resource.resource_update_service_id
        if not rid:
            if self.single_mode:
                self.check_failed.emit(resource.resource_name, "没有配置更新源")
            return False

        # 获取 CDK
        cdk = global_config.get_app_config().CDK if hasattr(global_config.get_app_config(), 'CDK') else ""

        # 设置更新通道
        channel = "beta" if global_config.get_app_config().receive_beta_update else "stable"

        # 构造 API URL 和参数
        api_url = f"{self.mirror_base_url}/resources/{rid}/latest"
        params = {
            "current_version": resource.resource_version,
            "cdk": cdk,
            "user_agent": "MaaYYsGUI",
            "channel": channel,
            "os": platform.system().lower(),
            "arch": platform.machine().lower(),
        }

        # 记录日志时隐藏 CDK
        log_params = params.copy()
        log_params["cdk"] = "***"
        logger.debug(f"检查资源:{resource.resource_name}更新,api_url:{api_url},params:{log_params}")

        try:
            response = requests.get(api_url, params=params)
            logger.debug(f"资源检查响应:{response}")

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
                error_message = f"API返回错误 ({response.status_code})"

                try:
                    error_data = response.json()
                    error_code = error_data.get("code")
                    error_msg = error_data.get("msg", "")

                    if error_code is not None:
                        error_detail = error_map.get(error_code, error_msg or "未知业务错误")
                        error_message = f"业务错误 ({error_code}): {error_detail}"
                except:
                    pass

                if self.single_mode:
                    self.check_failed.emit(resource.resource_name, error_message)
                return False

            # 解析返回数据
            result = response.json()
            logger.info(result)
            # 处理错误码
            error_code = result.get("code")
            if error_code is not None and error_code != 0:
                if error_code > 0:
                    detail = error_map.get(error_code, result.get("msg", "未知业务错误"))
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

            if latest_version and latest_version != resource.resource_version:
                # 发现新版本
                self.update_found.emit(
                    resource.resource_name,
                    latest_version,
                    resource.resource_version,
                    download_url,
                    update_type
                )
                return True
            elif self.single_mode:
                # 未发现新版本
                self.update_not_found.emit(resource.resource_name)
                return False

        except Exception as e:
            if self.single_mode:
                self.check_failed.emit(resource.resource_name, f"检查更新异常: {str(e)}")
            return False

        return False

    def _check_github_update(self, resource):
        """
        检查 GitHub 更新。
        通过解析 SemVer 标签来区分 stable 和 beta 更新。
        """
        channel = "beta" if global_config.get_app_config().receive_beta_update else "stable"
        logger.info(f"正在以 '{channel}' 通道为资源 '{resource.resource_name}' 检查 GitHub 更新...")

        system = platform.system().lower()
        machine = platform.machine().lower()

        platform_key = (
            "macos-x64" if system == "darwin" and machine not in ("arm64", "aarch64") else
            "macos-arm64" if system == "darwin" else
            "linux" if system == "linux" else
            "windows"
        )

        repo_url = resource.resource_rep_url
        if not repo_url or "github.com" not in repo_url:
            if self.single_mode: self.check_failed.emit(resource.resource_name, "未配置有效的GitHub仓库URL")
            return False

        try:
            owner_repo = repo_url.rstrip("/").split("github.com/")[1]
            api_url = f"{self.github_api_url}/repos/{owner_repo}/releases"
            headers = {"Accept": "application/vnd.github.v3+json"}

            response = requests.get(api_url, headers=headers)

            if response.status_code == 403:
                if self.single_mode: self.check_failed.emit(resource.resource_name, "请求被拒绝 (403)：API速率限制")
                return False
            if response.status_code != 200:
                if self.single_mode: self.check_failed.emit(resource.resource_name,
                                                            f"GitHub API返回错误 ({response.status_code})")
                return False

            releases = response.json()
            if not isinstance(releases, list):
                if self.single_mode: self.check_failed.emit(resource.resource_name, "未能获取有效的版本列表")
                return False

            valid_releases = []
            for release in releases:
                tag_name = release.get("tag_name", "").lstrip("v")
                try:
                    # 尝试将tag解析为SemVer对象
                    version_info = semver.VersionInfo.parse(tag_name)
                    # 将(版本对象, 原始release数据)存入列表
                    valid_releases.append((version_info, release))
                except ValueError:
                    logger.debug(f"已跳过非SemVer标签: {release.get('tag_name')}")

            if not valid_releases:
                if self.single_mode: self.check_failed.emit(resource.resource_name, "未找到任何有效的SemVer版本标签")
                return False

            # 按版本号从高到低排序
            valid_releases.sort(key=lambda item: item[0], reverse=True)

            # --- 根据通道选择版本 ---
            target_release_data = None
            if channel == "beta":
                # Beta通道：直接取最新的版本
                target_release_data = valid_releases[0][1]
                logger.info(f"Beta通道找到最新版本: {target_release_data.get('tag_name')}")
            else:
                # Stable通道：寻找最新的、非预发布版本
                for version_info, release_data in valid_releases:
                    if version_info.prerelease is None:
                        target_release_data = release_data
                        logger.info(f"Stable通道找到最新版本: {target_release_data.get('tag_name')}")
                        break

            if not target_release_data:
                msg = f"在 '{channel}' 通道中未找到合适的更新"
                logger.warning(msg)
                if self.single_mode: self.check_failed.emit(resource.resource_name, msg)
                return False

            # --- 确定下载链接和版本号 ---
            latest_version = target_release_data.get("tag_name", "").lstrip("v")
            download_url = ""
            download_assets = target_release_data.get("assets", [])

            if platform_key in self.platform_patterns:
                for pattern in self.platform_patterns[platform_key]:
                    for asset in download_assets:
                        if re.search(pattern, asset.get("name", ""), re.IGNORECASE):
                            download_url = asset.get("browser_download_url", "")
                            break
                    if download_url: break

            if not download_url and download_assets:
                download_url = download_assets[0].get("browser_download_url", "")
            if not download_url:
                download_url = target_release_data.get("zipball_url", "")

            # --- 版本比较和信号发射 ---
            if semver.compare(latest_version, resource.resource_version.lstrip("v")) > 0:
                logger.info(
                    f"发现新版本: {resource.resource_name} (当前: {resource.resource_version}, 最新: {latest_version})")
                self.update_found.emit(resource.resource_name, latest_version, resource.resource_version, download_url,
                                       "full")
                return True
            else:
                if self.single_mode: self.update_not_found.emit(resource.resource_name)
                return False

        except Exception as e:
            logger.error(f"检查GitHub更新时出错: {str(e)}")
            if self.single_mode: self.check_failed.emit(resource.resource_name, f"检查GitHub更新时出错: {str(e)}")
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

        Args:
            resource_name: 资源名称
            url: 下载 URL
            output_dir: 输出目录
            data: 新资源的数据（添加新资源时使用）
            resource: 资源对象（更新现有资源时使用）
            version: 版本号
        """
        super().__init__()
        self.resource_name = resource_name
        self.url = url
        self.output_dir = Path(output_dir)
        self.data = data
        self.resource = resource
        self.version = version or "1.0.0"
        self.is_cancelled = False

    def run(self):
        """执行下载任务"""
        try:
            if not self.url:
                raise ValueError("下载 URL 为空")

            # 创建输出文件名
            filename = f"{self.resource_name}_{self.version}.zip"
            output_path = self.output_dir / filename

            # 下载文件
            response = requests.get(self.url, stream=True)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0)) or 1024 * 1024  # 默认 1MB
            chunk_size = max(4096, total_size // 100)

            with open(output_path, 'wb') as f:
                downloaded = 0
                last_update_time = time.time()

                for chunk in response.iter_content(chunk_size=chunk_size):
                    if self.is_cancelled:
                        f.close()
                        if output_path.exists():
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
                            speed = (chunk_size / 1024 / 1024) / elapsed  # MB/s
                            self.progress_updated.emit(self.resource_name, progress, speed)
                            last_update_time = current_time

            # 发送完成信号
            result_data = self.resource if self.resource else self.data
            self.download_completed.emit(self.resource_name, str(output_path), result_data)

        except Exception as e:
            logger.error(f"下载资源 {self.resource_name} 失败: {str(e)}")
            self.download_failed.emit(self.resource_name, str(e))

    def cancel(self):
        """取消下载"""
        self.is_cancelled = True


