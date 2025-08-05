import asyncio
import platform
import urllib.request
import zipfile
import tarfile
from pathlib import Path
import filelock
import re
import shutil
import sys
from datetime import datetime


class PythonRuntimeManager:
    """Python运行时管理器 - 优化版

    功能：
    1. 自动下载和安装指定版本的Python
    2. 自动配置pip、setuptools、wheel等基础包
    3. 使用virtualenv创建虚拟环境
    4. 支持Windows、Linux、macOS多平台
    5. 实时显示安装进度和输出
    """

    def __init__(self, runtime_base_dir: str, logger=None):
        self.runtime_base_dir = Path(runtime_base_dir)
        self.runtime_base_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logger or self._get_default_logger()
        print(f"\n🚀 Python运行时管理器初始化")
        print(f"📁 基础目录: {self.runtime_base_dir.absolute()}")
        print("-" * 60)

    def _get_default_logger(self):
        """获取默认logger"""
        import logging
        logger = logging.getLogger("PythonRuntimeManager")
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            logger.addHandler(handler)
            logger.setLevel(logging.DEBUG)
        return logger

    def _print_progress(self, message: str, level: str = "INFO"):
        """打印进度信息"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        icons = {
            "INFO": "ℹ️",
            "SUCCESS": "✅",
            "WARNING": "⚠️",
            "ERROR": "❌",
            "PROGRESS": "⏳"
        }
        icon = icons.get(level, "▶")
        print(f"[{timestamp}] {icon} {message}")

    def _download_with_progress(self, url: str, filepath: Path):
        """带进度条的下载函数"""

        def download_hook(block_num, block_size, total_size):
            downloaded = block_num * block_size
            percent = min(100, (downloaded / total_size) * 100)
            mb_downloaded = downloaded / (1024 * 1024)
            mb_total = total_size / (1024 * 1024)

            # 使用\r实现进度条覆盖更新
            bar_length = 40
            filled_length = int(bar_length * percent // 100)
            bar = '█' * filled_length + '░' * (bar_length - filled_length)

            sys.stdout.write(f'\r下载进度: |{bar}| {percent:.1f}% ({mb_downloaded:.1f}/{mb_total:.1f} MB)')
            sys.stdout.flush()

            if percent >= 100:
                print()  # 完成后换行

        urllib.request.urlretrieve(url, str(filepath), download_hook)

    async def _stream_subprocess_output(self, cmd, cwd=None):
        """实时流式输出子进程的结果"""
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT  # 合并stderr到stdout
        )

        # 实时读取并打印输出
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            print(f"  │ {line.decode().rstrip()}")

        await process.wait()
        return process.returncode

    def _get_python_download_url(self, version: str) -> dict:
        """动态生成Python下载URL"""
        self._print_progress(f"正在查找Python {version}的最新版本...", "PROGRESS")
        patch_version = self._get_latest_patch_version(version)
        if not patch_version:
            raise ValueError(f"无法找到Python {version}的有效版本")

        self._print_progress(f"找到版本: Python {patch_version}", "SUCCESS")
        base_url = f"https://www.python.org/ftp/python/{patch_version}"

        return {
            "windows": f"{base_url}/python-{patch_version}-embed-amd64.zip",
            "linux": f"{base_url}/Python-{patch_version}.tgz",
            "darwin": f"{base_url}/Python-{patch_version}.tgz"
        }

    def _get_latest_patch_version(self, version: str) -> str:
        """获取指定版本的最新patch版本"""
        try:
            url = f"https://www.python.org/ftp/python/"
            with urllib.request.urlopen(url) as response:
                html = response.read().decode('utf-8')

            pattern = rf'{version}\.(\d+)'
            matches = re.findall(pattern, html)

            if matches:
                max_patch = max(int(m) for m in matches)
                return f"{version}.{max_patch}"

        except Exception as e:
            self._print_progress(f"无法从官网获取版本信息: {e}", "WARNING")

        # 使用预定义的版本映射作为后备
        fallback_versions = {
            "3.8": "3.8.19",
            "3.9": "3.9.19",
            "3.10": "3.10.14",
            "3.11": "3.11.9",
            "3.12": "3.12.3"
        }
        return fallback_versions.get(version)

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
        print(f"\n{'=' * 60}")
        self._print_progress(f"检查Python {version}安装状态...", "INFO")

        python_exe = self.get_python_executable(version)

        if python_exe.exists():
            self._print_progress(f"Python {version} 已存在: {python_exe}", "SUCCESS")
            # 检查pip和virtualenv是否可用
            if await self._check_python_components(version):
                self._print_progress("所有组件已就绪！", "SUCCESS")
                return True
            else:
                self._print_progress(f"Python {version} 组件不完整，开始修复...", "WARNING")
                return await self._setup_python_components(version)

        self._print_progress(f"Python {version} 未安装，准备下载...", "INFO")
        return await self._download_python(version)

    async def _check_python_components(self, version: str) -> bool:
        """检查Python组件是否完整"""
        python_exe = self.get_python_executable(version)

        self._print_progress("检查Python组件...", "PROGRESS")

        components = {
            "pip": False,
            "virtualenv": False
        }

        # 检查pip
        try:
            process = await asyncio.create_subprocess_exec(
                str(python_exe), "-m", "pip", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            if process.returncode == 0:
                components["pip"] = True
                print(f"  ✓ pip: {stdout.decode().strip()}")
            else:
                print(f"  ✗ pip: 不可用")
        except Exception as e:
            print(f"  ✗ pip: 检查失败 - {e}")

        # 检查virtualenv
        try:
            process = await asyncio.create_subprocess_exec(
                str(python_exe), "-m", "virtualenv", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            if process.returncode == 0:
                components["virtualenv"] = True
                print(f"  ✓ virtualenv: {stdout.decode().strip()}")
            else:
                print(f"  ✗ virtualenv: 不可用")
        except Exception as e:
            print(f"  ✗ virtualenv: 检查失败 - {e}")

        return all(components.values())

    async def _download_python(self, version: str) -> bool:
        """下载并安装Python"""
        system = platform.system().lower()

        try:
            download_urls = self._get_python_download_url(version)
            url = download_urls.get(system)
            if not url:
                raise ValueError(f"不支持的系统: {system}")
        except Exception as e:
            self._print_progress(f"获取下载URL失败: {e}", "ERROR")
            return False

        python_dir = self.get_python_dir(version)

        # 使用锁避免重复下载
        lock_file = self.runtime_base_dir / f".download_lock_{version}"
        lock = filelock.FileLock(str(lock_file))

        try:
            with lock.acquire(timeout=300):
                # 再次检查是否已安装
                if self.get_python_executable(version).exists():
                    return True

                self._print_progress(f"开始下载Python {version}", "INFO")
                print(f"  URL: {url}")

                # 创建临时目录
                temp_dir = python_dir.parent / f"temp_python_{version}"
                temp_dir.mkdir(exist_ok=True)

                # 下载文件
                filename = url.split("/")[-1]
                temp_file = temp_dir / filename

                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda: self._download_with_progress(url, temp_file)
                )

                self._print_progress("下载完成！", "SUCCESS")
                self._print_progress("开始解压文件...", "PROGRESS")

                # 解压文件
                python_dir.mkdir(parents=True, exist_ok=True)

                if filename.endswith(".zip"):
                    print("  解压ZIP文件...")
                    with zipfile.ZipFile(temp_file, 'r') as zip_ref:
                        total_files = len(zip_ref.namelist())
                        for i, file in enumerate(zip_ref.namelist()):
                            zip_ref.extract(file, python_dir)
                            if i % 10 == 0:  # 每10个文件更新一次进度
                                percent = (i / total_files) * 100
                                sys.stdout.write(f'\r  解压进度: {percent:.1f}%')
                                sys.stdout.flush()
                        print(f'\r  解压进度: 100.0%')

                elif filename.endswith(".tgz") or filename.endswith(".tar.gz"):
                    print("  解压TAR.GZ文件...")
                    with tarfile.open(temp_file, 'r:gz') as tar_ref:
                        tar_ref.extractall(python_dir)

                    # Linux/Mac需要编译
                    if system in ["linux", "darwin"]:
                        patch_version = self._get_latest_patch_version(version)
                        await self._compile_python(python_dir, patch_version)

                # 清理临时文件
                self._print_progress("清理临时文件...", "PROGRESS")
                temp_file.unlink()
                temp_dir.rmdir()

                self._print_progress(f"Python {version} 安装完成！", "SUCCESS")

                # 设置Python组件
                if not await self._setup_python_components(version):
                    self._print_progress("Python组件设置失败", "ERROR")
                    return False

                return True

        except Exception as e:
            self._print_progress(f"下载Python {version}失败: {e}", "ERROR")
            return False

    async def _compile_python(self, python_dir: Path, patch_version: str):
        """编译Python (Linux/Mac)"""
        source_dir = python_dir / f"Python-{patch_version}"

        self._print_progress("开始编译Python (这可能需要几分钟)...", "INFO")

        commands = [
            (["./configure", f"--prefix={python_dir}", "--enable-optimizations"], "配置"),
            (["make", "-j4"], "编译"),
            (["make", "install"], "安装")
        ]

        for cmd, step_name in commands:
            self._print_progress(f"执行{step_name}步骤...", "PROGRESS")
            print(f"  命令: {' '.join(cmd)}")

            returncode = await self._stream_subprocess_output(cmd, str(source_dir))

            if returncode != 0:
                self._print_progress(f"{step_name}步骤失败", "ERROR")
                raise Exception(f"编译命令失败: {' '.join(cmd)}")

            self._print_progress(f"{step_name}完成", "SUCCESS")

        # 清理源码目录
        self._print_progress("清理源码目录...", "PROGRESS")
        shutil.rmtree(source_dir)

    async def _setup_python_components(self, version: str) -> bool:
        """设置Python组件（pip和virtualenv）"""
        python_exe = self.get_python_executable(version)
        system = platform.system().lower()

        print(f"\n{'=' * 60}")
        self._print_progress("配置Python组件", "INFO")

        try:
            # Windows嵌入式版本需要特殊处理
            if system == "windows":
                await self._setup_windows_embedded_python(version)

            # 确保pip已安装
            self._print_progress("检查pip状态...", "PROGRESS")

            # 检查pip是否已存在
            process = await asyncio.create_subprocess_exec(
                str(python_exe), "-m", "pip", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                # 尝试ensurepip
                self._print_progress("pip不存在，尝试使用ensurepip安装...", "WARNING")
                returncode = await self._stream_subprocess_output(
                    [str(python_exe), "-m", "ensurepip", "--upgrade"]
                )

                if returncode != 0:
                    self._print_progress("ensurepip失败，尝试手动安装pip...", "WARNING")
                    await self._install_pip_manually(python_exe)

            # 升级pip到最新版本
            self._print_progress("升级pip到最新版本...", "PROGRESS")
            returncode = await self._stream_subprocess_output(
                [str(python_exe), "-m", "pip", "install", "--upgrade", "pip"]
            )

            # 安装setuptools、wheel和virtualenv
            self._print_progress("安装必要的包 (setuptools, wheel, virtualenv)...", "PROGRESS")
            returncode = await self._stream_subprocess_output(
                [str(python_exe), "-m", "pip", "install", "--upgrade", "setuptools", "wheel", "virtualenv"]
            )

            if returncode != 0:
                self._print_progress("安装必要包失败", "ERROR")
                return False

            self._print_progress("Python组件配置完成！", "SUCCESS")
            return True

        except Exception as e:
            self._print_progress(f"设置Python组件失败: {e}", "ERROR")
            return False

    async def _setup_windows_embedded_python(self, version: str):
        """设置Windows嵌入式Python"""
        python_dir = self.get_python_dir(version)

        # 创建python._pth文件以启用site-packages
        pth_file = python_dir / f"python{version.replace('.', '')}._pth"
        if pth_file.exists():
            content = pth_file.read_text()
            if "#import site" in content:
                content = content.replace("#import site", "import site")
                pth_file.write_text(content)
                self._print_progress("已启用Windows嵌入式Python的site-packages", "SUCCESS")

    async def _install_pip_manually(self, python_exe: Path):
        """手动安装pip"""
        try:
            # 下载get-pip.py
            get_pip_url = "https://bootstrap.pypa.io/get-pip.py"
            temp_file = python_exe.parent / "get-pip.py"

            self._print_progress("下载get-pip.py...", "PROGRESS")
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._download_with_progress(get_pip_url, temp_file)
            )

            # 运行get-pip.py
            self._print_progress("运行get-pip.py安装pip...", "PROGRESS")
            returncode = await self._stream_subprocess_output(
                [str(python_exe), str(temp_file)]
            )

            if returncode != 0:
                raise Exception("get-pip.py执行失败")

            # 清理临时文件
            temp_file.unlink()
            self._print_progress("pip手动安装成功", "SUCCESS")

        except Exception as e:
            self._print_progress(f"手动安装pip失败: {e}", "ERROR")
            raise

    async def create_venv(self, version: str, resource_name: str) -> bool:
        """使用virtualenv创建虚拟环境"""
        python_exe = self.get_python_executable(version)
        venv_dir = self.get_venv_dir(version, resource_name)

        print(f"\n{'=' * 60}")
        self._print_progress(f"创建虚拟环境: {resource_name}", "INFO")

        if venv_dir.exists():
            self._print_progress(f"虚拟环境已存在: {venv_dir}", "SUCCESS")
            return True

        self._print_progress(f"目标路径: {venv_dir}", "INFO")
        venv_dir.parent.mkdir(parents=True, exist_ok=True)

        # 使用virtualenv创建虚拟环境
        self._print_progress("执行virtualenv命令...", "PROGRESS")
        returncode = await self._stream_subprocess_output(
            [str(python_exe), "-m", "virtualenv", str(venv_dir)]
        )

        if returncode == 0:
            self._print_progress("虚拟环境创建成功！", "SUCCESS")
            await self._upgrade_venv_pip(version, resource_name)
            return True

        self._print_progress("创建虚拟环境失败", "ERROR")
        return False

    async def _upgrade_venv_pip(self, version: str, resource_name: str):
        """升级虚拟环境中的pip"""
        venv_python = self.get_venv_python(version, resource_name)

        try:
            self._print_progress("升级虚拟环境中的pip、setuptools和wheel...", "PROGRESS")
            returncode = await self._stream_subprocess_output(
                [str(venv_python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"]
            )

            if returncode == 0:
                self._print_progress("虚拟环境组件升级成功", "SUCCESS")
            else:
                self._print_progress("虚拟环境组件升级失败", "WARNING")

        except Exception as e:
            self._print_progress(f"升级虚拟环境pip时出错: {e}", "WARNING")

    async def get_python_info(self, version: str) -> dict:
        """获取Python安装信息"""
        python_exe = self.get_python_executable(version)
        info = {
            "version": version,
            "installed": python_exe.exists(),
            "executable": str(python_exe),
            "components": {}
        }

        if not python_exe.exists():
            return info

        print(f"\n{'=' * 60}")
        self._print_progress(f"获取Python {version}详细信息...", "INFO")

        try:
            # 获取详细版本信息
            process = await asyncio.create_subprocess_exec(
                str(python_exe), "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            full_version = (stdout.decode() + stderr.decode()).strip()
            info["full_version"] = full_version
            print(f"  版本: {full_version}")

            # 检查pip
            process = await asyncio.create_subprocess_exec(
                str(python_exe), "-m", "pip", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            info["components"]["pip"] = {
                "available": process.returncode == 0,
                "version": stdout.decode().strip() if process.returncode == 0 else None
            }
            if process.returncode == 0:
                print(f"  ✓ pip: {stdout.decode().strip()}")
            else:
                print(f"  ✗ pip: 不可用")

            # 检查virtualenv
            process = await asyncio.create_subprocess_exec(
                str(python_exe), "-m", "virtualenv", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            info["components"]["virtualenv"] = {
                "available": process.returncode == 0,
                "version": stdout.decode().strip() if process.returncode == 0 else None
            }
            if process.returncode == 0:
                print(f"  ✓ virtualenv: {stdout.decode().strip()}")
            else:
                print(f"  ✗ virtualenv: 不可用")

        except Exception as e:
            info["error"] = str(e)
            self._print_progress(f"获取信息时出错: {e}", "ERROR")

        return info