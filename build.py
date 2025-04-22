import argparse
import datetime
import logging
import os
import shutil
import site
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import List, Optional

import PyInstaller.__main__
import semver

# 常量定义
APP_NAME = "MFWPH"
DEFAULT_VERSION = "0.0.1"
DEFAULT_EXCLUSIONS = ['.git', '.github', '.gitignore', '.gitmodules', '.nicegui', '.idea', 'config', 'debug','logs','pending_updates','resource']

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class BuildContext:
    """构建上下文管理器，处理临时文件"""

    def __init__(self, keep_files: bool = False):
        self.keep_files = keep_files
        self.temp_files = []

    def add_temp_file(self, file_path: str) -> str:
        self.temp_files.append(file_path)
        return file_path

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.keep_files:
            for file_path in self.temp_files:
                if file_path and os.path.exists(file_path):
                    try:
                        os.unlink(file_path)
                        logger.debug(f"删除临时文件: {file_path}")
                    except Exception as e:
                        logger.warning(f"删除临时文件失败 {file_path}: {str(e)}")


def get_version() -> str:
    """获取版本号"""
    # 从GitHub Actions环境变量获取
    github_ref = os.environ.get('GITHUB_REF', '')
    if github_ref.startswith('refs/tags/v'):
        version = github_ref.replace('refs/tags/v', '')
        try:
            semver.VersionInfo.parse(version)
            logger.info(f"使用GitHub标签版本: {version}")
            return version
        except ValueError:
            logger.warning(f"GitHub标签 {version} 不符合SemVer格式")

    # 从git命令获取
    try:
        result = subprocess.run(['git', 'describe', '--tags', '--abbrev=0'],
                                capture_output=True, text=True, check=False)
        if result.returncode == 0 and result.stdout.strip().startswith('v'):
            version = result.stdout.strip()[1:]
            try:
                semver.VersionInfo.parse(version)
                logger.info(f"使用git标签版本: {version}")
                return version
            except ValueError:
                logger.warning(f"Git标签 {version} 不符合SemVer格式")
    except Exception as e:
        logger.error(f"获取git标签时出错: {str(e)}")

    logger.info(f"使用默认版本: {DEFAULT_VERSION}")
    return DEFAULT_VERSION


def bump_version(version: str, bump_type: str) -> str:
    """增加版本号"""
    try:
        ver = semver.VersionInfo.parse(version)
        func = getattr(ver, f'bump_{bump_type}')
        return str(func())
    except Exception as e:
        logger.warning(f"无法增加版本 '{version}': {str(e)}")
        return version


def find_site_package_path(target: str) -> str:
    """查找site-packages中的路径"""
    for path in site.getsitepackages():
        target_path = os.path.join(path, target)
        if os.path.exists(target_path):
            logger.info(f"找到 {target} 在: {target_path}")
            return target_path

    # 创建后备路径
    fallback_path = os.path.join(os.getcwd(), f"{target.replace('/', '_')}_fallback")
    os.makedirs(fallback_path, exist_ok=True)
    logger.info(f"创建后备路径: {fallback_path}")
    return fallback_path


def create_file_with_content(content: str, suffix: str = '.txt') -> str:
    """创建包含指定内容的临时文件"""
    with tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False, encoding='utf-8') as f:
        f.write(content)
        return f.name


def create_version_info_files(version: str, build_time: str, ctx: BuildContext):
    """创建版本相关的信息文件"""
    # 创建版本信息文件 - 使用固定名称 versioninfo.txt
    version_content = f"version={version}\nbuild_time={build_time}\n"
    version_file = os.path.join(tempfile.gettempdir(), "versioninfo.txt")  # 使用固定文件名
    with open(version_file, 'w', encoding='utf-8') as f:
        f.write(version_content)
    ctx.add_temp_file(version_file)

    # 创建Windows文件版本信息
    ver_info = semver.VersionInfo.parse(version)
    version_tuple = (ver_info.major, ver_info.minor, ver_info.patch, 0)

    win_version_content = f"""
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={version_tuple},
    prodvers={version_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          u'040904B0',
          [StringStruct(u'CompanyName', u''),
           StringStruct(u'FileDescription', u'{APP_NAME}'),
           StringStruct(u'FileVersion', u'{version}'),
           StringStruct(u'InternalName', u'{APP_NAME}'),
           StringStruct(u'LegalCopyright', u''),
           StringStruct(u'OriginalFilename', u'{APP_NAME}.exe'),
           StringStruct(u'ProductName', u'{APP_NAME}'),
           StringStruct(u'ProductVersion', u'{version}')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""
    win_version_file = create_file_with_content(win_version_content)
    ctx.add_temp_file(win_version_file)

    return version_file, win_version_file


def run_pyinstaller(version_file: str, win_version_file: str):
    """运行PyInstaller"""
    maa_bin_path = find_site_package_path('maa/bin')
    maa_agent_path = find_site_package_path('MaaAgentBinary')

    args = [
        'main.py',
        '--onefile',
        '--windowed',
        f'--name={APP_NAME}',
        '--clean',
        '--uac-admin',
        f'--add-data={maa_bin_path}{os.pathsep}maa/bin',
        f'--add-data={maa_agent_path}{os.pathsep}MaaAgentBinary',
        f'--add-data={version_file}{os.pathsep}.',
        f'--version-file={win_version_file}'
    ]

    logger.info("正在运行PyInstaller...")
    PyInstaller.__main__.run(args)
    logger.info("PyInstaller构建成功")


def copy_assets(dist_dir: str):
    """复制assets文件夹"""
    src = 'assets'
    dst = os.path.join(dist_dir, 'assets')

    if os.path.exists(src):
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        logger.info(f"已复制assets文件夹到: {dst}")
    else:
        logger.warning(f"assets文件夹不存在: {src}")


def create_zip_package(dist_dir: str, zip_path: str, exclusions: List[str]):
    """创建ZIP包"""
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(dist_dir):
            # 排除指定目录
            dirs[:] = [d for d in dirs if d not in exclusions]

            for file in files:
                if file == os.path.basename(zip_path) or file in exclusions:
                    continue

                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, dist_dir)
                zipf.write(file_path, arcname)

    logger.info(f"成功创建ZIP包: {zip_path}")


def main():
    parser = argparse.ArgumentParser(description=f'Build script for {APP_NAME}')
    parser.add_argument('--keep-files', '-k', action='store_true', help='Keep intermediate files')
    parser.add_argument('--zip-name', '-z', help='Custom name for the output zip file')
    parser.add_argument('--exclude', '-e', nargs='+', default=DEFAULT_EXCLUSIONS, help='Files to exclude')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    parser.add_argument('--bump', choices=['major', 'minor', 'patch'], help='Increment version')
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    start_time = datetime.datetime.now()
    logger.info(f"开始 {APP_NAME} 构建过程")

    try:
        # 获取版本号
        version = get_version()
        if args.bump:
            version = bump_version(version, args.bump)

        # 设置目录和文件名
        dist_dir = os.path.join(os.getcwd(), 'dist')
        Path(dist_dir).mkdir(exist_ok=True)

        build_time = start_time.strftime("%Y%m%d_%H%M%S")
        zip_name = args.zip_name if args.zip_name else f"{APP_NAME}_v{version}_{build_time}"
        zip_path = os.path.join(dist_dir, f"{zip_name}.zip")

        with BuildContext(args.keep_files) as ctx:
            # 创建版本信息文件
            version_file, win_version_file = create_version_info_files(version, build_time, ctx)

            # 运行PyInstaller
            run_pyinstaller(version_file, win_version_file)

            # 复制assets并创建ZIP包
            copy_assets(dist_dir)
            create_zip_package(dist_dir, zip_path, args.exclude)

        # 设置GitHub Actions输出
        print(f"::set-output name=zip_file::{zip_path}")
        print(f"::set-output name=version::v{version}")

        duration = (datetime.datetime.now() - start_time).total_seconds()
        logger.info(f"构建成功完成，用时: {duration:.2f} 秒")
        logger.info(f"输出文件: {zip_path}")

        return 0
    except Exception as e:
        logger.error(f"构建过程失败: {str(e)}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())