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

# --- 新增的导入 ---
import ssl
import certifi
from aiohttp import TCPConnector
# --- 结束 ---

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

    # --- MODIFIED: 适配预编译版本的目录结构 ---
    def get_python_executable(self) -> Path:
        """获取Python可执行文件路径"""
        if platform.system() == "Windows":
            return self.python_dir / "python.exe"
        # 对于 Linux 和 macOS 的预编译版本，可执行文件位于 bin 目录下
        return self.python_dir / "bin" / "python3"

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
        """检查依赖是否发生变化"""
        if not requirements_path.exists():
            return False, ""
        with open(requirements_path, 'rb') as f:
            current_hash = hashlib.md5(f.read()).hexdigest()
        info = self.get_venv_info(resource_name)
        if info.dependencies_hash != current_hash:
            return True, current_hash
        return False, current_hash

    def update_dependencies_hash(self, resource_name: str, hash_value: str):
        """更新依赖的hash值"""
        info = self.get_venv_info(resource_name)
        info.dependencies_hash = hash_value
        self._save_runtime_cache()

    def clear_dependencies_hash(self, resource_name: str):
        """清除依赖hash"""
        info = self.get_venv_info(resource_name)
        info.dependencies_hash = None
        self._save_runtime_cache()

    def cleanup_old_envs(self, keep_days: int = 30):
        """清理长时间未使用的虚拟环境"""
        current_time = time.time()
        cutoff_time = current_time - (keep_days * 24 * 3600)
        to_remove = [h for h, i in self._runtime_cache.items() if i.last_used < cutoff_time]
        for resource_hash in to_remove:
            info = self._runtime_cache[resource_hash]
            if info.venv_path.exists():
                shutil.rmtree(info.venv_path, ignore_errors=True)
                self.logger.info(f"清理旧虚拟环境: {info.venv_name}")
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
            self._runtimes: Dict[str, PythonRuntime] = {}
            self._download_session: Optional[aiohttp.ClientSession] = None
            self._install_locks: Dict[str, asyncio.Lock] = {}
            self._initialized = True
            self.logger.info(f"🚀 全局Python运行时管理器初始化: {self.runtime_base_dir.absolute()}")

    # --- MODIFIED: 更新默认配置以使用预编译、可移植的Python版本 ---
    def _load_config(self) -> Dict[str, Any]:
        """
        加载配置文件。如果文件不存在，则使用包含预编译Python源的默认配置创建它。
        """
        # --- 唯一的修改在这里 ---
        # 我们需要将 os.path.join 返回的字符串，用 Path() 包装起来，转换成一个 Path 对象
        # 这样下面的 .exists() 和 .parent 才能正常工作
        config_path_str = os.path.join(os.getcwd(), "assets", "config", "python_runtime_config.json")
        config_path = Path(config_path_str)
        build_tag = "20240415"

        default_config = {
            "fallback_versions": {
                "3.10": "3.10.13",
                "3.11": "3.11.9",
                "3.12": "3.12.3"
            },
            "build_tag": build_tag,
            "python_download_sources": {
                "windows": [
                    "https://mirrors.huaweicloud.com/python/{version}/python-{version}-embed-amd64.zip",
                    "https://registry.npmmirror.com/-/binary/python/{version}/python-{version}-embed-amd64.zip",
                    "https://www.python.org/ftp/python/{version}/python-{version}-embed-amd64.zip"
                ],
                "linux": [
                    "https://registry.npmmirror.com/-/binary/python-build-standalone/v{build_tag}/python-{version}-pgo+lto-x86_64-unknown-linux-gnu-install_only.tar.gz",
                    "https://github.com/indygreg/python-build-standalone/releases/download/{build_tag}/python-{version}-pgo+lto-x86_64-unknown-linux-gnu-install_only.tar.gz"
                ],
                "darwin": {
                    "x86_64": [
                        "https://registry.npmmirror.com/-/binary/python-build-standalone/v{build_tag}/python-{version}-pgo+lto-x86_64-apple-darwin-install_only.tar.gz",
                        "https://github.com/indygreg/python-build-standalone/releases/download/{build_tag}/python-{version}-pgo+lto-x86_64-apple-darwin-install_only.tar.gz"
                    ],
                    "aarch64": [
                        "https://registry.npmmirror.com/-/binary/python-build-standalone/v{build_tag}/python-{version}-pgo+lto-aarch64-apple-darwin-install_only.tar.gz",
                        "https://github.com/indygreg/python-build-standalone/releases/download/{build_tag}/python-{version}-pgo+lto-aarch64-apple-darwin-install_only.tar.gz"
                    ]
                }
            },
            "pip_sources": [
                "https://pypi.tuna.tsinghua.edu.cn/simple/",
                "https://mirrors.aliyun.com/pypi/simple/",
                "https://pypi.douban.com/simple/",
                "https://pypi.mirrors.ustc.edu.cn/simple/",
                "https://pypi.org/simple/"
            ],
            "get_pip_sources": [
                "https://bootstrap.pypa.io/get-pip.py",
                "https://pypi.tuna.tsinghua.edu.cn/mirrors/pypi/get-pip.py"
            ]
        }

        # --- 新增逻辑：如果文件不存在，则创建并写入默认配置 ---
        if not config_path.exists():
            self.logger.info(f"配置文件 {config_path} 不存在，将创建默认配置文件。")
            try:
                # 确保父目录存在
                config_path.parent.mkdir(parents=True, exist_ok=True)
                with open(config_path, 'w', encoding='utf-8') as f:
                    # 将 default_config 写入文件，使用 indent 参数美化格式
                    json.dump(default_config, f, indent=4, ensure_ascii=False)
                return default_config
            except Exception as e:
                self.logger.error(f"创建默认配置文件失败: {e}。将仅在内存中使用默认配置。")
                return default_config

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"加载配置文件 {config_path} 失败: {e}。将使用默认配置。")
            return default_config

    def get_runtime(self, version: str) -> PythonRuntime:
        """获取指定版本的Python运行时"""
        if version not in self._runtimes:
            self._runtimes[version] = PythonRuntime(version, self.runtime_base_dir, self.logger)
        return self._runtimes[version]

    async def _get_install_lock(self, version: str) -> asyncio.Lock:
        """获取安装锁"""
        if version not in self._install_locks:
            self._install_locks[version] = asyncio.Lock()
        return self._install_locks[version]

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建使用certifi证书的aiohttp会话"""
        if self._download_session is None or self._download_session.closed:
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            connector = TCPConnector(ssl=ssl_context)
            timeout = aiohttp.ClientTimeout(total=3600, connect=60)
            self._download_session = aiohttp.ClientSession(timeout=timeout, connector=connector)
        return self._download_session

    def _get_patch_version(self, version: str) -> str:
        """获取完整版本号"""
        if len(version.split('.')) == 3:
            return version
        return self.config.get("fallback_versions", {}).get(version, "3.11.9")

    def _get_subprocess_kwargs(self) -> dict:
        """获取子进程参数"""
        kwargs = {'stdout': asyncio.subprocess.PIPE, 'stderr': asyncio.subprocess.PIPE}
        if platform.system() == "Windows":
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
        return kwargs

    async def ensure_python_installed(self, version: str) -> bool:
        """确保Python版本已安装"""
        runtime = self.get_runtime(version)
        if runtime.is_python_installed():
            self.logger.info(f"✅ Python {version} 已安装")
            return await self._ensure_pip_installed(runtime)

        lock = await self._get_install_lock(version)
        async with lock:
            if runtime.is_python_installed():
                return await self._ensure_pip_installed(runtime)

            self.logger.info(f"Python {version} 未安装，开始下载...")
            python_installed = await self._download_and_install_python_core(runtime)
            if not python_installed:
                self.logger.error(f"Python {runtime.version} 核心安装失败。")
                notification_manager.show_error(f"Python {runtime.version} 安装失败", "错误")
                shutil.rmtree(runtime.python_dir, ignore_errors=True)
                return False

            if await self._ensure_pip_installed(runtime):
                self.logger.info(f"✅ Python {runtime.version} 及 pip 安装完成")
                notification_manager.show_success(f"Python {runtime.version} 安装成功", "完成")
                return True
            else:
                self.logger.error(f"Python {runtime.version} 安装成功，但 pip 安装失败。请检查网络或手动安装 pip。")
                notification_manager.show_error(f"Python {runtime.version} 已安装，但 pip 安装失败", "错误")
                return False

    # --- MODIFIED: 重写此函数以下载预编译版本并处理macOS架构 ---
    async def _download_and_install_python_core(self, runtime: PythonRuntime) -> bool:
        """
        仅下载并解压Python。全平台统一为下载预编译包并解压。
        返回True表示Python核心文件已就位，否则返回False。
        """
        system = platform.system().lower()
        patch_version = self._get_patch_version(runtime.version)
        all_sources = self.config.get("python_download_sources", {})

        sources = []
        if system == "darwin":
            # 针对 macOS，需要判断 CPU 架构
            arch = platform.machine()
            if arch == "arm64":
                arch = "aarch64"  # 统一为 aarch64

            arch_sources = all_sources.get(system, {}).get(arch)
            if not arch_sources:
                self.logger.error(f"不支持的 macOS 架构: {arch}")
                return False
            sources = arch_sources
        else:
            # 适用于 Windows 和 Linux
            sources = all_sources.get(system, [])

        if not sources:
            self.logger.error(f"未找到适用于 {system} 的 Python 下载源")
            return False

        build_tag = self.config.get("build_tag", "20240415")
        urls = [url.format(version=patch_version, build_tag=build_tag) for url in sources]
        temp_dir = self.runtime_base_dir / f"temp_{runtime.version}"

        try:
            for url in urls:
                try:
                    filename = url.split("/")[-1]
                    temp_dir.mkdir(exist_ok=True)
                    temp_file = temp_dir / filename

                    self.logger.info(f"尝试从 {url} 下载...")
                    await self._download_file_async(url, temp_file)

                    await self._extract_archive(temp_file, runtime.python_dir)

                    if system == "windows":
                        await self._setup_windows_embedded(runtime.version, runtime.python_dir)

                    if runtime.get_python_executable().exists():
                        self.logger.info(f"✅ Python {runtime.version} 核心文件安装成功。")
                        return True
                    else:
                        self.logger.error("解压后未找到 Python 可执行文件，尝试下一个源。")
                        shutil.rmtree(runtime.python_dir, ignore_errors=True)
                        continue

                except Exception as e:
                    self.logger.error(f"从 {url} 下载或解压失败: {e}", exc_info=True)
                    shutil.rmtree(runtime.python_dir, ignore_errors=True)
                    continue
        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

        self.logger.error(f"所有下载源均失败，Python {runtime.version} 安装失败。")
        return False

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
                async with aiofiles.open(filepath, 'wb') as file:
                    async for chunk in response.content.iter_chunked(8192):
                        await file.write(chunk)
                self.logger.info("下载完成")
        except Exception as e:
            self.logger.error(f"下载失败: {e}")
            if filepath.exists():
                filepath.unlink()
            raise

    async def _extract_archive(self, archive_path: Path, extract_to: Path):
        """异步解压文件，并处理单层目录问题"""
        extract_to.mkdir(parents=True, exist_ok=True)
        self.logger.info(f"开始解压 {archive_path.name} 到 {extract_to}...")

        temp_extract_dir = extract_to.parent / f"temp_extract_{extract_to.name}"
        if temp_extract_dir.exists():
            shutil.rmtree(temp_extract_dir)
        temp_extract_dir.mkdir()

        def extract():
            if archive_path.suffix == '.zip':
                with zipfile.ZipFile(archive_path, 'r') as zf:
                    zf.extractall(temp_extract_dir)
            else:
                with tarfile.open(archive_path, 'r:*') as tf:
                    tf.extractall(path=temp_extract_dir)

            inner_dirs = list(temp_extract_dir.iterdir())
            if len(inner_dirs) == 1 and inner_dirs[0].is_dir():
                source_dir = inner_dirs[0]
                for item in source_dir.iterdir():
                    shutil.move(str(item), str(extract_to / item.name))
                source_dir.rmdir()
            else:
                for item in temp_extract_dir.iterdir():
                    shutil.move(str(item), str(extract_to / item.name))

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, extract)

        shutil.rmtree(temp_extract_dir, ignore_errors=True)
        self.logger.info("解压完成")
        archive_path.unlink()

    async def _setup_windows_embedded(self, version: str, python_dir: Path):
        """设置Windows嵌入式Python"""
        pth_file = next(python_dir.glob("python*._pth"), None)
        if pth_file and pth_file.exists():
            content = pth_file.read_text()
            if "#import site" in content:
                content = content.replace("#import site", "import site")
                pth_file.write_text(content)

    async def _ensure_pip_installed(self, runtime: PythonRuntime) -> bool:
        """
        确保pip已安装。优先使用ensurepip，如果失败，则尝试下载get-pip.py进行安装。
        """
        python_exe = runtime.get_python_executable()
        kwargs = self._get_subprocess_kwargs()

        process = await asyncio.create_subprocess_exec(str(python_exe), "-m", "pip", "--version", **kwargs)
        await process.communicate()
        if process.returncode == 0:
            self.logger.info("pip已存在，开始升级核心包...")
            return await self._upgrade_core_packages(runtime)

        self.logger.info("pip未找到，尝试使用 ensurepip 进行安装...")
        process_ensure = await asyncio.create_subprocess_exec(
            str(python_exe), "-m", "ensurepip", "--upgrade", **kwargs
        )
        _, stderr_ensure = await process_ensure.communicate()

        if process_ensure.returncode == 0:
            self.logger.info("ensurepip 安装成功，开始升级核心包...")
            return await self._upgrade_core_packages(runtime)

        self.logger.warning(f"ensurepip 失败: {stderr_ensure.decode(errors='ignore')}")
        self.logger.info("尝试备选方案：下载 get-pip.py 进行安装...")

        get_pip_sources = self.config.get("get_pip_sources", [])
        temp_get_pip_path = runtime.python_dir / "get-pip.py"

        for url in get_pip_sources:
            try:
                await self._download_file_async(url, temp_get_pip_path)
                process_get_pip = await asyncio.create_subprocess_exec(
                    str(python_exe), str(temp_get_pip_path), **kwargs
                )
                _, stderr_get_pip = await process_get_pip.communicate()

                if process_get_pip.returncode == 0:
                    self.logger.info(f"通过 {url} 安装 pip 成功。")
                    if temp_get_pip_path.exists():
                        temp_get_pip_path.unlink()
                    return await self._upgrade_core_packages(runtime)
                else:
                    self.logger.error(f"使用 {url} 的 get-pip.py 失败: {stderr_get_pip.decode(errors='ignore')}")
            except Exception as e:
                self.logger.error(f"下载或执行 get-pip.py 从 {url} 失败: {e}")
            finally:
                if temp_get_pip_path.exists():
                    temp_get_pip_path.unlink()

        self.logger.error("所有pip安装方法均失败。")
        return False

    async def _upgrade_core_packages(self, runtime: PythonRuntime) -> bool:
        """
        升级pip, setuptools, wheel, 和 virtualenv。
        """
        python_exe = runtime.get_python_executable()
        kwargs = self._get_subprocess_kwargs()

        self.logger.info("升级pip, setuptools, wheel, virtualenv...")
        process_upgrade = await asyncio.create_subprocess_exec(
            str(python_exe), "-m", "pip", "install", "--upgrade",
            "pip", "setuptools", "wheel", "virtualenv",
            **kwargs
        )
        _, stderr_upgrade = await process_upgrade.communicate()

        if process_upgrade.returncode != 0:
            self.logger.error(f"升级pip和virtualenv失败: {stderr_upgrade.decode(errors='ignore')}")
            return False

        self.logger.info("核心包升级成功。")
        return True

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
        process = await asyncio.create_subprocess_exec(
            str(python_exe), "-m", "virtualenv", str(info.venv_path),
            **kwargs
        )
        _, stderr = await process.communicate()
        if process.returncode == 0:
            self.logger.info(f"✅ 虚拟环境创建成功: {info.venv_name}")
            await asyncio.create_subprocess_exec(
                str(info.python_exe), "-m", "pip", "install", "--upgrade",
                "pip", "setuptools", "wheel",
                **kwargs
            )
            return info
        self.logger.error(f"创建虚拟环境失败: {stderr.decode(errors='ignore')}")
        return None

    async def install_requirements(
            self,
            version: str,
            resource_name: str,
            requirements_path: Path,
            force_reinstall: bool = False,
            max_retries: int = 1
    ) -> bool:
        """安装requirements.txt中的依赖"""
        if not requirements_path.exists():
            self.logger.info(f"requirements.txt不存在: {requirements_path}")
            return True
        runtime = self.get_runtime(version)
        info = runtime.get_venv_info(resource_name)
        changed, current_hash = await runtime.check_dependencies_changed(resource_name, requirements_path)
        if not changed and not force_reinstall:
            self.logger.info("依赖未变化，跳过安装")
            return True
        if not info.python_exe.exists():
            self.logger.error(f"虚拟环境不存在: {info.venv_name}")
            return False
        self.logger.info(f"开始安装依赖: {requirements_path}")
        for retry in range(max_retries + 1):
            if retry > 0:
                self.logger.info(f"第 {retry} 次重试安装依赖...")
                await asyncio.sleep(2)
            install_success = False
            for source in self.config.get("pip_sources", []):
                try:
                    self.logger.info(f"使用pip源安装依赖: {source}")
                    notification_manager.show_info("正在安装依赖，请耐心等待...", "安装依赖", 10000)
                    cmd = [
                        str(info.python_exe), "-m", "pip", "install",
                        "-r", str(requirements_path), "-i", source,
                        "--no-cache-dir", "-v"
                    ]
                    process = await asyncio.create_subprocess_exec(
                        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
                    )
                    stdout, _ = await process.communicate()
                    if process.returncode == 0:
                        self.logger.info("✅ 依赖安装成功")
                        install_success = True
                        break
                    else:
                        output = stdout.decode('utf-8', errors='ignore')
                        self.logger.warning(f"使用源 {source} 安装失败。输出:\n{output[-500:]}")
                except Exception as e:
                    self.logger.error(f"安装出错: {e}", exc_info=True)
            if install_success:
                runtime.update_dependencies_hash(resource_name, current_hash)
                return True
        runtime.clear_dependencies_hash(resource_name)
        self.logger.error(f"依赖安装失败（尝试了 {max_retries + 1} 次）")
        return False

    async def get_venv_python(self, version: str, resource_name: str) -> Optional[str]:
        """获取虚拟环境的Python可执行文件路径"""
        runtime = self.get_runtime(version)
        info = runtime.get_venv_info(resource_name)
        return str(info.python_exe) if info.python_exe.exists() else None

    def cleanup_old_environments(self, keep_days: int = 30):
        """清理所有版本的旧虚拟环境"""
        for runtime in self._runtimes.values():
            runtime.cleanup_old_envs(keep_days)

    async def cleanup(self):
        """清理资源"""
        if self._download_session:
            await self._download_session.close()
            self._download_session = None


python_runtime_manager = GlobalPythonRuntimeManager()