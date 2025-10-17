import psutil
import shlex
import re
from typing import Optional


def _cmdline_to_str(cmdline) -> str:
    """把 cmdline list -> 单一小写字符串（健壮处理 None/空列表）"""
    if not cmdline:
        return ""
    if isinstance(cmdline, (list, tuple)):
        return " ".join(cmdline).lower()
    return str(cmdline).lower()


def _iter_procs():
    """安全迭代系统进程（只取需要字段）"""
    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            yield p
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue


def find_emulator_pid(start_command: str) -> Optional[int]:
    """
    根据启动命令返回对应模拟器的进程 PID。
    支持 LDPlayer (dnplayer.exe index=N) 和 MuMu (MuMuNxMain.exe -v N)。
    返回第一个匹配到的 PID 或 None。
    """
    cmd = start_command.strip()
    cmd_lower = cmd.lower()

    # ---- LDPlayer: dnplayer.exe index=N ----
    if "dnplayer.exe" in cmd_lower:
        m = re.search(r'index[=\s]+(\d+)', cmd_lower)
        if not m:
            return None
        idx = m.group(1)

        pattern = re.compile(r'index[=\s]+' + re.escape(idx))
        for p in _iter_procs():
            try:
                name = (p.info.get('name') or "").lower()
                # 增加对进程名的初步过滤，提高效率
                if "dnplayer" not in name and "dnconsole" not in name:
                    continue
                full = _cmdline_to_str(p.info.get('cmdline'))
                if pattern.search(full):
                    return p.pid
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        # not found
        return None

    # ---- MuMu: MuMuNxMain.exe -v N  ----
    if "mumu" in cmd_lower:
        m = re.search(r'-v\s+(\d+)', cmd_lower)
        if not m:
            return None
        v = m.group(1)

        # v == "0": 目标是主实例 MuMuNxDevice.exe，其命令行可能不含 -v 参数
        if v == "0":
            for p in _iter_procs():
                try:
                    name = (p.info.get('name') or "").lower()
                    full = _cmdline_to_str(p.info.get('cmdline'))

                    # 核心判断：必须是 MuMu 设备进程
                    if "mumunxdevice.exe" not in name and "mumunxdevice.exe" not in full:
                        continue

                    # 检查是否是多开实例（即 v > 0 的情况），如果是则排除
                    # 多开实例会明确带有 -v N (N>0)
                    match_v = re.search(r'-v\s+(\d+)', full)
                    if match_v and match_v.group(1) != "0":
                        continue

                    # 如果不是多开实例，那就是 v=0 的目标进程
                    return p.pid
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return None

        # v > 0: 必须严格匹配包含 "-v N" 的 MuMuNxDevice.exe
        pattern = re.compile(r'-v\s*' + re.escape(v) + r'\b')
        for p in _iter_procs():
            try:
                name = (p.info.get('name') or "").lower()
                full = _cmdline_to_str(p.info.get('cmdline'))

                # 核心判断：必须是 MuMu 设备进程
                if "mumunxdevice.exe" not in name and "mumunxdevice.exe" not in full:
                    continue

                # 精确匹配 -v N 参数
                if pattern.search(full):
                    return p.pid
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None

    # 其它未识别
    return None
