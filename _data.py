# -*- coding: utf-8 -*-
"""只读数据文件定位：打包成 exe 后数据在 exe 内部（BD2_DATA），看不到"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def p(name):
    base = os.environ.get('BD2_DATA') or ''
    if base:
        cand = os.path.join(base, name)
        if os.path.exists(cand):
            return cand
    return os.path.join(HERE, name)
