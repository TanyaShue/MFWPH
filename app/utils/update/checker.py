import platform
import requests
import semver
from PySide6.QtCore import (Signal, QThread)

from app.models.config.global_config import global_config
from app.models.config.resource_config import ResourceConfig
from app.models.logging.log_manager import log_manager
from app.utils.update.models import UpdateInfo, UpdateSource

logger = log_manager.get_app_logger()


class UpdateChecker(QThread):
    """资源更新检查线程 (只负责检查)"""
    update_found = Signal(UpdateInfo)
    update_not_found = Signal(str)
    check_failed = Signal(str, str)
    check_completed = Signal(int, int)

    def __init__(self, resources, single_mode=False):
        super().__init__()
        self.resources = [resources] if single_mode else resources
        self.single_mode = single_mode
        self.mirror_base_url = "https://mirrorchyan.com/api"
        self.github_api_url = "https://api.github.com"
        self.is_cancelled = False
        logger.debug(
            f"UpdateChecker initialized. Single mode: {single_mode}. Resources to check: {len(self.resources)}.")

    def run(self):
        updates_found = 0
        logger.debug("UpdateChecker thread started.")
        for resource in self.resources:
            if self.is_cancelled:
                logger.info("Update check was cancelled.")
                break
            try:
                logger.debug(f"Checking updates for resource: '{resource.resource_name}'.")
                app_config = global_config.get_app_config()
                update_method = app_config.get_resource_update_method(resource.resource_name)
                update_channel = app_config.get_resource_update_channel(resource.resource_name)
                logger.debug(f"Update method: '{update_method}', Update channel: '{update_channel}'.")

                update_result = False
                if update_method.lower() == "mirrorchyan":
                    update_result = self._check_mirror_update(resource, update_channel)
                else:
                    update_result = self._check_github_update(resource, update_channel)

                if update_result:
                    updates_found += 1
            except Exception as e:
                logger.error(f"检查资源 {resource.resource_name} 更新时发生未知错误: {e}", exc_info=True)
                if self.single_mode:
                    self.check_failed.emit(resource.resource_name, str(e))

        if not self.single_mode:
            logger.info(
                f"Update check completed. Total checked: {len(self.resources)}, Updates found: {updates_found}.")
            self.check_completed.emit(len(self.resources), updates_found)
        logger.debug("UpdateChecker thread finished.")

    def cancel(self):
        self.is_cancelled = True

    def _check_mirror_update(self, resource: ResourceConfig, channel: str):
        rid = resource.mirror_update_service_id
        logger.debug(f"Checking MirrorChyan update for '{resource.resource_name}' with service ID '{rid}'.")
        if not rid:
            if self.single_mode: self.check_failed.emit(resource.resource_name, "该资源没有mirror酱更新途径")
            return False

        cdk = global_config.get_app_config().CDK if hasattr(global_config.get_app_config(), 'CDK') else ""

        api_url = f"{self.mirror_base_url}/resources/{rid}/latest"
        params = {"current_version": resource.resource_version, "cdk": cdk, "user_agent": "MaaYYsGUI",
                  "channel": channel, "os": platform.system().lower(), "arch": platform.machine().lower()}
        log_params = params.copy()
        log_params["cdk"] = "***" if cdk else ""
        logger.debug(f"检查资源: {resource.resource_name}, API_URL: {api_url}, PARAMS: {log_params}")

        try:
            response = requests.get(api_url, params=params)
            logger.debug(
                f"MirrorChyan API response for '{resource.resource_name}': Status {response.status_code}, Body: {response.text}")

            try:
                result = response.json()
            except requests.exceptions.JSONDecodeError:
                logger.warning(f"MirrorChyan API did not return valid JSON. Status: {response.status_code}")
                self.check_failed.emit(resource.resource_name, f"API响应格式错误 (Status: {response.status_code})")
                return False

            error_map = {
                1001: "INVALID_PARAMS: 参数不正确", 7001: "KEY_EXPIRED: CDK 已过期",
                7002: "KEY_INVALID: CDK 错误", 7003: "RESOURCE_QUOTA_EXHAUSTED: CDK 今日下载次数已达上限",
                7004: "KEY_MISMATCHED: CDK 类型和待下载的资源不匹配",
                8001: "RESOURCE_NOT_FOUND: 对应架构和系统下的资源不存在",
                8002: "INVALID_OS: 错误的系统参数", 8003: "INVALID_ARCH: 错误的架构参数",
                8004: "INVALID_CHANNEL: 错误的更新通道参数", 1: "UNDIVIDED: 未区分的业务错误",
            }

            error_code = result.get("code")
            if error_code is not None and error_code != 0:
                detail = error_map.get(error_code, result.get("msg", "未知业务错误"))
                logger.warning(
                    f"MirrorChyan API returned business error for '{resource.resource_name}': {detail} (Code: {error_code})")
                if self.single_mode:
                    self.check_failed.emit(resource.resource_name, f"业务错误 ({error_code}): {detail}")
                return False

            data = result.get("data", {})
            latest_version = data.get("version_name", "")
            download_url = data.get("url", "")
            update_type = data.get("update_type", "full")
            logger.debug(
                f"Parsed MirrorChyan data: version='{latest_version}', url='{download_url}', type='{update_type}'.")

            # 【修正】在比较版本前，移除版本号字符串头部的 'v'
            latest_version_str = latest_version.lstrip('v')
            current_version_str = resource.resource_version.lstrip('v')
            logger.debug(f"Comparing versions - Latest: '{latest_version_str}', Current: '{current_version_str}'.")

            # 【修正】使用处理过的、符合 SemVer 规范的字符串进行比较
            if latest_version_str and semver.compare(latest_version_str, current_version_str) > 0:
                logger.info(
                    f"New MirrorChyan version found for '{resource.resource_name}': {latest_version} (current: {resource.resource_version}).")
                update_info = UpdateInfo(
                    resource_name=resource.resource_name, current_version=resource.resource_version,
                    new_version=latest_version,  # 仍然使用带 'v' 的原始版本号创建 UpdateInfo
                    download_url=download_url,
                    update_type=update_type, source=UpdateSource.MIRROR
                )
                self.update_found.emit(update_info)
                return True
            else:
                logger.info(f"Resource '{resource.resource_name}' is up to date (MirrorChyan).")
                if self.single_mode: self.update_not_found.emit(resource.resource_name)
                return False
        except requests.exceptions.RequestException as e:
            logger.error(f"检查 MirrorChyan 更新时发生网络请求异常: {e}", exc_info=True)
            if self.single_mode: self.check_failed.emit(resource.resource_name, f"网络请求失败: {str(e)}")
            return False

    def _check_github_update(self, resource: ResourceConfig, channel: str):
        repo_url = resource.resource_rep_url
        logger.debug(f"Checking GitHub update for '{resource.resource_name}' from repo '{repo_url}'.")
        if not repo_url or "github.com" not in repo_url:
            if self.single_mode: self.check_failed.emit(resource.resource_name, "未配置有效的 GitHub 仓库 URL")
            return False

        try:
            owner_repo = repo_url.rstrip("/").split("github.com/")[1].replace(".git", "")
            api_url = f"{self.github_api_url}/repos/{owner_repo}/tags"
            logger.debug(f"Constructed GitHub API URL: {api_url}")

            headers = {"Accept": "application/vnd.github.v3+json"}
            github_token = global_config.app_config.github_token
            if github_token:
                logger.debug("Using configured GitHub token for API request.")
                headers["Authorization"] = f"token {github_token}"

            response = requests.get(api_url, headers=headers)
            logger.debug(f"GitHub API response for '{resource.resource_name}': Status {response.status_code}")

            if response.status_code != 200:
                msg = f"GitHub API 返回错误 ({response.status_code})"
                logger.warning(f"{msg}. Body: {response.text}")
                if self.single_mode: self.check_failed.emit(resource.resource_name, msg)
                return False

            tags = response.json()
            logger.debug(f"Received {len(tags)} tags from GitHub API.")

            valid_tags = []
            for tag in tags:
                tag_name = tag.get("name", "").lstrip("v")
                try:
                    version_info = semver.VersionInfo.parse(tag_name)
                    valid_tags.append((version_info, tag))
                except ValueError:
                    logger.debug(f"Skipping non-SemVer tag: '{tag.get('name')}'")

            if not valid_tags:
                logger.warning("Repository contains no valid SemVer tags.")
                if self.single_mode: self.check_failed.emit(resource.resource_name,
                                                            "仓库中未找到任何有效的 SemVer 版本标签")
                return False

            logger.debug(f"Found {len(valid_tags)} valid SemVer tags. Sorting...")
            valid_tags.sort(key=lambda item: item[0], reverse=True)

            latest_tag_data = None
            if channel == "stable":
                logger.debug("Searching for the latest stable (non-prerelease) version.")
                for version_info, tag_data in valid_tags:
                    if version_info.prerelease is None:
                        latest_tag_data = tag_data
                        break
            else:
                logger.debug(f"Searching for the latest version in '{channel}' channel (including prereleases).")
                latest_tag_data = valid_tags[0][1]

            if not latest_tag_data:
                msg = f"在 '{channel}' 频道中未找到合适的更新"
                logger.warning(msg)
                if self.single_mode: self.check_failed.emit(resource.resource_name, msg)
                return False

            logger.debug(f"Latest tag selected for channel '{channel}': {latest_tag_data.get('name')}")
            latest_version_str = latest_tag_data.get("name", "").lstrip("v")
            current_version_str = resource.resource_version.lstrip("v")
            logger.debug(f"Comparing versions - Latest: '{latest_version_str}', Current: '{current_version_str}'.")

            if semver.compare(latest_version_str, current_version_str) > 0:
                logger.info(
                    f"New GitHub version found for '{resource.resource_name}': {latest_version_str} (current: {current_version_str}).")
                update_info = UpdateInfo(
                    resource_name=resource.resource_name, current_version=resource.resource_version,
                    new_version=latest_version_str, download_url=latest_tag_data.get("zipball_url", ""),
                    update_type="full", source=UpdateSource.GITHUB
                )
                self.update_found.emit(update_info)
                return True
            else:
                logger.info(f"Resource '{resource.resource_name}' is up to date (GitHub).")
                if self.single_mode: self.update_not_found.emit(resource.resource_name)
                return False
        except requests.exceptions.RequestException as e:
            logger.error(f"检查 GitHub 更新时发生网络请求异常: {e}", exc_info=True)
            if self.single_mode: self.check_failed.emit(resource.resource_name, f"网络请求失败: {str(e)}")
            return False

