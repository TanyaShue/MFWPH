# python_runtime_manager.py
import asyncio
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tarfile
import time
import zipfile
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
import aiohttp
import aiofiles
import filelock

from app.models.logging.log_manager import app_logger
from app.utils.notification_manager import notification_manager


@dataclass
class RuntimeInfo:
    """运行时信息"""
    version: str
    resource_name: str
    resource_hash: str
    venv_name: str
    venv_path: Path
    python_exe: Path
    last_used: float
    dependencies_hash: Optional[str] = None


class PythonRuntime:
    """单个Python运行时实例"""

    def __init__(self, version: str, runtime_dir: Path, logger):
        self.version = version
        self.runtime_dir = runtime_dir
        self.logger = logger
        self.python_dir = runtime_dir / f"python{version}"
        self.envs_dir = self.python_dir / "envs"
        self.envs_dir.mkdir(parents=True, exist_ok=True)

        # 运行时信息缓存
        self._runtime_cache: Dict[str, RuntimeInfo] = {}
        self._load_runtime_cache()

    def _load_runtime_cache(self):
        """加载运行时缓存信息"""
        cache_file = self.envs_dir / ".runtime_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for key, info in data.items():
                        self._runtime_cache[key] = RuntimeInfo(
                            version=info['version'],
                            resource_name=info['resource_name'],
                            resource_hash=info['resource_hash'],
                            venv_name=info['venv_name'],
                            venv_path=Path(info['venv_path']),
                            python_exe=Path(info['python_exe']),
                            last_used=info['last_used'],
                            dependencies_hash=info.get('dependencies_hash')
                        )
            except Exception as e:
                self.logger.error(f"加载运行时缓存失败: {e}")

    def _save_runtime_cache(self):
        """保存运行时缓存信息"""
        cache_file = self.envs_dir / ".runtime_cache.json"
        try:
            data = {}
            for key, info in self._runtime_cache.items():
                data[key] = {
                    'version': info.version,
                    'resource_name': info.resource_name,
                    'resource_hash': info.resource_hash,
                    'venv_name': info.venv_name,
                    'venv_path': str(info.venv_path),
                    'python_exe': str(info.python_exe),
                    'last_used': info.last_used,
                    'dependencies_hash': info.dependencies_hash
                }
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"保存运行时缓存失败: {e}")

    def get_python_executable(self) -> Path:
        """获取Python可执行文件路径"""
        if platform.system() == "Windows":
            return self.python_dir / "python.exe"
        return self.python_dir / "bin" / "python"

    def _get_resource_hash(self, resource_name: str) -> str:
        """计算资源名称的MD5哈希"""
        return hashlib.md5(resource_name.encode('utf-8')).hexdigest()[:16]

    def get_venv_info(self, resource_name: str) -> RuntimeInfo:
        """获取虚拟环境信息"""
        resource_hash = self._get_resource_hash(resource_name)

        if resource_hash in self._runtime_cache:
            info = self._runtime_cache[resource_hash]
            info.last_used = time.time()
            self._save_runtime_cache()
            return info

        # 创建新的运行时信息
        venv_name = f"venv_{resource_hash}"
        venv_path = self.envs_dir / venv_name

        if platform.system() == "Windows":
            python_exe = venv_path / "Scripts" / "python.exe"
        else:
            python_exe = venv_path / "bin" / "python"

        info = RuntimeInfo(
            version=self.version,
            resource_name=resource_name,
            resource_hash=resource_hash,
            venv_name=venv_name,
            venv_path=venv_path,
            python_exe=python_exe,
            last_used=time.time()
        )

        self._runtime_cache[resource_hash] = info
        self._save_runtime_cache()
        return info

    def is_python_installed(self) -> bool:
        """检查Python是否已安装"""
        return self.get_python_executable().exists()

    def is_venv_exists(self, resource_name: str) -> bool:
        """检查虚拟环境是否存在"""
        info = self.get_venv_info(resource_name)
        return info.venv_path.exists() and info.python_exe.exists()

    async def check_dependencies_changed(self, resource_name: str, requirements_path: Path) -> tuple[bool, str]:
        """检查依赖是否发生变化
        返回: (是否变化, 当前hash值)
        """
        if not requirements_path.exists():
            return False, ""

        # 计算当前requirements的hash
        with open(requirements_path, 'rb') as f:
            current_hash = hashlib.md5(f.read()).hexdigest()

        info = self.get_venv_info(resource_name)

        # 比较hash，但不更新缓存
        if info.dependencies_hash != current_hash:
            return True, current_hash

        return False, current_hash

    def update_dependencies_hash(self, resource_name: str, hash_value: str):
        """更新依赖的hash值（在安装成功后调用）"""
        info = self.get_venv_info(resource_name)
        info.dependencies_hash = hash_value
        self._save_runtime_cache()

    def clear_dependencies_hash(self, resource_name: str):
        """清除依赖hash（用于安装失败或需要重新安装的情况）"""
        info = self.get_venv_info(resource_name)
        info.dependencies_hash = None
        self._save_runtime_cache()

    def cleanup_old_envs(self, keep_days: int = 30):
        """清理长时间未使用的虚拟环境"""
        current_time = time.time()
        cutoff_time = current_time - (keep_days * 24 * 3600)

        to_remove = []
        for resource_hash, info in self._runtime_cache.items():
            if info.last_used < cutoff_time:
                if info.venv_path.exists():
                    shutil.rmtree(info.venv_path, ignore_errors=True)
                    self.logger.info(f"清理旧虚拟环境: {info.venv_name}")
                to_remove.append(resource_hash)

        for resource_hash in to_remove:
            del self._runtime_cache[resource_hash]

        if to_remove:
            self._save_runtime_cache()


class GlobalPythonRuntimeManager:
    """全局Python运行时管理器（单例）"""

    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self.runtime_base_dir = Path("./runtime")
            self.runtime_base_dir.mkdir(parents=True, exist_ok=True)
            self.logger = app_logger
            self.config = self._load_config()

            # 运行时实例缓存
            self._runtimes: Dict[str, PythonRuntime] = {}

            # 下载会话
            self._download_session: Optional[aiohttp.ClientSession] = None

            # 安装锁（防止并发安装）
            self._install_locks: Dict[str, asyncio.Lock] = {}

            self._initialized = True
            self.logger.info(f"🚀 全局Python运行时管理器初始化: {self.runtime_base_dir.absolute()}")


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
                    "https://www.python.org/ftp/python/{version}/python-{version}-embed-amd64.zip"
                ],
                "linux": [
                    "https://mirrors.aliyun.com/python-release/source/Python-{version}.tgz",
                    "https://www.python.org/ftp/python/{version}/Python-{version}.tgz"
                ],
                "darwin": [
                    "https://mirrors.aliyun.com/python-release/macos//Python-{version}.tgz",
                    "https://www.python.org/ftp/python/{version}/Python-{version}.tgz"
                ]
            },
            "pip_sources": [
                "https://mirrors.aliyun.com/pypi/simple/",
                "https://pypi.tuna.tsinghua.edu.cn/simple/",
                "https://pypi.org/simple/"
            ],
            "get_pip_sources": [
                "https://mirrors.aliyun.com/pypi/get-pip.py",
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

    def get_runtime(self, version: str) -> PythonRuntime:
        """获取指定版本的Python运行时"""
        if version not in self._runtimes:
            self._runtimes[version] = PythonRuntime(
                version,
                self.runtime_base_dir,
                self.logger
            )
        return self._runtimes[version]

    async def _get_install_lock(self, version: str) -> asyncio.Lock:
        """获取安装锁"""
        if version not in self._install_locks:
            self._install_locks[version] = asyncio.Lock()
        return self._install_locks[version]

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建aiohttp会话"""
        if self._download_session is None or self._download_session.closed:
            timeout = aiohttp.ClientTimeout(total=1800, connect=60)
            self._download_session = aiohttp.ClientSession(timeout=timeout)
        return self._download_session

    def _get_patch_version(self, version: str) -> str:
        """获取完整版本号"""
        if len(version.split('.')) == 3:
            return version

        fallback = self.config.get("fallback_versions", {})
        return fallback.get(version, "3.11.9")

    def _get_subprocess_kwargs(self) -> dict:
        """获取子进程参数，用于隐藏命令行窗口"""
        kwargs = {
            'stdout': asyncio.subprocess.PIPE,
            'stderr': asyncio.subprocess.PIPE
        }

        if platform.system() == "Windows":
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW

        return kwargs

    async def ensure_python_installed(self, version: str) -> bool:
        """确保Python版本已安装"""
        runtime = self.get_runtime(version)

        if runtime.is_python_installed():
            self.logger.info(f"✅ Python {version} 已安装")
            return await self._ensure_pip_installed(runtime)

        # 使用锁防止并发安装
        lock = await self._get_install_lock(version)
        async with lock:
            # 再次检查
            if runtime.is_python_installed():
                return True

            self.logger.info(f"Python {version} 未安装，开始下载...")
            return await self._download_and_install_python(runtime)

    async def _download_and_install_python(self, runtime: PythonRuntime) -> bool:
        """下载并安装Python"""
        system = platform.system().lower()
        patch_version = self._get_patch_version(runtime.version)

        sources = self.config.get("python_download_sources", {}).get(system, [])
        if not sources:
            self.logger.error(f"不支持的系统: {system}")
            return False

        urls = [url.format(version=patch_version) for url in sources]
        temp_dir = self.runtime_base_dir / f"temp_{runtime.version}"

        try:
            for url in urls:
                try:
                    filename = url.split("/")[-1]
                    temp_dir.mkdir(exist_ok=True)
                    temp_file = temp_dir / filename

                    # 下载文件
                    await self._download_file_async(url, temp_file)

                    # 根据平台执行不同的安装逻辑
                    if system == "windows":
                        await self._extract_archive(temp_file, runtime.python_dir)
                        await self._setup_windows_embedded(runtime.version, runtime.python_dir)
                    elif system == "darwin":  # macOS
                        await self._install_macos_pkg(temp_file, runtime.python_dir, patch_version)
                    elif system == "linux":
                        # Linux 仍然使用解压和编译
                        await self._extract_archive(temp_file, runtime.python_dir)
                        await self._compile_python(runtime.python_dir, patch_version)

                    # 安装pip
                    if await self._ensure_pip_installed(runtime):
                        self.logger.info(f"✅ Python {runtime.version} 安装完成")
                        notification_manager.show_success(f"Python {runtime.version} 安装成功", "完成")
                        return True
                    else:
                        raise Exception("pip installation failed")

                except Exception as e:
                    self.logger.error(f"从 {url} 安装失败: {e}", exc_info=True)
                    continue
        finally:
            # 确保临时文件被清理
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

        notification_manager.show_error(f"Python {runtime.version} 安装失败", "错误")
        return False

    async def _install_macos_pkg(self, pkg_path: Path, target_dir: Path, version_str: str):
        """
        通过移动.pkg中的内容来安装Python，避免需要sudo权限。
        """
        self.logger.info(f"在macOS上提取 {pkg_path.name}...")

        # 创建一个临时目录来解压.pkg内容
        extract_tmp_dir = pkg_path.parent / "pkg_extract"
        extract_tmp_dir.mkdir(exist_ok=True)

        # 使用pkgutil展开.pkg文件，这不需要sudo权限
        cmd_expand = ["pkgutil", "--expand", str(pkg_path), str(extract_tmp_dir)]
        process_expand = await asyncio.create_subprocess_exec(*cmd_expand, **self._get_subprocess_kwargs())
        _, stderr_expand = await process_expand.communicate()

        if process_expand.returncode != 0:
            raise Exception(f"展开.pkg失败: {stderr_expand.decode()}")

        # 找到最大的payload文件并解压
        payload_path = next(extract_tmp_dir.glob("*.pkg/Payload"), None)
        if not payload_path:
            raise FileNotFoundError("在.pkg内容中找不到Payload")

        # 解压Payload
        cmd_extract_payload = ["tar", "-xzf", str(payload_path), "-C", str(extract_tmp_dir)]
        process_extract = await asyncio.create_subprocess_exec(*cmd_extract_payload, **self._get_subprocess_kwargs())
        _, stderr_extract = await process_extract.communicate()

        if process_extract.returncode != 0:
            raise Exception(f"解压Payload失败: {stderr_extract.decode()}")

        # Python框架通常安装在/Applications目录中
        py_version_short = ".".join(version_str.split('.')[:2])
        source_app_dir = extract_tmp_dir / f"Applications/Python {py_version_short}"

        if not source_app_dir.exists():
            raise FileNotFoundError(f"在解压的内容中找不到Python应用目录: {source_app_dir}")

        # 将Python目录内容移动到我们的目标运行时目录
        target_dir.mkdir(parents=True, exist_ok=True)
        for item in source_app_dir.iterdir():
            shutil.move(str(item), str(target_dir))

        self.logger.info(f"Python已从.pkg移动到 {target_dir}")

    async def _compile_python(self, python_dir: Path, version: str):
        """编译Python (Linux) - 优化版"""
        source_dir = python_dir / f"Python-{version}"
        if not source_dir.exists():
            found_dirs = [d for d in python_dir.iterdir() if d.is_dir() and d.name.lower().startswith('python-')]
            if not found_dirs:
                raise FileNotFoundError(f"在 {python_dir} 中找不到Python源码目录。")
            source_dir = found_dirs[0]

        self.logger.info(f"在 {source_dir} 中开始编译Python...")

        # --prefix 指定安装目录, --enable-optimizations 提升性能
        commands = [
            (["./configure", f"--prefix={python_dir}", "--enable-optimizations", "--with-ensurepip=install"], "配置"),
            (["make", "-j", str(os.cpu_count() or 1)], "编译"),
            (["make", "altinstall"], "安装")  # altinstall避免覆盖系统python
        ]

        for cmd, step in commands:
            self.logger.info(f"执行步骤: {step}...")
            kwargs = self._get_subprocess_kwargs()
            kwargs['cwd'] = source_dir
            process = await asyncio.create_subprocess_exec(*cmd, **kwargs)
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode(errors='ignore')
                self.logger.error(f"{step} 失败。日志: {error_msg}")
                raise Exception(f"{step} failed. Error: {error_msg}")

        self.logger.info("编译完成，清理源码...")
        shutil.rmtree(source_dir, ignore_errors=True)

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

                async with aiofiles.open(filepath, 'wb') as file:
                    async for chunk in response.content.iter_chunked(chunk_size):
                        await file.write(chunk)
                        downloaded += len(chunk)

                        if downloaded % (chunk_size * 100) == 0:
                            await asyncio.sleep(0)

                self.logger.info("下载完成")
                return True

        except Exception as e:
            self.logger.error(f"下载失败: {e}")
            if filepath.exists():
                filepath.unlink()
            raise

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

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, extract)
        archive_path.unlink()

    async def _setup_windows_embedded(self, version: str, python_dir: Path):
        """设置Windows嵌入式Python"""
        pth_file = python_dir / f"python{version.replace('.', '')}._pth"

        if pth_file.exists():
            content = pth_file.read_text()
            if "#import site" in content:
                content = content.replace("#import site", "import site")
                pth_file.write_text(content)

    async def _ensure_pip_installed(self, runtime: PythonRuntime) -> bool:
        """确保pip已安装"""
        python_exe = runtime.get_python_executable()
        kwargs = self._get_subprocess_kwargs()

        # 检查pip
        process = await asyncio.create_subprocess_exec(
            str(python_exe), "-m", "pip", "--version",
            **kwargs
        )
        await process.communicate()

        if process.returncode != 0:
            self.logger.info("安装pip...")

            # 尝试ensurepip
            process = await asyncio.create_subprocess_exec(
                str(python_exe), "-m", "ensurepip", "--upgrade",
                **kwargs
            )
            await process.communicate()

            if process.returncode != 0:
                # 使用get-pip.py
                get_pip_urls = self.config.get("get_pip_sources", [])
                get_pip_file = python_exe.parent / "get-pip.py"

                for url in get_pip_urls:
                    try:
                        await self._download_file_async(url, get_pip_file)

                        process = await asyncio.create_subprocess_exec(
                            str(python_exe), str(get_pip_file),
                            **kwargs
                        )
                        await process.communicate()
                        get_pip_file.unlink()

                        if process.returncode == 0:
                            break
                    except Exception as e:
                        self.logger.warning(f"从 {url} 下载失败: {e}")
                        continue
                else:
                    self.logger.error("安装pip失败")
                    return False

        # 升级pip和安装virtualenv
        process = await asyncio.create_subprocess_exec(
            str(python_exe), "-m", "pip", "install", "--upgrade",
            "pip", "setuptools", "wheel", "virtualenv",
            **kwargs
        )
        await process.communicate()

        return process.returncode == 0

    async def create_venv(self, version: str, resource_name: str) -> Optional[RuntimeInfo]:
        """创建虚拟环境"""
        runtime = self.get_runtime(version)
        info = runtime.get_venv_info(resource_name)

        if info.venv_path.exists():
            self.logger.info(f"虚拟环境已存在: {info.venv_name}")
            return info

        python_exe = runtime.get_python_executable()
        info.venv_path.parent.mkdir(parents=True, exist_ok=True)

        kwargs = self._get_subprocess_kwargs()

        # 创建虚拟环境
        process = await asyncio.create_subprocess_exec(
            str(python_exe), "-m", "virtualenv", str(info.venv_path),
            **kwargs
        )
        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            self.logger.info(f"✅ 虚拟环境创建成功: {info.venv_name}")

            # 升级虚拟环境中的pip
            process = await asyncio.create_subprocess_exec(
                str(info.python_exe), "-m", "pip", "install", "--upgrade",
                "pip", "setuptools", "wheel",
                **kwargs
            )
            await process.communicate()

            return info

        self.logger.error(f"创建虚拟环境失败: {stderr.decode()}")
        return None

    async def install_requirements(
            self,
            version: str,
            resource_name: str,
            requirements_path: Path,
            force_reinstall: bool = False,
            max_retries: int = 1
    ) -> bool:
        """安装requirements.txt中的依赖

        Args:
            version: Python版本
            resource_name: 资源名称
            requirements_path: requirements.txt路径
            force_reinstall: 是否强制重新安装
            max_retries: 最大重试次数

        Returns:
            bool: 安装是否成功
        """
        if not requirements_path.exists():
            self.logger.info(f"requirements.txt不存在: {requirements_path}")
            return True

        runtime = self.get_runtime(version)
        info = runtime.get_venv_info(resource_name)

        # 检查依赖是否变化
        current_hash = ""
        if not force_reinstall:
            changed, current_hash = await runtime.check_dependencies_changed(resource_name, requirements_path)
            if not changed:
                self.logger.info("依赖未变化，跳过安装")
                return True
        else:
            # 强制重装时也计算hash，用于后续保存
            with open(requirements_path, 'rb') as f:
                current_hash = hashlib.md5(f.read()).hexdigest()

        if not info.python_exe.exists():
            self.logger.error(f"虚拟环境不存在: {info.venv_name}")
            return False

        pip_sources = self.config.get("pip_sources", [])

        # 记录安装开始
        self.logger.info(f"开始安装依赖: {requirements_path}")

        # 多次重试机制
        for retry in range(max_retries + 1):
            if retry > 0:
                self.logger.info(f"第 {retry} 次重试安装依赖...")
                await asyncio.sleep(2)  # 重试前等待

            install_success = False

            for source in pip_sources:
                try:
                    self.logger.info(f"使用pip源安装依赖: {source}")
                    notification_manager.show_info("首次安装等待时间较长,请耐心等待...","安装依赖",5000)
                    # 先升级pip（仅在第一次尝试时）
                    if retry == 0:
                        upgrade_cmd = [
                            str(info.python_exe), "-m", "pip", "install",
                            "--upgrade", "pip", "-i", source
                        ]

                        # 静默升级pip
                        kwargs = self._get_subprocess_kwargs()
                        process = await asyncio.create_subprocess_exec(*upgrade_cmd, **kwargs)
                        await process.communicate()

                    # 安装依赖
                    cmd = [
                        str(info.python_exe), "-m", "pip", "install",
                        "-r", str(requirements_path),
                        "-i", source,
                        "--no-cache-dir",  # 避免缓存问题
                        "-v"  # 添加verbose以获取更多输出
                    ]

                    # 创建进程并捕获输出
                    process = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.STDOUT,  # 合并stderr到stdout
                        env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}  # 确保UTF-8编码
                    )

                    # 收集所有输出
                    all_output = []

                    # 实时读取并记录到debug
                    while True:
                        line = await process.stdout.readline()
                        if not line:
                            break

                        decoded_line = line.decode('utf-8', errors='ignore').rstrip()
                        if decoded_line:
                            # 全部输出到debug日志
                            self.logger.debug(f"[pip] {decoded_line}")
                            all_output.append(decoded_line)

                    returncode = await process.wait()

                    # 将完整输出也保存到debug（方便查看完整日志）
                    if all_output:
                        self.logger.debug(f"=== pip完整输出 ({source}) ===\n" + "\n".join(all_output))

                    if returncode == 0:
                        self.logger.info("✅ 依赖安装成功")
                        install_success = True
                        break
                    else:
                        # 失败时，将最后几行输出提升到warning级别
                        self.logger.warning(f"使用源 {source} 安装失败 (返回码: {returncode})")
                        if all_output:
                            last_lines = all_output[-10:]  # 取最后10行
                            self.logger.warning(f"失败输出末尾:\n" + "\n".join(last_lines))

                except asyncio.TimeoutError:
                    self.logger.warning(f"使用源 {source} 安装超时")
                except Exception as e:
                    self.logger.error(f"安装出错: {e}", exc_info=True)
                    continue

            if install_success:
                # 只有在安装成功后才更新hash缓存
                runtime.update_dependencies_hash(resource_name, current_hash)
                self.logger.info(f"已更新依赖hash缓存: {current_hash[:8]}...")
                return True

        # 所有重试都失败，清除hash以便下次重新尝试
        runtime.clear_dependencies_hash(resource_name)
        self.logger.error(f"依赖安装失败（尝试了 {max_retries + 1} 次）")
        return False

    async def get_venv_python(self, version: str, resource_name: str) -> Optional[str]:
        """获取虚拟环境的Python可执行文件路径"""
        runtime = self.get_runtime(version)
        info = runtime.get_venv_info(resource_name)

        if info.python_exe.exists():
            return str(info.python_exe)
        return None

    def cleanup_old_environments(self, keep_days: int = 30):
        """清理所有版本的旧虚拟环境"""
        for runtime in self._runtimes.values():
            runtime.cleanup_old_envs(keep_days)

    async def cleanup(self):
        """清理资源"""
        if self._download_session:
            await self._download_session.close()
            self._download_session = None


# 全局实例
python_runtime_manager = GlobalPythonRuntimeManager()