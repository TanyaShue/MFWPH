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

    def get_python_executable(self) -> Path:
        """获取Python可执行文件路径"""
        if platform.system() == "Windows":
            return self.python_dir / "python.exe"

        # --- MODIFIED: 对Linux和macOS，预编译版的可执行文件路径是统一的 ---
        # 预编译包解压后内部是标准的目录结构
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

    # --- MODIFICATION START: 更新下载源为可移植的预编译版本 ---
    def _load_config(self) -> Dict[str, Any]:
        """
        加载配置文件，源已更新为python-build-standalone项目的预编译便携版。
        这避免了在Linux和macOS上进行本地编译，大大提高了速度和可靠性。
        """
        config_path = Path("assets/config/python_sources.json")
        # 使用20240415作为稳定的构建日期标签，如果未来需要更新版本可以修改此日期
        build_tag = "20240415"

        default_config = {
            "fallback_versions": {
                "3.10": "3.10.14",
                "3.11": "3.11.9",
                "3.12": "3.12.3"
            },
            "python_download_sources": {
                "windows": [
                    "https://mirrors.aliyun.com/python-release/windows/python-{version}-embed-amd64.zip",
                    "https://www.python.org/ftp/python/{version}/python-{version}-embed-amd64.zip"
                ],
                "linux": [
                    "https://mirror.ghproxy.com/https://github.com/indygreg/python-build-standalone/releases/download/{build_tag}/cpython-{version}+{build_tag}-{arch}-unknown-linux-gnu-install_only.tar.gz",
                    "https://github.com/indygreg/python-build-standalone/releases/download/{build_tag}/cpython-{version}+{build_tag}-{arch}-unknown-linux-gnu-install_only.tar.gz"
                ],
                "darwin": [
                    "https://mirror.ghproxy.com/https://github.com/indygreg/python-build-standalone/releases/download/{build_tag}/cpython-{version}+{build_tag}-{arch}-apple-darwin-install_only.tar.gz",
                    "https://github.com/indygreg/python-build-standalone/releases/download/{build_tag}/cpython-{version}+{build_tag}-{arch}-apple-darwin-install_only.tar.gz"
                ]
            },
            "build_tag": build_tag,  # 将构建标签也加入配置，方便统一管理
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

    # --- MODIFICATION END ---

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
                return True
            self.logger.info(f"Python {version} 未安装，开始下载...")
            return await self._download_and_install_python(runtime)

    # --- MODIFICATION START: 极大简化安装流程 ---
    async def _download_and_install_python(self, runtime: PythonRuntime) -> bool:
        """
        下载并安装Python。现在全平台统一为下载预编译包并解压，不再需要编译或特殊安装逻辑。
        """
        system = platform.system().lower()
        patch_version = self._get_patch_version(runtime.version)

        # 动态检测CPU架构
        arch = platform.machine()
        if system == "darwin" and arch == "arm64":
            arch = "aarch64"  # Apple Silicon

        sources = self.config.get("python_download_sources", {}).get(system, [])
        if not sources:
            self.logger.error(f"不支持的系统: {system}")
            return False

        # 格式化URL，填入版本、构建标签和架构
        build_tag = self.config.get("build_tag", "20240415")
        urls = [url.format(version=patch_version, build_tag=build_tag, arch=arch) for url in sources]

        temp_dir = self.runtime_base_dir / f"temp_{runtime.version}"

        try:
            for url in urls:
                try:
                    filename = url.split("/")[-1]
                    temp_dir.mkdir(exist_ok=True)
                    temp_file = temp_dir / filename

                    await self._download_file_async(url, temp_file)

                    # 所有平台都统一使用解压逻辑
                    await self._extract_archive(temp_file, runtime.python_dir)

                    if system == "windows":
                        await self._setup_windows_embedded(runtime.version, runtime.python_dir)

                    if await self._ensure_pip_installed(runtime):
                        self.logger.info(f"✅ Python {runtime.version} 安装完成")
                        notification_manager.show_success(f"Python {runtime.version} 安装成功", "完成")
                        return True
                    else:
                        raise Exception("pip installation failed")

                except Exception as e:
                    self.logger.error(f"从 {url} 安装失败: {e}", exc_info=True)
                    shutil.rmtree(runtime.python_dir, ignore_errors=True)
                    continue
        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

        notification_manager.show_error(f"Python {runtime.version} 安装失败", "错误")
        return False

    # --- MODIFICATION END ---

    # --- REMOVED: _install_macos_pkg 和 _compile_python 函数已被移除 ---

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
            else:  # .tar.gz
                with tarfile.open(archive_path, 'r:*') as tf:
                    tf.extractall(path=temp_extract_dir)

            # python-build-standalone解压后通常有一个名为'python'的根目录
            # 我们需要将这个目录的内容移动到目标位置，而不是保留这个多余的层级
            inner_dirs = list(temp_extract_dir.iterdir())
            if len(inner_dirs) == 1 and inner_dirs[0].is_dir():
                source_dir = inner_dirs[0]
                for item in source_dir.iterdir():
                    shutil.move(str(item), str(extract_to / item.name))
                source_dir.rmdir()  # 删除空的源目录
            else:  # 如果没有单层目录，直接移动所有内容
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
        """确保pip已安装"""
        python_exe = runtime.get_python_executable()
        kwargs = self._get_subprocess_kwargs()

        process = await asyncio.create_subprocess_exec(str(python_exe), "-m", "pip", "--version", **kwargs)
        await process.communicate()

        if process.returncode != 0:
            self.logger.info("pip未找到，开始安装...")
            # 预编译版本通常自带ensurepip，这是最可靠的方式
            process_ensure = await asyncio.create_subprocess_exec(str(python_exe), "-m", "ensurepip", "--upgrade",
                                                                  **kwargs)
            _, stderr_ensure = await process_ensure.communicate()

            if process_ensure.returncode != 0:
                self.logger.error(f"ensurepip 失败: {stderr_ensure.decode(errors='ignore')}")
                return False

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
                    notification_manager.show_info("正在安装依赖，请耐心等待...", "安装依赖", 5000)
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