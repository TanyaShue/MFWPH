import asyncio
import platform
import zipfile
import tarfile
from pathlib import Path
import filelock
import shutil
import json
import aiohttp
import aiofiles
import time
import subprocess
from typing import Optional, Dict, Any

from app.utils.notification_manager import notification_manager


class PythonRuntimeManager:
    """Python运行时管理器 - 优化版（隐藏命令行窗口）"""

    def __init__(self, runtime_base_dir: str, logger=None):
        self.runtime_base_dir = Path(runtime_base_dir)
        self.runtime_base_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logger or self._get_default_logger()
        self.config = self._load_config()
        self._download_session: Optional[aiohttp.ClientSession] = None
        self.logger.info(f"🚀 Python运行时管理器初始化: {self.runtime_base_dir.absolute()}")

    def _get_subprocess_kwargs(self) -> dict:
        """获取子进程参数，用于隐藏命令行窗口"""
        kwargs = {
            'stdout': asyncio.subprocess.PIPE,
            'stderr': asyncio.subprocess.PIPE
        }

        # Windows系统特殊处理
        if platform.system() == "Windows":
            # 使用 CREATE_NO_WINDOW 标志来隐藏窗口
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
            # 或者使用以下方式（适用于较旧的Python版本）
            # kwargs['creationflags'] = 0x08000000  # CREATE_NO_WINDOW

        return kwargs

    def _get_default_logger(self):
        """获取默认logger"""
        import logging
        logger = logging.getLogger("PythonRuntimeManager")
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger

    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        config_path = Path("assets/config/python_sources.json")
        default_config = {
            "fallback_versions": {
                "3.10": "3.10.5",
                "3.11": "3.11.9",
                "3.12": "3.12.3"
            },
            "python_download_sources": {
                "windows": [
                    "https://mirrors.aliyun.com/python-release/windows/python-{version}-embed-amd64.zip",
                    "https://mirrors.huaweicloud.com/python/{version}/python-{version}-embed-amd64.zip",
                    "https://registry.npmmirror.com/-/binary/python/{version}/python-{version}-embed-amd64.zip",
                    "https://npm.taobao.org/mirrors/python/{version}/python-{version}-embed-amd64.zip",
                    "https://www.python.org/ftp/python/{version}/python-{version}-embed-amd64.zip"
                ],
                "linux": [
                    "https://mirrors.aliyun.com/python-release/source/Python-{version}.tgz",
                    "https://mirrors.huaweicloud.com/python/{version}/Python-{version}.tgz",
                    "https://registry.npmmirror.com/-/binary/python/{version}/Python-{version}.tgz",
                    "https://npm.taobao.org/mirrors/python/{version}/Python-{version}.tgz",
                    "https://www.python.org/ftp/python/{version}/Python-{version}.tgz"
                ],
                "darwin": [
                    "https://mirrors.aliyun.com/python-release/source/Python-{version}.tgz",
                    "https://mirrors.huaweicloud.com/python/{version}/Python-{version}.tgz",
                    "https://registry.npmmirror.com/-/binary/python/{version}/Python-{version}.tgz",
                    "https://npm.taobao.org/mirrors/python/{version}/Python-{version}.tgz",
                    "https://www.python.org/ftp/python/{version}/Python-{version}.tgz"
                ]
            },
            "pip_sources": [
                "https://pypi.tuna.tsinghua.edu.cn/simple/",
                "https://mirrors.aliyun.com/pypi/simple/",
                "https://pypi.douban.com/simple/",
                "https://pypi.mirrors.ustc.edu.cn/simple/",
                "https://mirrors.cloud.tencent.com/pypi/simple/",
                "https://pypi.org/simple/"
            ],
            "get_pip_sources": [
                "https://mirrors.aliyun.com/pypi/get-pip.py",
                "https://pypi.tuna.tsinghua.edu.cn/mirrors/pypi/get-pip.py",
                "https://mirrors.huaweicloud.com/repository/pypi/get-pip.py",
                "https://registry.npmmirror.com/-/binary/pypa/get-pip.py",
                "https://bootstrap.pypa.io/get-pip.py"
            ]
        }

        try:
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            self.logger.error(f"加载配置失败: {e}")
        return default_config

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建aiohttp会话"""
        if self._download_session is None or self._download_session.closed:
            timeout = aiohttp.ClientTimeout(total=1800, connect=60)  # 30分钟总超时
            self._download_session = aiohttp.ClientSession(timeout=timeout)
        return self._download_session

    async def _download_file_async(self, url: str, filepath: Path):
        """异步下载文件"""
        session = await self._get_session()
        filepath.parent.mkdir(parents=True, exist_ok=True)

        try:
            async with session.get(url) as response:
                response.raise_for_status()
                total_size = int(response.headers.get('content-length', 0))

                self.logger.info(f"下载: {url} ({total_size / 1024 / 1024:.1f} MB)")
                notification_manager.show_info("开始安装Python环境，请稍候...", "安装")

                downloaded = 0
                chunk_size = 8192
                start_time = time.time()
                last_log_time = start_time

                async with aiofiles.open(filepath, 'wb') as file:
                    async for chunk in response.content.iter_chunked(chunk_size):
                        await file.write(chunk)
                        downloaded += len(chunk)

                        current_time = time.time()

                        # 每2秒记录一次进度
                        if current_time - last_log_time >= 2.0 or downloaded >= total_size:
                            progress = (downloaded / total_size) * 100 if total_size > 0 else 0
                            elapsed = current_time - start_time

                            # 计算速度和剩余时间
                            if elapsed > 0:
                                speed = downloaded / elapsed  # bytes/sec
                                remaining_bytes = total_size - downloaded
                                eta = remaining_bytes / speed if speed > 0 else 0

                                # 格式化时间
                                if eta < 60:
                                    eta_str = f"{int(eta)}秒"
                                elif eta < 3600:
                                    eta_str = f"{int(eta / 60)}分{int(eta % 60)}秒"
                                else:
                                    eta_str = f"{int(eta / 3600)}小时{int((eta % 3600) / 60)}分"

                                self.logger.debug(f"下载进度: {progress:.1f}% | 剩余: {eta_str}")
                            else:
                                self.logger.debug(f"下载进度: {progress:.1f}%")

                            last_log_time = current_time

                        # 定期让出控制权，保持UI响应
                        if downloaded % (chunk_size * 100) == 0:
                            await asyncio.sleep(0)

                self.logger.info("下载完成")
                return True

        except Exception as e:
            self.logger.error(f"下载失败: {e}")
            if filepath.exists():
                filepath.unlink()
            raise

    def _get_patch_version(self, version: str) -> str:
        """获取完整版本号"""
        # 简化版本处理
        if len(version.split('.')) == 3:
            return version

        fallback = self.config.get("fallback_versions", {})
        return fallback.get(version, "3.11.9")

    def get_python_dir(self, version: str) -> Path:
        """获取Python版本目录"""
        return self.runtime_base_dir / f"python{version}"

    def get_python_executable(self, version: str) -> Path:
        """获取Python可执行文件路径"""
        python_dir = self.get_python_dir(version)
        if platform.system() == "Windows":
            return python_dir / "python.exe"
        return python_dir / "bin" / "python"

    def get_venv_dir(self, version: str, resource_name: str) -> Path:
        """获取虚拟环境目录"""
        return self.get_python_dir(version) / "envs" / resource_name

    def get_venv_python(self, version: str, resource_name: str) -> Path:
        """获取虚拟环境中的Python路径"""
        venv_dir = self.get_venv_dir(version, resource_name)
        if platform.system() == "Windows":
            return venv_dir / "Scripts" / "python.exe"
        return venv_dir / "bin" / "python"

    async def ensure_python_installed(self, version: str) -> bool:
        """确保Python版本已安装"""
        python_exe = self.get_python_executable(version)

        if python_exe.exists():
            self.logger.info(f"✅ Python {version} 已安装")
            return await self._ensure_pip_installed(version)

        self.logger.info(f"Python {version} 未安装，开始下载...")
        return await self._download_and_install_python(version)

    async def _download_and_install_python(self, version: str) -> bool:
        """下载并安装Python"""
        system = platform.system().lower()
        patch_version = self._get_patch_version(version)

        # 获取下载URL
        sources = self.config.get("python_download_sources", {}).get(system, [])
        if not sources:
            self.logger.error(f"不支持的系统: {system}")
            return False

        urls = [url.format(version=patch_version) for url in sources]
        python_dir = self.get_python_dir(version)

        # 使用文件锁避免并发下载
        lock_file = self.runtime_base_dir / f".lock_{version}"
        lock = filelock.FileLock(str(lock_file), timeout=300)

        try:
            with lock:
                # 再次检查是否已安装
                if self.get_python_executable(version).exists():
                    return True

                # 下载Python
                temp_dir = self.runtime_base_dir / f"temp_{version}"
                temp_dir.mkdir(exist_ok=True)

                for url in urls:
                    try:
                        filename = url.split("/")[-1]
                        temp_file = temp_dir / filename

                        await self._download_file_async(url, temp_file)

                        # 解压文件
                        await self._extract_archive(temp_file, python_dir)

                        # Linux/Mac需要编译
                        if system in ["linux", "darwin"]:
                            await self._compile_python(python_dir, patch_version)

                        # Windows嵌入式版本设置
                        if system == "windows":
                            await self._setup_windows_embedded(version)

                        # 清理临时文件
                        shutil.rmtree(temp_dir, ignore_errors=True)

                        # 安装pip
                        await self._ensure_pip_installed(version)

                        self.logger.info(f"✅ Python {version} 安装完成")
                        notification_manager.show_success(f"Python {version} 安装成功", "完成")
                        return True

                    except Exception as e:
                        self.logger.error(f"下载失败: {e}")
                        continue

                notification_manager.show_error(f"Python {version} 安装失败", "错误")
                return False

        except Exception as e:
            self.logger.error(f"安装Python失败: {e}")
            return False

    async def _extract_archive(self, archive_path: Path, extract_to: Path):
        """异步解压文件"""
        extract_to.mkdir(parents=True, exist_ok=True)

        def extract():
            if archive_path.suffix == '.zip':
                with zipfile.ZipFile(archive_path, 'r') as zf:
                    zf.extractall(extract_to)
            elif archive_path.suffix in ['.tgz', '.gz']:
                with tarfile.open(archive_path, 'r:gz') as tf:
                    tf.extractall(extract_to)

        # 在异步环境中运行同步解压操作
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, extract)

        # 删除压缩包
        archive_path.unlink()

    async def _compile_python(self, python_dir: Path, version: str):
        """编译Python (Linux/Mac)"""
        source_dir = python_dir / f"Python-{version}"

        commands = [
            (["./configure", f"--prefix={python_dir}"], "配置"),
            (["make", "-j4"], "编译"),
            (["make", "install"], "安装")
        ]

        for cmd, step in commands:
            self.logger.info(f"执行{step}...")

            # 使用隐藏窗口的参数
            kwargs = self._get_subprocess_kwargs()
            kwargs['cwd'] = source_dir

            process = await asyncio.create_subprocess_exec(
                *cmd, **kwargs
            )
            await process.communicate()

            if process.returncode != 0:
                raise Exception(f"{step}失败")

        # 清理源码
        shutil.rmtree(source_dir, ignore_errors=True)

    async def _setup_windows_embedded(self, version: str):
        """设置Windows嵌入式Python"""
        python_dir = self.get_python_dir(version)
        pth_file = python_dir / f"python{version.replace('.', '')}._pth"

        if pth_file.exists():
            content = pth_file.read_text()
            if "#import site" in content:
                content = content.replace("#import site", "import site")
                pth_file.write_text(content)

    async def _ensure_pip_installed(self, version: str) -> bool:
        """确保pip已安装"""
        python_exe = self.get_python_executable(version)

        # 检查pip - 使用隐藏窗口的参数
        kwargs = self._get_subprocess_kwargs()
        process = await asyncio.create_subprocess_exec(
            str(python_exe), "-m", "pip", "--version",
            **kwargs
        )
        await process.communicate()

        if process.returncode != 0:
            # 尝试安装pip
            self.logger.info("安装pip...")

            # 先尝试ensurepip
            process = await asyncio.create_subprocess_exec(
                str(python_exe), "-m", "ensurepip", "--upgrade",
                **kwargs
            )
            await process.communicate()

            if process.returncode != 0:
                # 下载get-pip.py
                get_pip_url = "https://bootstrap.pypa.io/get-pip.py"
                get_pip_file = python_exe.parent / "get-pip.py"

                try:
                    await self._download_file_async(get_pip_url, get_pip_file)

                    process = await asyncio.create_subprocess_exec(
                        str(python_exe), str(get_pip_file),
                        **kwargs
                    )
                    await process.communicate()
                    get_pip_file.unlink()
                except Exception as e:
                    self.logger.error(f"安装pip失败: {e}")
                    return False

        # 安装virtualenv - 使用隐藏窗口的参数
        process = await asyncio.create_subprocess_exec(
            str(python_exe), "-m", "pip", "install", "--upgrade",
            "pip", "setuptools", "wheel", "virtualenv",
            **kwargs
        )
        await process.communicate()

        return process.returncode == 0

    async def create_venv(self, version: str, resource_name: str) -> bool:
        """使用virtualenv创建虚拟环境"""
        venv_dir = self.get_venv_dir(version, resource_name)

        if venv_dir.exists():
            self.logger.info(f"虚拟环境已存在: {resource_name}")
            return True

        python_exe = self.get_python_executable(version)
        venv_dir.parent.mkdir(parents=True, exist_ok=True)

        # 获取隐藏窗口的参数
        kwargs = self._get_subprocess_kwargs()

        # 先确保virtualenv已安装
        process = await asyncio.create_subprocess_exec(
            str(python_exe), "-m", "pip", "list",
            **kwargs
        )
        stdout, _ = await process.communicate()

        if "virtualenv" not in stdout.decode():
            self.logger.info("安装virtualenv...")
            process = await asyncio.create_subprocess_exec(
                str(python_exe), "-m", "pip", "install", "virtualenv",
                **kwargs
            )
            await process.communicate()

        # 使用virtualenv创建虚拟环境 - 使用隐藏窗口的参数
        process = await asyncio.create_subprocess_exec(
            str(python_exe), "-m", "virtualenv", str(venv_dir),
            **kwargs
        )
        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            self.logger.info(f"✅ 虚拟环境创建成功: {resource_name}")

            # 升级虚拟环境中的pip - 使用隐藏窗口的参数
            venv_python = self.get_venv_python(version, resource_name)
            process = await asyncio.create_subprocess_exec(
                str(venv_python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel",
                **kwargs
            )
            await process.communicate()

            return True

        self.logger.error(f"创建虚拟环境失败: {stderr.decode()}")
        return False

    async def install_packages(self, version: str, resource_name: str, packages: list) -> bool:
        """在虚拟环境中安装包"""
        venv_python = self.get_venv_python(version, resource_name)

        if not venv_python.exists():
            self.logger.error(f"虚拟环境不存在: {resource_name}")
            return False

        # 使用隐藏窗口的参数安装包
        kwargs = self._get_subprocess_kwargs()

        self.logger.info(f"安装包: {', '.join(packages)}")
        process = await asyncio.create_subprocess_exec(
            str(venv_python), "-m", "pip", "install", *packages,
            **kwargs
        )
        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            self.logger.info(f"✅ 包安装成功")
            return True
        else:
            self.logger.error(f"包安装失败: {stderr.decode()}")
            return False

    async def run_python_script(self, version: str, resource_name: str, script_path: str, *args) -> tuple:
        """在虚拟环境中运行Python脚本"""
        venv_python = self.get_venv_python(version, resource_name)

        if not venv_python.exists():
            self.logger.error(f"虚拟环境不存在: {resource_name}")
            return (None, "Virtual environment does not exist")

        # 使用隐藏窗口的参数运行脚本
        kwargs = self._get_subprocess_kwargs()

        process = await asyncio.create_subprocess_exec(
            str(venv_python), script_path, *args,
            **kwargs
        )
        stdout, stderr = await process.communicate()

        return (stdout.decode() if stdout else None,
                stderr.decode() if stderr else None)

    async def cleanup(self):
        """清理资源"""
        if self._download_session:
            await self._download_session.close()

    def __del__(self):
        """析构函数"""
        if hasattr(self, '_download_session') and self._download_session:
            try:
                asyncio.create_task(self._download_session.close())
            except:
                pass
