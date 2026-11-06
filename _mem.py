# -*- coding: utf-8 -*-
"""动态决定并行进程数：保证内存占用不超过【当前可用内存】的 80%

用法:
    import _mem
    WORKERS = _mem.fit_workers(期望数量)      # 会被内存和 CPU 双重限制

环境变量可调:
    PER_WORKER_MB   每个 worker 预计占用（默认 300MB，实测约 280MB）
    MEM_FRAC        允许使用的可用内存比例（默认 0.8 即 80%）
    MEM_RESERVE_MB  给父进程/系统预留（默认 400MB）
"""
import ctypes
import os


class _MEMSTATUS(ctypes.Structure):
    _fields_ = [('dwLength', ctypes.c_ulong),
                ('dwMemoryLoad', ctypes.c_ulong),
                ('ullTotalPhys', ctypes.c_ulonglong),
                ('ullAvailPhys', ctypes.c_ulonglong),
                ('ullTotalPageFile', ctypes.c_ulonglong),
                ('ullAvailPageFile', ctypes.c_ulonglong),
                ('ullTotalVirtual', ctypes.c_ulonglong),
                ('ullAvailVirtual', ctypes.c_ulonglong),
                ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]


def stats():
    """返回 (总内存MB, 可用内存MB)"""
    try:
        if os.name == 'nt':
            ms = _MEMSTATUS()
            ms.dwLength = ctypes.sizeof(_MEMSTATUS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
            return ms.ullTotalPhys / 1048576.0, ms.ullAvailPhys / 1048576.0
        d = {}
        with open('/proc/meminfo') as f:
            for line in f:
                k, v = line.split(':')
                d[k] = float(v.strip().split()[0]) / 1024.0
        return d.get('MemTotal', 0.0), d.get('MemAvailable', d.get('MemFree', 0.0))
    except Exception:
        return 0.0, 0.0


PER_WORKER_MB = float(os.environ.get('PER_WORKER_MB') or 300)
CPU_FRAC = float(os.environ.get('CPU_FRAC') or 0.8)     # ★ CPU 占用上限比例
MEM_FRAC = float(os.environ.get('MEM_FRAC') or 0.8)
MEM_RESERVE_MB = float(os.environ.get('MEM_RESERVE_MB') or 400)


def fit_workers(want=None, per_worker_mb=None, frac=None, quiet=False, cpu_frac=None):
    per = float(per_worker_mb or PER_WORKER_MB)
    fr = MEM_FRAC if frac is None else float(frac)
    cf = CPU_FRAC if cpu_frac is None else float(cpu_frac)
    cpu = os.cpu_count() or 4
    want = int(want or cpu)
    # ★ CPU 上限：最多只用 80% 的核心（20核 → 16），留出余量给前台
    cpu_cap = max(1, int(round(cpu * cf)))
    total, avail = stats()

    if avail <= 0:          # 读不到内存信息 → 保守用一半核心
        n = max(1, min(want, max(1, cpu // 2)))
        if not quiet:
            print('  [内存] 读不到系统内存，保守用 %d 进程' % n, flush=True)
        return n

    budget = max(0.0, avail * fr - MEM_RESERVE_MB)
    by_mem = int(budget / per) if per > 0 else cpu
    n = max(1, min(want, cpu_cap, max(1, by_mem)))
    if not quiet:
        print('  [资源] 内存 %.1f/%.1fGB（用 %.0f%%）· CPU %d 核（上限 %.0f%% = %d）'
              ' · 每进程 %.0fMB → 本次 %d 进程'
              % (avail / 1024.0, total / 1024.0, fr * 100, cpu, cf * 100, cpu_cap,
                 per, n), flush=True)
    return n


def set_low_priority():
    """把当前进程降为【低于正常】优先级；子进程会继承 → 搜索时前台不卡"""
    try:
        if os.name == 'nt':
            BELOW_NORMAL_PRIORITY_CLASS = 0x4000
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            return bool(ctypes.windll.kernel32.SetPriorityClass(handle, BELOW_NORMAL_PRIORITY_CLASS))
        os.nice(10)
        return True
    except Exception:
        return False


def brief():
    total, avail = stats()
    return '总 %.1fGB / 可用 %.1fGB' % (total / 1024.0, avail / 1024.0)


if __name__ == '__main__':
    print(brief())
    print('建议进程数（最多 20）:', fit_workers(20))
