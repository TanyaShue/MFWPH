import time

import requests
from PySide6.QtCore import QThread, Signal

from app.models.config.global_config import global_config


class DownloadThread(QThread):
    """Unified thread for downloading resources and updates"""
    progress_updated = Signal(str, float, float)  # resource_name, progress, speed
    download_completed = Signal(str, str, object)  # resource_name, file_path, data/resource
    download_failed = Signal(str, str)  # resource_name, error

    def __init__(self, resource_name, url, output_dir, data=None, resource=None, version=None):
        super().__init__()
        self.resource_name = resource_name
        self.url = url
        self.output_dir = output_dir
        self.data = data
        self.resource = resource
        self.version = version or "1.0.0"
        self.is_cancelled = False

    def run(self):
        try:

            if self.url is None or self.url == "":
                raise RuntimeError("can't download resource,cdk为空或cdk不存在")
            # Create output filename
            filename = f"{self.resource_name}_{self.version}.zip"
            output_path = self.output_dir / filename
            # Download file with progress
            response = requests.get(self.url, stream=True)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0)) or 1024 * 1024  # Default 1MB
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

                        # Calculate progress and speed
                        progress = (downloaded / total_size) * 100
                        current_time = time.time()
                        elapsed = current_time - last_update_time

                        if elapsed >= 0.5:
                            speed = (chunk_size / 1024 / 1024) / elapsed  # MB/s
                            self.progress_updated.emit(self.resource_name, progress, speed)
                            last_update_time = current_time

            # Send completion signal
            result_data = self.resource if self.resource else self.data
            self.download_completed.emit(self.resource_name, str(output_path), result_data)
        except Exception as e:
            self.download_failed.emit(self.resource_name, str(e))

    def cancel(self):
        """Cancel download"""
        self.is_cancelled = True


class UpdateCheckThread(QThread):
    """Thread for checking updates using API or GitHub"""
    update_found = Signal(str, str, str, str)  # resource_name, latest_version, current_version, download_url
    update_not_found = Signal(str)  # resource_name (single mode only)
    check_failed = Signal(str, str)  # resource_name, error_message (single mode only)
    check_completed = Signal(int, int)  # total_checked, updates_found (batch mode only)

    def __init__(self, resources, single_mode=False):
        super().__init__()
        self.resources = [resources] if single_mode else resources
        self.single_mode = single_mode
        self.update_method = global_config.get_app_config().update_method
        # 根据更新方法设置基础URL
        self.mirror_base_url = "https://mirrorchyan.com/api"
        self.github_api_url = "https://api.github.com"

    def run(self):
        updates_found = 0

        for resource in self.resources:
            if self.update_method == "MirrorChyan":
                # 使用Mirror酱API更新检查
                updates_found += self._check_update_mirror(resource)
            else:
                # 使用GitHub更新检查
                updates_found += self._check_update_github(resource)

        # Signal completion in batch mode
        if not self.single_mode:
            self.check_completed.emit(len(self.resources), updates_found)

    def _check_update_mirror(self, resource):
        """使用Mirror酱API检查更新"""
        # 获取资源更新服务ID
        rid = resource.resource_update_service_id
        if not rid:
            if self.single_mode:
                self.check_failed.emit(resource.resource_name, "没有配置更新源")
            return 0

        try:
            # 从全局配置中获取 CDK（如果有配置）
            cdk = global_config.get_app_config().CDK if hasattr(global_config.get_app_config(), 'CDK') else ""

            # 根据测试版设置选择更新通道
            channel = "beta" if global_config.get_app_config().receive_beta_update else "stable"

            # 构造 API URL 与参数
            api_url = f"{self.mirror_base_url}/resources/{rid}/latest"
            params = {
                "current_version": resource.resource_version,
                "cdk": cdk,
                "user_agent": "ResourceDownloader",
                "channel": channel  # 根据配置动态选择通道
            }
            response = requests.get(api_url, params=params)

            # 定义业务逻辑错误码与说明的对应关系
            error_map = {
                1001: "INVALID_PARAMS: 参数不正确，请参考集成文档",
                7001: "KEY_EXPIRED: CDK 已过期",
                7002: "KEY_INVALID: CDK 错误",
                7003: "RESOURCE_QUOTA_EXHAUSTED: CDK 今日下载次数已达上限",
                7004: "KEY_MISMATCHED: CDK 类型和待下载的资源不匹配",
                8001: "RESOURCE_NOT_FOUND: 对应架构和系统下的资源不存在",
                8002: "INVALID_OS: 错误的系统参数",
                8003: "INVALID_ARCH: 错误的架构参数",
                8004: "INVALID_CHANNEL: 错误的更新通道参数",
                1: "UNDIVIDED: 未区分的业务错误，以响应体 JSON 的 msg 为准",
            }

            # 处理非200状态码
            if response.status_code != 200:
                error_message = f"API返回错误 ({response.status_code})"

                # 尝试解析错误响应中的JSON数据
                try:
                    error_data = response.json()
                    error_code = error_data.get("code")
                    error_msg = error_data.get("msg", "")

                    if error_code is not None:
                        # 查找对应的错误描述
                        error_detail = error_map.get(error_code, error_msg or "未知业务错误")
                        error_message = f"业务错误 ({error_code}): {error_detail}"
                except:
                    # 如果无法解析JSON，仅使用HTTP状态码作为错误信息
                    pass

                if self.single_mode:
                    self.check_failed.emit(resource.resource_name, error_message)
                return 0

            # 解析返回的 JSON 数据
            result = response.json()

            # 错误码处理
            error_code = result.get("code")
            # 确保error_code不是None并且不等于0
            if error_code is not None and error_code != 0:
                if error_code > 0:
                    # 业务逻辑错误，根据返回码寻找对应的错误说明
                    detail = error_map.get(error_code, result.get("msg", "未知业务错误，请联系 Mirror 酱技术支持"))
                    if self.single_mode:
                        self.check_failed.emit(resource.resource_name, f"业务错误 ({error_code}): {detail}")
                else:  # 处理error_code < 0的情况
                    # 意料之外的严重错误
                    if self.single_mode:
                        self.check_failed.emit(resource.resource_name,
                                               "意料之外的严重错误，请及时联系 Mirror 酱的技术支持处理")
                return 0

            # 若接口返回成功（code == 0），则从数据中提取版本与下载链接
            data = result.get("data", {})
            latest_version = data.get("version_name", "")
            download_url = data.get("url", "")

            if latest_version and latest_version != resource.resource_version:
                # 检测到新版本，发出更新通知
                self.update_found.emit(
                    resource.resource_name,
                    latest_version,
                    resource.resource_version,
                    download_url
                )
                return 1
            elif self.single_mode:
                # 未检测到新版本，发出没有更新的信号
                self.update_not_found.emit(resource.resource_name)
                return 0

        except Exception as e:
            if self.single_mode:
                self.check_failed.emit(resource.resource_name, f"检查更新异常: {str(e)}")
            return 0

        return 0

    def _check_update_github(self, resource):
        """使用GitHub检查更新"""
        repo_url = resource.resource_rep_url

        if not repo_url or "github.com" not in repo_url:
            if self.single_mode:
                self.check_failed.emit(resource.resource_name, "未配置有效的GitHub仓库URL")
            return 0

        try:
            # 解析GitHub仓库URL
            repo_parts = repo_url.rstrip("/").split("github.com/")
            if len(repo_parts) != 2:
                if self.single_mode:
                    self.check_failed.emit(resource.resource_name, "GitHub仓库URL格式无效")
                return 0

            owner_repo = repo_parts[1]

            # 获取GitHub仓库最新的发布版本
            api_url = f"{self.github_api_url}/repos/{owner_repo}/releases/latest"

            # 设置请求头
            headers = {
                "Accept": "application/vnd.github.v3+json"
            }

            # 发送请求
            response = requests.get(api_url, headers=headers)

            if response.status_code == 404:
                # 尝试获取tags
                api_url = f"{self.github_api_url}/repos/{owner_repo}/tags"
                response = requests.get(api_url, headers=headers)
            # Handle HTTP errors
            if response.status_code == 403:
                error_message = "请求被拒绝 (403)：可能是超出了 API 请求速率限制或缺少认证信息。"
                if self.single_mode:
                    self.check_failed.emit(resource.resource_name, error_message)
                return 0

            if response.status_code != 200:
                if self.single_mode:
                    self.check_failed.emit(resource.resource_name, f"GitHub API返回错误 ({response.status_code})")
                return 0

            result = response.json()

            # 解析返回结果
            if "/releases/latest" in api_url:
                # 处理releases数据
                latest_version = result.get("tag_name", "")
                download_assets = result.get("assets", [])
                if download_assets:
                    # 获取第一个资源的下载URL
                    download_url = download_assets[0].get("browser_download_url", "")
                else:
                    # 如果没有资源，使用zip下载URL
                    download_url = result.get("zipball_url", "")
            else:
                # 处理tags数据
                if not result or not isinstance(result, list):
                    if self.single_mode:
                        self.check_failed.emit(resource.resource_name, "无法找到任何版本标签")
                    return 0

                # 获取最新的tag
                latest_tag = result[0]
                latest_version = latest_tag.get("name", "").lstrip("v")

                # 构建下载URL
                download_url = f"https://github.com/{owner_repo}/archive/refs/tags/{latest_tag.get('name', '')}.zip"

            # 比较版本
            if latest_version and latest_version != resource.resource_version:
                self.update_found.emit(
                    resource.resource_name,
                    latest_version,
                    resource.resource_version,
                    download_url
                )
                return 1
            elif self.single_mode:
                self.update_not_found.emit(resource.resource_name)
                return 0

        except Exception as e:
            if self.single_mode:
                self.check_failed.emit(resource.resource_name, f"检查GitHub更新时出错: {str(e)}")
            return 0

        return 0

