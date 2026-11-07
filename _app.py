# -*- coding: utf-8 -*-
"""BD2 Arena Tool —— exe 入口（分发器 + 控制台 UTF-8 修正）"""
import multiprocessing
import os
import sys


def _console_utf8():
    """Windows 控制台默认 GBK → 中文乱码，这里强制切到 UTF-8"""
    if os.name != 'nt':
        return
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    os.environ['PYTHONUTF8'] = '1'


def _prepare():
    if not getattr(sys, 'frozen', False):
        return
    os.environ['BD2_HOME'] = os.path.dirname(os.path.abspath(sys.executable))
    mp = getattr(sys, '_MEIPASS', '')
    if mp:
        os.environ['BD2_DATA'] = mp


def main():
    multiprocessing.freeze_support()
    _console_utf8()
    _prepare()
    args = sys.argv[1:]
    if args and args[0].lower().endswith(('.py', '.pyc')):
        name = os.path.splitext(os.path.basename(args[0]))[0]
        sys.argv = [args[0]] + args[1:]
        try:
            mod = __import__(name)
        except Exception as e:
            sys.stderr.write('找不到子命令 %s: %s\n' % (name, e))
            return 1
        fn = getattr(mod, 'main', None)
        if fn is not None:
            fn()
        # 没有 main() = 脚本式模块（顶层代码 import 时就跑完了，比如 build_pool.py）
        return 0
    import bd2dash
    fn = getattr(bd2dash, 'main', None)
    if fn:
        fn()
    return 0


if __name__ == '__main__':
    sys.exit(main())
