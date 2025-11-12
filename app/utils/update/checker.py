# --- START OF FILE checker.py ---

import platform
import re  # <-- 新增: 导入正则表达式模块
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

    def __init__(self, resources, single_mode=False, channel=None, source=None, target_asset_name=None,
                 force_check=False):
        """
        【已修改】构造函数现在接受一个可选的 'target_asset_name' 参数来查找特定的发布包。
        【已修改】新增 'force_check' 参数，用于强制获取最新版本信息，即使当前版本号相同。
        """
        super().__init__()
        self.resources = [resources] if single_mode else resources
        self.single_mode = single_mode
        self.channel = channel
        self.source = source  # 保存从外部传入的强制更新源
        self.target_asset_name = target_asset_name  # <-- 新增：保存目标资源文件名
        self.force_check = force_check  # <-- 新增：强制检查标志
        self.mirror_base_url = "https://mirrorchyan.com/api"
        self.github_api_url = "https://api.github.com"
        self.is_cancelled = False
        logger.debug(
            f"UpdateChecker 已初始化。单模式: {single_mode}。强制检查: {self.force_check}。待检查资源数: {len(self.resources)}。")

    def run(self):
        updates_found = 0
        logger.debug("UpdateChecker 线程已启动。")
        for resource in self.resources:
            if self.is_cancelled:
                logger.info("更新检查已被取消。")
                break
            try:
                logger.debug(f"正在为资源 '{resource.resource_name}' 检查更新。")
                app_config = global_config.get_app_config()

                update_method = self.source
                if not update_method:
                    update_method = app_config.get_resource_update_method(resource.resource_name)

                update_channel = self.channel
                if not update_channel:
                    update_channel = app_config.get_resource_update_channel(resource.resource_name)

                logger.debug(f"更新方式: '{update_method}', 更新通道: '{update_channel}'。")

                update_result = False
                if update_method and update_method.lower() == "mirrorchyan":
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
                f"更新检查完成。总计检查: {len(self.resources)}, 发现更新: {updates_found}。")
            self.check_completed.emit(len(self.resources), updates_found)
        logger.debug("UpdateChecker 线程已结束。")

    def cancel(self):
        self.is_cancelled = True

    def _check_mirror_update(self, resource: ResourceConfig, channel: str):
        rid = resource.mirror_update_service_id
        logger.debug(f"正在为 '{resource.resource_name}' 检查 MirrorChyan 更新, 服务 ID 为 '{rid}'。")
        if not rid:
            if self.single_mode: self.check_failed.emit(resource.resource_name, "该资源没有mirror酱更新途径")
            return False

        cdk = global_config.get_app_config().CDK if hasattr(global_config.get_app_config(), 'CDK') else ""

        api_url = f"{self.mirror_base_url}/resources/{rid}/latest"
        params = {"cdk": cdk, "user_agent": "MaaYYsGUI",
                  "channel": channel, "os": platform.system().lower(), "arch": platform.machine().lower()}

        # --- 修改开始: 如果不是强制检查，则传递当前版本号 ---
        if not self.force_check:
            params["current_version"] = resource.resource_version
        # --- 修改结束 ---

        log_params = params.copy()
        log_params["cdk"] = "***" if cdk else ""
        logger.debug(f"检查资源: {resource.resource_name}, API_URL: {api_url}, PARAMS: {log_params}")

        try:
            response = requests.get(api_url, params=params)
            logger.debug(
                f"'{resource.resource_name}' 的 MirrorChyan API 响应: 状态 {response.status_code}, 内容: {response.text}")

            try:
                result = response.json()
            except requests.exceptions.JSONDecodeError:
                logger.warning(f"MirrorChyan API 未返回有效的 JSON。状态码: {response.status_code}")
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
                    f"'{resource.resource_name}' 的 MirrorChyan API 返回业务错误: {detail} (代码: {error_code})")
                if self.single_mode:
                    self.check_failed.emit(resource.resource_name, f"业务错误 ({error_code}): {detail}")
                return False

            data = result.get("data", {})
            latest_version = data.get("version_name", "")
            download_url = data.get("url", "")
            update_type = data.get("update_type", "full")
            release_note = data.get("release_note", "")
            logger.debug(
                f"解析的 MirrorChyan 数据: 版本='{latest_version}', 下载链接='{download_url}', 类型='{update_type}'。")

            latest_version_str = latest_version.lstrip('v')
            current_version_str = resource.resource_version.lstrip('v')
            logger.debug(f"正在比较版本 - 最新: '{latest_version_str}', 当前: '{current_version_str}'。")

            if latest_version_str and (self.force_check or semver.compare(latest_version_str, current_version_str) > 0):
                log_action = "强制获取" if self.force_check else "发现新的"
                logger.info(
                    f"为 '{resource.resource_name}' {log_action} MirrorChyan 版本: {latest_version} (当前: {resource.resource_version})。")
                update_info = UpdateInfo(
                    resource_name=resource.resource_name, current_version=resource.resource_version,
                    new_version=latest_version,
                    download_url=download_url,
                    update_type=update_type, source=UpdateSource.MIRROR,
                    release_note=release_note
                )
                self.update_found.emit(update_info)
                return True
            else:
                logger.info(f"资源 '{resource.resource_name}' 已是最新版本 (MirrorChyan)。")
                if self.single_mode: self.update_not_found.emit(resource.resource_name)
                return False
        except requests.exceptions.RequestException as e:
            logger.error(f"检查 MirrorChyan 更新时发生网络请求异常: {e}", exc_info=True)
            if self.single_mode: self.check_failed.emit(resource.resource_name, f"网络请求失败: {str(e)}")
            return False

    def _check_github_update(self, resource: ResourceConfig, channel: str):
        repo_url = resource.resource_rep_url
        logger.debug(f"正在为 '{resource.resource_name}' 从仓库 '{repo_url}' 检查 GitHub 更新。")
        if not repo_url or "github.com" not in repo_url:
            if self.single_mode: self.check_failed.emit(resource.resource_name, "未配置有效的 GitHub 仓库 URL")
            return False

        try:
            owner_repo = repo_url.rstrip("/").split("github.com/")[1].replace(".git", "")
            api_url = f"{self.github_api_url}/repos/{owner_repo}/tags"
            logger.debug(f"已构造 GitHub API URL: {api_url}")

            headers = {"Accept": "application/vnd.github.v3+json"}
            github_token = global_config.app_config.github_token
            if github_token:
                logger.debug("正在使用配置的 GitHub token 进行 API 请求。")
                headers["Authorization"] = f"token {github_token}"

            response = requests.get(api_url, headers=headers)
            logger.debug(f"'{resource.resource_name}' 的 GitHub API 响应: 状态 {response.status_code}")

            if response.status_code != 200:
                msg = f"GitHub API 返回错误 ({response.status_code})"
                logger.warning(f"{msg}. 内容: {response.text}")
                if self.single_mode: self.check_failed.emit(resource.resource_name, msg)
                return False

            tags = response.json()
            logger.debug(f"从 GitHub API 收到 {len(tags)} 个标签。")

            valid_tags = []
            for tag in tags:
                tag_name = tag.get("name", "").lstrip("v")
                try:
                    version_info = semver.VersionInfo.parse(tag_name)
                    valid_tags.append((version_info, tag))
                except ValueError:
                    logger.debug(f"跳过非 SemVer 标签: '{tag.get('name')}'")

            if not valid_tags:
                logger.warning("仓库中不包含任何有效的 SemVer 标签。")
                if self.single_mode: self.check_failed.emit(resource.resource_name,
                                                            "仓库中未找到任何有效的 SemVer 版本标签")
                return False

            logger.debug(f"找到 {len(valid_tags)} 个有效的 SemVer 标签。正在排序...")
            valid_tags.sort(key=lambda item: item[0], reverse=True)

            latest_tag_data = None
            if channel == "stable":
                logger.debug("正在搜索最新的稳定版 (非预发布版)。")
                for version_info, tag_data in valid_tags:
                    if version_info.prerelease is None:
                        latest_tag_data = tag_data
                        break
            else:
                logger.debug(f"正在 '{channel}' 通道中搜索最新版本 (包括预发布版)。")
                latest_tag_data = valid_tags[0][1]

            if not latest_tag_data:
                msg = f"在 '{channel}' 频道中未找到合适的更新"
                logger.warning(msg)
                if self.single_mode: self.check_failed.emit(resource.resource_name, msg)
                return False

            logger.debug(f"为 '{channel}' 通道选择的最新标签: {latest_tag_data.get('name')}")
            latest_version_str = latest_tag_data.get("name", "").lstrip("v")
            current_version_str = resource.resource_version.lstrip("v")
            logger.debug(f"正在比较版本 - 最新: '{latest_version_str}', 当前: '{current_version_str}'。")

            # 在强制检查模式下，即使版本号相同也视为更新
            if self.force_check or semver.compare(latest_version_str, current_version_str) > 0:
                log_action = "强制获取" if self.force_check else "发现新的"
                logger.info(
                    f"为 '{resource.resource_name}' {log_action} GitHub 版本: {latest_version_str} (当前: {current_version_str})。")

                download_url = ""
                release_note = "无法获取更新日志。"
                tag_name = latest_tag_data.get("name")
                if not tag_name:
                    self.check_failed.emit(resource.resource_name, "最新的标签名称无效。")
                    return False

                asset_pattern = self.target_asset_name
                is_regex_search = False
                # 如果没有直接指定 asset, 则尝试从 platform_release_names 获取正则
                if not asset_pattern and hasattr(resource, 'platform_release_names') and resource.platform_release_names:
                    current_platform = platform.system().lower()
                    pattern = resource.platform_release_names.get(current_platform)
                    if pattern:
                        asset_pattern = pattern
                        is_regex_search = True  # 来自 platform_release_names 的总是被当作正则处理
                        logger.debug(f"将使用平台 '{current_platform}' 的正则模式 '{asset_pattern}' 查找资源。")

                release_api_url = f"{self.github_api_url}/repos/{owner_repo}/releases/tags/{tag_name}"
                try:
                    logger.debug(f"正在从 {release_api_url} 获取发布信息。")
                    release_response = requests.get(release_api_url, headers=headers)

                    if release_response.status_code == 200:
                        release_data = release_response.json()
                        release_note = release_data.get("body", "此版本没有提供更新日志。")

                        # --- 修改开始: 根据 asset_pattern (精确名称或正则) 查找资源 ---
                        if asset_pattern:
                            search_type = "正则" if is_regex_search else "精确名称"
                            logger.debug(f"正在查找名为 '{asset_pattern}' 的特定资源 (通过{search_type})。")
                            assets = release_data.get("assets", [])
                            found_asset = False
                            for asset in assets:
                                asset_name = asset.get("name")
                                if not asset_name:
                                    continue

                                match = False
                                # 如果是正则搜索
                                if is_regex_search:
                                    try:
                                        if re.search(asset_pattern, asset_name):
                                            match = True
                                    except re.error as e:
                                        logger.error(f"资源名称模式 '{asset_pattern}' 是一个无效的正则表达式: {e}")
                                        break  # 如果正则无效，则终止本次查找
                                # 否则，进行精确匹配
                                else:
                                    if asset_name == asset_pattern:
                                        match = True

                                if match:
                                    download_url = asset.get("browser_download_url")
                                    logger.info(f"已找到匹配的资源: '{asset_name}', URL: {download_url}")
                                    found_asset = True
                                    break

                            if not found_asset:
                                msg = f"版本 {latest_version_str} 中缺少必需的更新包 (匹配模式: '{asset_pattern}')。"
                                logger.error(msg)
                                self.check_failed.emit(resource.resource_name, msg)
                                return False
                        else:
                            # 默认行为：获取源码包
                            download_url = latest_tag_data.get("zipball_url", "")
                            logger.debug(f"未指定目标资源且无平台配置，使用默认的 zipball URL: {download_url}")
                        # --- 修改结束 ---
                    else:
                        logger.warning(f"获取 {tag_name} 的发布信息失败，状态码: {release_response.status_code}")
                        # 如果需要特定的 asset 但无法获取 release 列表，则失败
                        if asset_pattern:
                            msg = f"无法获取版本 {latest_version_str} 的发布详情，因此无法查找更新包 '{asset_pattern}'。"
                            self.check_failed.emit(resource.resource_name, msg)
                            return False
                        else:  # Fallback to source code if no specific asset is needed
                            download_url = latest_tag_data.get("zipball_url", "")

                except requests.exceptions.RequestException as re_exc:
                    logger.error(f"请求发布信息时出错: {re_exc}")
                    self.check_failed.emit(resource.resource_name, f"网络请求失败: {str(re_exc)}")
                    return False

                if not download_url:
                    msg = f"为版本 {latest_version_str} 找到了更新，但无法确定下载链接。"
                    logger.error(msg)
                    self.check_failed.emit(resource.resource_name, msg)
                    return False

                update_info = UpdateInfo(
                    resource_name=resource.resource_name, current_version=resource.resource_version,
                    new_version=latest_version_str, download_url=download_url,
                    update_type="full", source=UpdateSource.GITHUB,
                    release_note=release_note
                )
                self.update_found.emit(update_info)
                return True
            else:
                logger.info(f"资源 '{resource.resource_name}' 已是最新版本 (GitHub)。")
                if self.single_mode: self.update_not_found.emit(resource.resource_name)
                return False
        except requests.exceptions.RequestException as e:
            logger.error(f"检查 GitHub 更新时发生网络请求异常: {e}", exc_info=True)
            if self.single_mode: self.check_failed.emit(resource.resource_name, f"网络请求失败: {str(e)}")
            return False