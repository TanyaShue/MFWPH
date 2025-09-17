import base64
import json
from typing import Tuple, List, Optional, Dict, Any

import requests


def get_github_repo_refs(url: str, github_token: str = None) -> Tuple[bool, List[str], List[str]]:
    """
    检测传入的是否是有效的 GitHub 仓库链接，并返回所有的分支和标签。

    Args:
        url: GitHub 仓库的 URL.
        github_token: 可选的 GitHub Personal Access Token.

    Returns:
        一个元组 (success, branches, tags):
        - success (bool): 如果仓库有效则为 True，否则为 False.
        - branches (List[str]): 仓库中所有分支的名称列表。
        - tags (List[str]): 仓库中所有标签的名称列表。
    """
    if not url.startswith("https://github.com/"):
        print("错误：只支持 GitHub 仓库链接。")
        return False, [], []

    try:
        # 提取 owner/repo
        parts = url.rstrip("/").split("/")
        owner, repo = parts[-2], parts[-1].removesuffix(".git")
    except IndexError:
        print("错误：无法从 URL 中解析 owner 和 repo。")
        return False, [], []

    api_base_url = f"https://api.github.com/repos/{owner}/{repo}"
    headers = {"Accept": "application/vnd.github.v3+json"}
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    # 1. 验证仓库是否存在
    try:
        repo_resp = requests.get(api_base_url, headers=headers, timeout=10)
        if repo_resp.status_code != 200:
            print(f"错误：无法访问仓库，请检查链接或权限 (status={repo_resp.status_code})。")
            return False, [], []
    except requests.exceptions.RequestException as e:
        print(f"错误：请求仓库信息时发生网络错误: {e}")
        return False, [], []

    # 2. 获取所有分支
    branches = []
    branches_url = f"{api_base_url}/branches"
    try:
        branch_resp = requests.get(branches_url, headers=headers, timeout=10)
        if branch_resp.status_code == 200:
            branches = [item['name'] for item in branch_resp.json()]
        else:
            print(f"警告：无法获取分支列表 (status={branch_resp.status_code})。")
    except requests.exceptions.RequestException as e:
        print(f"警告：请求分支列表时发生网络错误: {e}")

    # 3. 获取所有标签
    tags = []
    tags_url = f"{api_base_url}/tags"
    try:
        tag_resp = requests.get(tags_url, headers=headers, timeout=10)
        if tag_resp.status_code == 200:
            tags = [item['name'] for item in tag_resp.json()]
        else:
            print(f"警告：无法获取标签列表 (status={tag_resp.status_code})。")
    except requests.exceptions.RequestException as e:
        print(f"警告：请求标签列表时发生网络错误: {e}")

    print(f"成功找到仓库: {owner}/{repo}")
    print(f"分支: {branches}")
    print(f"标签: {tags}")

    return True, branches, tags


def check_resource_config(url: str, ref: str, github_token: str = None) -> bool:
    """
    在指定的 ref (分支或标签) 下，校验 resource_config.json 文件是否存在且有效。

    Args:
        url: GitHub 仓库的 URL.
        ref: 需要校验的分支名或标签名。
        github_token: 可选的 GitHub Personal Access Token.

    Returns:
        bool: 如果文件存在且是有效的 JSON，则返回 True，否则返回 False.
    """
    if not url.startswith("https://github.com/"):
        print("错误：只支持 GitHub 仓库链接。")
        return False

    try:
        # 提取 owner/repo
        parts = url.rstrip("/").split("/")
        owner, repo = parts[-2], parts[-1].removesuffix(".git")
    except IndexError:
        print("错误：无法从 URL 中解析 owner 和 repo。")
        return False

    # 构建带 ref 参数的 GitHub API 地址
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/resource_config.json"
    params = {"ref": ref}
    headers = {"Accept": "application/vnd.github.v3+json"}
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    try:
        resp = requests.get(api_url, headers=headers, params=params, timeout=10)
        if resp.status_code != 200:
            print(f"在 ref '{ref}' 下未找到 resource_config.json 文件 (status={resp.status_code})。")
            return False

        data = resp.json()
        if "content" not in data:
            print("错误：API 返回异常，响应中没有 'content' 字段。")
            return False

        # Base64 解码
        content = base64.b64decode(data["content"]).decode("utf-8")

        # 尝试解析 JSON
        try:
            config: Dict[str, Any] = json.loads(content)
        except json.JSONDecodeError:
            print(f"错误：在 ref '{ref}' 下的 resource_config.json 文件解析失败，不是有效的 JSON 格式。")
            return False

        if not isinstance(config, dict):
            print(f"错误：在 ref '{ref}' 下的 resource_config.json 解析后不是一个字典。")
            return False

        print(f"成功：在 ref '{ref}' 下找到并成功解析了 resource_config.json。")
        print(f"配置内容: {config}")
        return True

    except requests.exceptions.RequestException as e:
        print(f"错误：检测过程中发生网络错误: {e}")
        return False
    except Exception as e:
        print(f"错误：检测过程中发生未知错误: {e}")
        return False

