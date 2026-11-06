# -*- coding: utf-8 -*-
"""繁 → 简 转换（用 name_map 里现成的简繁对照自动构建，不依赖外部库）
   name_map 的 key 有简体版本，value 是繁体 → 反推就能得到对照表
"""
import io
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
_T2S = None


def _build():
    global _T2S
    if _T2S is not None:
        return _T2S
    t2s = {}
    try:
        nm = json.load(io.open(os.path.join(HERE, 'name_map.json'), encoding='utf-8'))
    except Exception:
        _T2S = {}
        return _T2S
    for k, v in nm.items():
        if not isinstance(v, dict) or '·' not in k:
            continue
        # key 必须是纯中文（排除英文别名）
        if any(ord(c) < 128 for c in k):
            continue
        trad = '%s·%s' % (v.get('ch') or '', v.get('co') or '')
        if len(trad) != len(k):
            continue
        for a, b in zip(trad, k):
            if a != b and a not in t2s:
                t2s[a] = b
    _T2S = t2s
    return t2s


_CC = None


def _opencc():
    """优先用 opencc（转换最全）；没有就退回 name_map 反推的对照表"""
    global _CC
    if _CC is None:
        try:
            from opencc import OpenCC
            _CC = OpenCC('t2s')
        except Exception:
            _CC = False
    return _CC


def t2s(s):
    """把字符串里的繁体字换成简体（opencc 全量转换，失败退回对照表）"""
    if not s:
        return s
    cc = _opencc()
    if cc:
        try:
            return cc.convert(str(s))
        except Exception:
            pass
    if not s:
        return s
    m = _build()
    return ''.join(m.get(c, c) for c in str(s))


def pairs():
    return _build()


if __name__ == '__main__':
    m = _build()
    print('繁→简 对照表: %d 条' % len(m))
    items = list(m.items())[:40]
    print('  ' + '  '.join('%s→%s' % (a, b) for a, b in items))
    for t in ('莎赫拉查德·蒼藍魔女', '安潔莉卡·墮落之星', '涅肯達莉亞·殘破木乃伊',
              '馬莫尼勒·死亡之夜', '阿奇拉·戰場猛獸', '魯·小紅帽'):
        print('  %-22s → %s' % (t, t2s(t)))
