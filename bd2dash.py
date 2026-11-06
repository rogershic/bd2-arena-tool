# -*- coding: utf-8 -*-
"""BD2 竞技场 本地控制台
启动: python bd2dash.py    → http://127.0.0.1:8765
四个入口: 阵容 / 赛季规则 / 庇佑效果 / 服饰费用
"""
import io
import json
import os
import re
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
PY = r'D:\soft\python3.10\python.exe'
PORT = int(os.environ.get('BD2_PORT') or 8766)
import bd2cfg
import _make_html as MH
import _zh

BASE_ENV = {
    'PYTHONIOENCODING': 'utf-8', 'PYTHONHASHSEED': '0',
    'USE_POT_MAX': '0', 'ENEMY_ALWAYS_CRIT': '1', 'CRIT_RANDOM': '1',
    'BD2_SEASON': '49', 'BD2_LOGIN_FILE': 'batch_capture_s49.jsonl',
    'BD2_SEASON_TAG': '赛季49', 'BD2_MINSCORE': '1400',
}

BUILD = time.strftime('%H:%M:%S')
JOB = {'proc': None, 'lines': [], 'name': '', 'start': 0}
LOCK = threading.Lock()
BLESS_PATH = os.path.join(HERE, 'bless_id_map.json')
NAME_PATH = os.path.join(HERE, 'name_map.json')
COSTID_PATH = os.path.join(HERE, 'costume_cost_byid_s49.json')
SAVED_PATH = os.path.join(HERE, '保存的阵容.json')


def load_saved():
    if not os.path.exists(SAVED_PATH):
        return []
    try:
        d = json.load(io.open(SAVED_PATH, encoding='utf-8'))
        return d if isinstance(d, list) else []
    except Exception:
        return []


def store_saved(lst):
    # ★ 每次写入前先追加一份备份，防止误删/多实例覆盖导致收藏丢失
    try:
        bak = os.path.join(HERE, '保存的阵容.bak.jsonl')
        io.open(bak, 'a', encoding='utf-8').write(
            json.dumps({'at': time.strftime('%Y-%m-%d %H:%M:%S'),
                        'count': len(lst), 'data': lst}, ensure_ascii=False) + '\n')
    except Exception:
        pass
    jsave(SAVED_PATH, lst)


def jload(p):
    return json.load(io.open(p, encoding='utf-8'))


def jsave(p, d):
    tmp = p + '.tmp'
    io.open(tmp, 'w', encoding='utf-8', newline='').write(
        json.dumps(d, ensure_ascii=False, indent=1))
    os.replace(tmp, p)


def fullenv(extra=None):
    e = dict(os.environ)
    e.update(BASE_ENV)
    if extra:
        for k, v in extra.items():
            e[k] = str(v)
    return e


def start_job(name, cmd, extra_env=None):
    with LOCK:
        if JOB['proc'] and JOB['proc'].poll() is None:
            return False, '已有任务在跑：%s' % JOB['name']
        JOB['lines'] = ['=== %s ===' % name]
        JOB['name'] = name
        p = subprocess.Popen(cmd, cwd=HERE, env=fullenv(extra_env),
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             bufsize=1, universal_newlines=True,
                             encoding='utf-8', errors='replace')
        JOB['proc'] = p
    NOISE = ('[onhit_atk]', '已生成: ', '打开方式: ',
             '用 SFTP 同步', '用 HTTP 同步', '建立 SSH 隧道', '隧道就绪: ')

    def reader():
        for line in p.stdout:
            if any(k in line for k in NOISE):
                continue
            JOB['lines'].append(line.rstrip('\n'))
            if len(JOB['lines']) > 4000:
                del JOB['lines'][:1000]
        p.wait()
        JOB['lines'].append('=== 结束 (exit %s) ===' % p.returncode)
    threading.Thread(target=reader, daemon=True).start()
    return True, '已启动：%s' % name


SEASON_TAG = str(bd2cfg.rules().get('season_name') or '')
LIB = {'mtime': None, 'rows': []}
_NORM = {}
_NORMS = {}     # 简体写法 -> (原名, 原名)
_GID = {}


def _build_norm():
    if _NORM:
        return _NORM
    try:
        nm = json.load(io.open(NAME_PATH, encoding='utf-8'))
        for k, v in nm.items():
            if not isinstance(v, dict):
                continue
            if v.get('ch') and v.get('co'):
                _NORM[k] = (v['ch'], v['co'])
                _NORMS['%s·%s' % (_zh.t2s(v['ch']), _zh.t2s(v['co']))] = (v['ch'], v['co'])
        db = json.load(io.open(os.path.join(HERE, 'chars_db.json'), encoding='utf-8'))
        for c in db:
            ch = c.get('character')
            en = (c.get('enName') or '').lower()
            for x in (c.get('costumes') or []):
                co = x.get('costumeName')
                if en:
                    _NORM['%s·%s' % (en, co)] = (ch, co)
                if ch and co:
                    _NORMS['%s·%s' % (_zh.t2s(ch), _zh.t2s(co))] = (ch, co)
                # ★ 2026-11-06 抓包里未翻译的服饰会显示成 id68001 这种 gameId
                gid = str(x.get('gameId') or '')
                if gid.isdigit():
                    _GID[gid] = (ch, co)
                    _GID[gid.lstrip('0')] = (ch, co)
                    _GID[gid.zfill(6)] = (ch, co)
    except Exception:
        pass
    return _NORM


def norm_unit(char, costume):
    """把抓包里的名字统一成中文（简→繁、英→中）"""
    m = _build_norm()
    key = '%s·%s' % (char, costume)
    if key in m:
        return m[key]
    # 大小写/空格容错
    for k, v in m.items():
        if k.lower() == key.lower():
            return v
    # ★ 混合简繁写法（简体角色 + 繁体服饰）→ 归一化后再查
    _build_norm()
    _sk = '%s·%s' % (_zh.t2s(char), _zh.t2s(costume))
    if _sk in _NORMS:
        return _NORMS[_sk]
    # ★ 未翻译条目兜底: 服饰形如 id68001 → 用 gameId 查中文名
    mm = re.match(r'^id(\d+)$', str(costume or '').strip())
    if mm:
        num = mm.group(1)
        for k in (num, num.zfill(6), num.lstrip('0')):
            if k in _GID:
                return _GID[k]
    return (char, costume)


def load_lib():
    """读取阵容总库（优先）/历史库，缓存"""
    for fn in ('阵容总库.jsonl', '阵容历史库.jsonl'):
        p = os.path.join(HERE, fn)
        if not os.path.exists(p):
            continue
        mt = os.path.getmtime(p)
        if LIB['mtime'] == (p, mt):
            return LIB['rows']
        rows = []
        for line in io.open(p, encoding='utf-8', errors='replace'):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if not d.get('units'):
                continue
            # ★ 2026-11-06 用户要求: 阵容库只保留【当前赛季】的记录
            _tag = str(d.get('season') or '')
            if SEASON_TAG and SEASON_TAG not in _tag:
                continue
            rows.append(d)
        rows.sort(key=lambda d: -int(d.get('score') or 0))
        LIB['mtime'] = (p, mt)
        LIB['rows'] = rows
        return rows
    return []


def lib_summary(d, cols=5):
    us = sorted(d.get('units') or [], key=lambda u: u.get('order') or 0)
    out = []
    for u in us:
        try:
            p = int(u.get('pos'))
        except Exception:
            p = 0
        if p < 0:
            p = 0
        ch, co = norm_unit(u.get('char'), u.get('costume'))
        brk = str(u.get('brk') or '').replace('+', '')
        bst = str(u.get('burst') or '')
        tag = ('破%s' % brk if brk and brk != '-' else '')
        if bst.startswith('Lv'):
            tag += ('/爆%s' % bst[2:])
        out.append('%s·%s@%d行%d列%s' % (_zh.t2s(ch), _zh.t2s(co), p // cols + 1, p % cols + 1,
                                          ('(' + tag + ')') if tag else ''))
    return ' ｜ '.join(out)


_COST = None
_ATTR = None


def _maps():
    global _COST, _ATTR
    if _COST is None:
        nm = json.load(io.open(NAME_PATH, encoding='utf-8'))
        _COST = {}
        for v in nm.values():
            if isinstance(v, dict) and v.get('ch') and v.get('co'):
                _COST[(v['ch'], v['co'])] = v.get('cost')
        db = json.load(io.open(os.path.join(HERE, 'chars_db.json'), encoding='utf-8'))
        _ATTR = {}
        for c in db:
            for x in (c.get('costumes') or []):
                _ATTR[(c.get('character'), x.get('costumeName'))] = c.get('attribute')
    return _COST, _ATTR


def enrich_unit(order, pos, ch, co, brk, burst, force=False):
    """force=True: 对手口径（满破+有爆发即爆3）；否则尊重传入的破度/爆发，缺省用满破满爆"""
    cost, attr = _maps()
    def _n(v):
        try:
            return int(str(v).replace('+', '').replace('Lv', '') or 0)
        except Exception:
            return 0
    if force:
        _brk, _bst = norm_stats(ch, co)
    else:
        _hb0 = has_burst(ch, co)
        _brk = 5 if brk in (None, '', '-') else max(0, min(5, _n(brk)))
        _bst = (3 if _hb0 else 0) if burst in (None, '', '-') else max(0, min(3, _n(burst)))
        if not _hb0:
            _bst = 0
    return {'order': order or 1, 'pos': int(pos),
            'char': _zh.t2s(ch), 'costume': _zh.t2s(co),
            'cost': cost.get((ch, co)) or 30,
            'attr': _zh.t2s(attr.get((ch, co)) or '?'),
            'brk': _brk, 'burst': _bst,
            'has_burst': has_burst(ch, co)}




_POOL = {'mtime': None, 'data': None}
_BOXRAW = None
_BOXC = None


def load_pool():
    p = os.path.join(HERE, '_opp_cache.pkl')
    if not os.path.exists(p):
        return []                      # 还没建池 → 空池，别抛异常
    mt = os.path.getmtime(p)
    if _POOL['mtime'] != mt:
        import pickle
        _POOL['data'] = pickle.load(io.open(p, 'rb'))[0]
        _POOL['mtime'] = mt
    return _POOL['data']


def box_raw():
    """我方收藏服饰：原始名 -> (破度, 爆发)"""
    global _BOXRAW
    if _BOXRAW is None:
        try:
            box = json.load(io.open(os.path.join(HERE, 'my_box.json'), encoding='utf-8'))
        except Exception:
            # 没有个人服饰数据也能跑（此时服饰库 = 全部服饰）
            box = {}
        _BOXRAW = {}
        for k, v in box.items():
            if '·' not in k:
                continue
            _BOXRAW[k] = (int(v.get('break') or 5), int(v.get('burst') or 0))
    return _BOXRAW


_BOXKEY = None


def box_key(nch, nco):
    """(角色,服饰) → /api/box 里真实存在的 raw（按简体显示名匹配）"""
    global _BOXKEY
    if _BOXKEY is None:
        _BOXKEY = {}
        for x in box_list():
            _BOXKEY[(_zh.t2s(x['ch']), _zh.t2s(x['co']))] = x['raw']
    return _BOXKEY.get((_zh.t2s(nch), _zh.t2s(nco)))


def box_list():
    """给前端选服饰用：显示简体 + 原始名 + 费用/属性/破/爆"""
    global _BOXC
    if _BOXC is None:
        cost, attr = _maps()
        out = []
        src = dict(box_raw())
        if not src:
            # 没提供 my_box.json → 用数据库里所有服饰（owned=false）
            for (ch, co), (_c, x) in db_costumes().items():
                if not co:
                    continue
                _hb = bool(x.get('burst'))
                src['%s·%s' % (ch, co)] = (5, 3 if _hb else 0)
        for k, (brk, burst) in src.items():
            ch, co = k.split('·', 1)
            nch, nco = norm_unit(ch, co)
            out.append({'raw': k,
                        'ch': _zh.t2s(nch), 'co': _zh.t2s(nco),
                        'cost': cost.get((nch, nco)) or 30,
                        'attr': _zh.t2s(attr.get((nch, nco)) or '?'),
                        'brk': brk, 'burst': burst,
                        'owned': bool(box_raw().get(k)),
                        'has_burst': bool(((db_costumes().get((nch, nco)) or (None, {}))[1] or {}).get('burst'))})
        seen = set()
        uniq = []
        for x in out:
            kk = (x['ch'], x['co'])
            if kk in seen:
                continue
            seen.add(kk)
            uniq.append(x)
        uniq.sort(key=lambda x: (-x['cost'], x['ch'], x['co']))
        _BOXC = uniq
    return _BOXC


def build_units(team, from_box=True):
    """[[ch, co, pos], ...] -> 模拟器单位列表（ch/co 用数据库原名）"""
    import _sim3 as S
    br = box_raw()
    t = []
    for i, it in enumerate(team or []):
        try:
            ch, co, pos = it[0], it[1], int(it[2])
        except Exception:
            continue
        # ★ 2026-11-07 用户要求: 测试时用【用户自己选的】破度/爆发
        #   默认满破满爆（有爆发的服饰爆3），没选就用默认
        _hb = has_burst(ch, co)
        b = 5
        bu = 3 if _hb else 0
        if len(it) > 3 and it[3] not in (None, ''):
            try:
                b = max(0, min(5, int(it[3])))
            except Exception:
                pass
        if len(it) > 4 and it[4] not in (None, ''):
            try:
                bu = max(0, min(3, int(it[4])))
            except Exception:
                pass
        if not _hb:
            bu = 0                     # 该服饰本来没有爆发 → 只能是 0
        u = S.unit_stats(ch, co, i + 1, pos, b, bu)
        if not u:
            return None
        u['pos'] = pos
        u['order'] = i + 1
        t.append(u)
    return t



_ENCN = None


def en2cn_map():
    """英文角色名 -> 简体中文角色名（对战日志里显示的是 enName）"""
    global _ENCN
    if _ENCN is None:
        _ENCN = {}
        try:
            for c in json.load(io.open(os.path.join(HERE, 'chars_db.json'), encoding='utf-8')):
                en = c.get('enName')
                cn = c.get('character')
                if en and cn:
                    _ENCN[en] = _zh.t2s(cn)
                    _ENCN[en.lower()] = _zh.t2s(cn)
        except Exception:
            pass
    return _ENCN


def simp_log(lines):
    """对战日志：繁体转简体 + 英文角色名换中文"""
    m = en2cn_map()
    out = []
    for line in lines:
        t = _zh.t2s(str(line))
        for en, cn in m.items():
            if len(en) > 3 and en in t:
                t = t.replace(en, cn)
        out.append(t)
    return out


def _opp_list(opp):
    """按参数重建对手列表（顺序固定，detail 才能按序号复现同一套）"""
    mode = opp.get('mode') or 'range'
    if mode == 'manual':
        et = build_units(opp.get('team'))
        if not et:
            return []
        return [(et, list(opp.get('bf') or []), list(opp.get('bs') or []), 0,
                 '', '手动阵容')]
    if mode == 'lib':
        uid = str(opp.get('uid') or '')
        for d in load_lib():
            if str(d.get('uid')) == uid:
                team = []
                for z in sorted(d.get('units') or [], key=lambda y: y.get('order') or 0):
                    try:
                        pp = int(z.get('pos'))
                    except Exception:
                        pp = 0
                    c, k = norm_unit(z.get('char'), z.get('costume'))
                    team.append([c, k, pp if pp >= 0 else 0])
                et = build_units(team)
                if not et:
                    return []
                return [(et, d.get('bless_first') or [], d.get('bless_second') or [],
                         int(d.get('score') or 0), str(d.get('uid') or ''),
                         str(d.get('name') or ''))]
        return []
    lo = int(opp.get('lo') or 0)
    hi = int(opp.get('hi') or 99999)
    _sm = opp.get('sample')
    sample = int(_sm) if _sm is not None and str(_sm) != '' else 0
    pool = [y for y in load_pool() if lo <= (y[3] or 0) <= hi]
    if sample and len(pool) > sample:
        import random as _r
        pool = _r.Random(7).sample(pool, sample)
    return pool


def test_detail(payload):
    """重打一场，返回对战日志（用于看为什么输）"""
    import _sim3 as S
    import contextlib
    S.bless_points([])
    our = payload.get('our') or {}
    opp = payload.get('opp') or {}
    idx = int(payload.get('idx') or 0)
    side = payload.get('side') or 'f'
    mine = build_units(our.get('team'))
    if not mine:
        return {'ok': False, 'msg': '我方阵容解析失败'}
    opps = _opp_list(opp)
    if idx < 0 or idx >= len(opps):
        return {'ok': False, 'msg': '对手序号越界（可能参数变了，重新测试一次）'}
    y = opps[idx]
    buf = io.StringIO()
    S.VERBOSE[0] = True
    try:
        with contextlib.redirect_stdout(buf):
            if side == 'f':
                r = S.battle(S.clone_team(mine), S.clone_team(y[0]), True,
                             list(our.get('bf') or []), y[2])
            else:
                r = S.battle(S.clone_team(mine), S.clone_team(y[0]), False,
                             list(our.get('bs') or []), y[1])
    except Exception as _e:
        return {'ok': False, 'msg': '模拟失败: %s' % _e}
    finally:
        S.VERBOSE[0] = False
    lines = simp_log([l for l in buf.getvalue().splitlines() if l.strip()][-220:])
    units = []
    for u in (y[0] or []):
        nm = str(u.get('name') or '')
        units.append({'name': _zh.t2s(nm.replace('·', '·')),
                      'pos': int(u.get('pos') or 0)})
    return {'ok': True, 'result': ('胜' if r[0] == 'A' else '负'), 'rounds': r[1],
            'side': ('先攻' if side == 'f' else '后攻'),
            'score': (y[3] if len(y) > 3 else 0),
            'name': (_zh.t2s(str(y[5] or '')) if len(y) > 5 else ''),
            'uid': (str(y[4] or '') if len(y) > 4 else ''),
            'units': units, 'log': lines}


def run_test(payload):
    """返回 {'f':先攻胜率, 'b':后攻胜率, 'comb':综合, 'games':对战数, 'sets':对手数}"""
    import _sim3 as S
    S.bless_points([])
    our = payload.get('our') or {}
    opp = payload.get('opp') or {}
    n = max(1, int(payload.get('n') or 3))

    mine = build_units(our.get('team'))
    if not mine or len(mine) < 1:
        return {'ok': False, 'msg': '我方阵容解析失败，请检查服饰是否都在收藏里'}
    # ★ 费用上限校验（规则从 season_map 读）
    _maxc = int(bd2cfg.rules().get('max_cost') or 240)
    _cost, _ = _maps()
    _tot = 0
    for _it in (our.get('team') or []):
        _c2, _k2 = norm_unit(_it[0], _it[1])
        _tot += _cost.get((_c2, _k2)) or 30
    if _tot > _maxc:
        return {'ok': False, 'msg': '我方总费用 %d 超过上限 %d' % (_tot, _maxc)}
    if len(our.get('team') or []) > int(bd2cfg.rules().get('max_units') or 7):
        return {'ok': False, 'msg': '我方人数超过上限'}
    bf, bs = list(our.get('bf') or []), list(our.get('bs') or [])

    opps = _opp_list(opp)
    if not opps:
        return {'ok': False, 'msg': '这个分数区间没有对手'}

    a = b = 0
    total = len(opps) * n
    import random as _r
    losers = []
    allrows = []
    for i, y in enumerate(opps):
        eu, ebf, ebs = y[0], y[1], y[2]
        fw = bw = 0
        for r in range(n):
            _r.seed(1000 + r + i * 17)
            if S.battle(S.clone_team(mine), S.clone_team(eu), True, bf, ebs)[0] == 'A':
                a += 1
                fw += 1
            _r.seed(2000 + r + i * 17)
            if S.battle(S.clone_team(mine), S.clone_team(eu), False, bs, ebf)[0] == 'A':
                b += 1
                bw += 1
        names = []
        for u0 in (eu or []):
            nm0 = str(u0.get('name') or '').split('·')[-1]
            if nm0:
                names.append(_zh.t2s(nm0))
        row = {'idx': i, 'score': (y[3] if len(y) > 3 else 0),
               'name': (_zh.t2s(str(y[5] or '')) if len(y) > 5 else ''),
               'uid': (str(y[4] or '') if len(y) > 4 else ''),
               'fw': fw, 'ft': n, 'bw': bw, 'bt': n,
               'lineup': ' · '.join(names[:7])}
        allrows.append(row)
        if fw < n or bw < n:
            losers.append(dict(row))
    losers.sort(key=lambda x: ((x['ft'] - x['fw']) + (x['bt'] - x['bw'])), reverse=True)
    if total <= 0:
        return {'ok': False, 'msg': '没有对手可测'}
    f, bk = 100.0 * a / total, 100.0 * b / total
    return {'ok': True, 'f': f, 'b': bk, 'comb': (f + bk) / 2,
            'games': total, 'sets': len(opps), 'n': n, 'losers': losers[:60],
            'rows': sorted(allrows, key=lambda x: ((x['ft'] - x['fw']) + (x['bt'] - x['bw'])),
                           reverse=True)[:80],
            'n_losers': len(losers)}




_DBCO = None


def db_costumes():
    """(角色, 服饰) -> DB 原始记录"""
    global _DBCO
    if _DBCO is None:
        db = json.load(io.open(os.path.join(HERE, 'chars_db.json'), encoding='utf-8'))
        _DBCO = {}
        for c in db:
            for x in (c.get('costumes') or []):
                _DBCO[(c.get('character'), x.get('costumeName'))] = (c, x)
    return _DBCO


_BURSTMAP = None


def burst_map():
    """(角色,服饰) -> 是否有爆发（简体键 + 繁体键都放一份）"""
    global _BURSTMAP
    if _BURSTMAP is None:
        _BURSTMAP = {}
        for (ch, co), (_c, x) in db_costumes().items():
            v = bool(x.get('burst'))
            _BURSTMAP[(ch, co)] = v
            _BURSTMAP[(_zh.t2s(ch), _zh.t2s(co))] = v
    return _BURSTMAP


def has_burst(ch, co):
    return bool(burst_map().get((ch, co)) or burst_map().get((_zh.t2s(ch), _zh.t2s(co))))


def norm_stats(nch, nco, brk=None, bst=None):
    """★ 2026-11-07 用户规则: 一律满破；该服饰有爆发就爆3，没爆发就0"""
    return 5, (3 if has_burst(nch, nco) else 0)


def costume_detail(raw, brk=5, bst=0):
    """服饰详情：填入当前破度/爆发的技能文本 + 范围形状"""
    import _sim3 as S
    import re as _re
    if '·' not in raw:
        return {'ok': False, 'msg': '参数不对'}
    ch, co = raw.split('·', 1)
    nch, nco = norm_unit(ch, co)
    rec = db_costumes().get((nch, nco))
    if not rec:
        return {'ok': False, 'msg': '数据库里没有这件服饰'}
    c, x = rec
    brk = max(0, min(5, int(brk)))
    bst = max(0, min(3, int(bst)))
    bursts = x.get('burst') or []
    if not bursts:
        bst = 0
    u = S.unit_stats(nch, nco, 1, 12, brk, bst) or {}

    # ---- 数值：等级行 + 潜能 + 爆发（和 unit_stats 同口径）----
    lv = x.get('level') or []
    vals = {}
    if lv:
        for k, v in lv[min(brk, len(lv) - 1)].items():
            sv = str(v)
            if _re.match(r'(VALUE|HIT)\d', k) and sv.replace('.', '').isdigit():
                vals[k] = float(sv)
    for sp in (x.get('skillPotential') or []):
        for sw in (sp.get('switches') or []):
            if sw.get('target') in vals and isinstance(sw.get('value'), (int, float)):
                vals[sw['target']] += sw['value']
    for b in bursts[:bst]:
        for sw in (b.get('switches') or []):
            if sw.get('target') in vals and isinstance(sw.get('value'), (int, float)):
                vals[sw['target']] += sw['value']

    def fill(t):
        def rep(m):
            k = m.group(1)
            v = vals.get(k)
            if v is None:
                return m.group(0)
            return str(int(v)) if abs(v - int(v)) < 1e-9 else ('%.1f' % v)
        return _re.sub(r'\{(VALUE\d|HIT\d)\}', rep, t or '')

    skill = [fill(t) for t in (x.get('skill') or [])]

    # ---- 范围：基础 range → 潜能 Range → 爆发 Range ----
    rc = x.get('range') or ''
    for sp in (x.get('skillPotential') or []):
        if sp.get('type') == 'Range' and sp.get('value'):
            rc = sp['value']
    for b in bursts[:bst]:
        if b.get('type') == 'Range' and b.get('value'):
            rc = b['value']
        for ex in (b.get('extraEffects') or []):
            if ex.get('type') == 'Range' and ex.get('value'):
                rc = ex['value']

    return {'ok': True, 'raw': raw, 'ch': _zh.t2s(nch), 'co': _zh.t2s(nco),
            'cost': (_maps()[0].get((nch, nco)) or 30),
            'attr': _zh.t2s(u.get('attr') or c.get('attribute') or '?'),
            'type': u.get('type') or c.get('atkType'),
            'brk': brk, 'bst': bst, 'has_burst': bool(bursts),
            'skill_name': x.get('skillName') or '',
            'skill': skill,
            'hits': u.get('hits'), 'per': u.get('per'), 'per_main': u.get('per_main'),
            'basis': u.get('basis'), 'target': _zh.t2s(u.get('target') or ''),
            'shape': u.get('shape') or [],
            'range_code': rc,
            'levels': [dict(r) for r in lv],
            'burst_text': [(_zh.t2s(b.get('value') or '') ) for b in bursts],
            'potential_text': [_zh.t2s(sp.get('value') or '') for sp in (x.get('skillPotential') or [])]}


def pool_stats():
    out = {}
    try:
        out['saved'] = len(load_saved())
    except Exception:
        out['saved'] = 0
    try:
        rows = load_lib()
        sc = [int(d.get('score') or 0) for d in rows if d.get('score')]
        out['lib'] = {'n': len(rows), 'min': min(sc) if sc else 0,
                      'max': max(sc) if sc else 0}
        # ★ 数据更新时间（看抓取后有没有刷新）
        import time as _t2
        try:
            _cs = json.load(io.open(os.path.join(HERE, 'cloud_sync.json'), encoding='utf-8'))
            out['cloud'] = {'synced': _cs.get('ts'), 'remote': _cs.get('remote_ts')}
        except Exception:
            out['cloud'] = None
        for _fn in ('阵容总库.jsonl', '阵容历史库.jsonl'):
            _p = os.path.join(HERE, _fn)
            if os.path.exists(_p):
                out['lib']['updated'] = _t2.strftime(
                    '%m-%d %H:%M', _t2.localtime(os.path.getmtime(_p)))
                out['lib']['src'] = _fn
                break
    except Exception:
        out['lib'] = {'n': 0, 'min': 0, 'max': 0}
    out['rules'] = bd2cfg.rules()
    return out


PAGE = r"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>BD2 竞技场控制台</title><meta http-equiv="Cache-Control" content="no-store,no-cache,must-revalidate"><meta http-equiv="Pragma" content="no-cache"><style>
*{scrollbar-width:thin;scrollbar-color:#3a4761 transparent}
::-webkit-scrollbar{width:9px;height:9px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:#33405a;border-radius:9px;border:2px solid transparent;
       background-clip:padding-box}
::-webkit-scrollbar-thumb:hover{background:#4a5c7d;background-clip:padding-box}
::-webkit-scrollbar-corner{background:transparent}
*{box-sizing:border-box}
body{margin:0;background:#0f1218;color:#e8ecf5;font-family:-apple-system,"Microsoft YaHei",sans-serif}
header{padding:14px 24px;border-bottom:1px solid #232a38;display:flex;align-items:center;gap:14px;flex-wrap:wrap}
h1{font-size:17px;margin:0;white-space:nowrap}
.pill{font-size:12px;padding:3px 10px;border-radius:20px;background:#1b2230;color:#8b97a8}
.tabs{display:flex;gap:6px;margin-left:12px}
.tab{padding:6px 14px;border-radius:8px;background:#171c26;border:1px solid #232a38;font-size:13px;cursor:pointer;color:#a8b3c4}
.tab.on{background:#1d4ed8;border-color:#2563eb;color:#fff}
.pane{display:none;padding:16px 24px}
.pane.on{display:block}
.grid2{display:grid;grid-template-columns:340px 1fr;gap:16px}
.panel{background:#171c26;border:1px solid #232a38;border-radius:12px;padding:16px}
.tt{font-size:13px;color:#8b97a8;margin:0 0 12px;letter-spacing:.5px}
button{background:#1f2937;color:#e8ecf5;border:1px solid #2d3748;border-radius:8px;padding:9px 12px;font-size:13px;cursor:pointer;width:100%;margin-bottom:8px;text-align:left}
button:hover{background:#26303f;border-color:#4dabf7}
button.primary{background:#1d4ed8;border-color:#2563eb}
button.primary:hover{background:#2563eb}
input,select{background:#12161e;border:1px solid #2d3748;color:#e8ecf5;border-radius:7px;padding:7px 9px;font-size:13px;width:100%;margin-bottom:8px}
.row{display:flex;gap:8px}
.kv{display:flex;justify-content:space-between;font-size:12.5px;padding:4px 0;color:#a8b3c4}
.kv b{color:#e8ecf5}
pre{background:#0b0e13;border:1px solid #232a38;border-radius:10px;padding:12px;font-size:12px;line-height:1.55;height:calc(100vh - 250px);overflow:auto;margin:0;white-space:pre-wrap;word-break:break-all;font-family:Consolas,monospace}
a.link{color:#4dabf7;font-size:12.5px;text-decoration:none}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #232a38}
th{color:#8b97a8;font-weight:500;position:sticky;top:0;background:#171c26}
tr:hover td{background:#1b2230}
td input{margin:0;padding:3px 6px;font-size:12px}
.scroll{max-height:calc(100vh - 240px);overflow:auto;border:1px solid #232a38;border-radius:10px}
.tag{font-size:11px;padding:1px 7px;border-radius:5px;background:#1b2230;color:#8b97a8}
.f-label{font-size:12px;color:#8b97a8;margin:10px 0 4px}
.modal-bg{display:none;position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:99;
          align-items:center;justify-content:center;padding:16px}
.modal-bg.on{display:flex}
.modal{background:#151a23;border:1px solid #2b3444;border-radius:15px;width:100%;max-width:520px;
       max-height:92vh;overflow:auto;box-shadow:0 24px 64px rgba(0,0,0,.6)}
.mhead{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;
       border-bottom:1px solid #232a38;position:sticky;top:0;background:#151a23;z-index:3}
.mtitle{font-size:14.5px;font-weight:700}
.mclose{cursor:pointer;color:#7d8899;font-size:14px;padding:3px 9px;border-radius:7px}
.mclose:hover{background:#232a38;color:#fff}
.mbody{padding:12px 16px 16px}
.swrap{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:11px}
.schip{background:#1b2230;border:1px solid #232a38;border-radius:8px;padding:4px 9px;
       font-size:11px;color:#7d8899}
.schip b{color:#e8ecf5;font-size:12.5px;margin-left:5px;font-weight:600}
.boardbox{background:#1b2230;border:1px solid #33405a;border-radius:12px;padding:9px 10px 10px;margin-bottom:12px}
.glab{display:grid;grid-template-columns:16px repeat(5,1fr);gap:4px;margin-bottom:4px}
.glab span{font-size:10px;color:#7d8899;text-align:center;font-weight:600}
.brow{display:grid;grid-template-columns:16px repeat(5,1fr);gap:4px;margin-bottom:4px}
.brow .rlab{font-size:10px;color:#7d8899;display:flex;align-items:center;justify-content:center;font-weight:600}
.slot{height:64px;border-radius:9px;background:#252e3d;border:1px solid #3a4761;
      display:flex;flex-direction:column;align-items:center;justify-content:center;
      gap:2px;overflow:hidden;position:relative;padding:3px 3px}
.slot.on{background:linear-gradient(180deg,#2e3a4c,#242e3d);border:1.5px solid var(--c);
         box-shadow:0 0 0 1px rgba(255,255,255,.04) inset}
.slot .nm{font-size:11.5px;font-weight:700;line-height:1.15;color:#f2f6fb;white-space:nowrap;
          overflow:hidden;text-overflow:ellipsis;max-width:100%;padding:0 1px}
.slot .cs{font-size:10px;color:#b9c6d8;line-height:1.15;white-space:nowrap;
          overflow:hidden;text-overflow:ellipsis;max-width:100%}
.slot .cf{font-size:9px;color:#9aa8ba;line-height:1.15;white-space:nowrap;font-weight:600}
.slot .od{position:absolute;top:1px;right:3px;font-size:9px;color:#ffd166;font-weight:800}
.ulist{display:flex;flex-direction:column;gap:5px}
.urow{display:flex;align-items:center;gap:8px;background:#1b2230;border:1px solid #232a38;
      border-left:3px solid var(--c);border-radius:8px;padding:6px 9px}
.uord{font-size:10.5px;color:#ffd166;font-weight:700;flex:none;width:20px}
.uname2{flex:1;font-size:12.5px;line-height:1.25;min-width:0}
.uname2 b{font-weight:600}
.uname2 span{display:block;font-size:10.5px;color:#8e9bb0;white-space:nowrap;
             overflow:hidden;text-overflow:ellipsis}
.upos{font-size:10.5px;color:#6d7888;flex:none;width:52px;text-align:right}
.umeta2{font-size:10.5px;color:#8e9bb0;flex:none;width:96px;text-align:right;white-space:nowrap}
.hr{height:1px;background:#232a38;margin:11px 0 9px}
.blrow{display:flex;gap:8px;margin-top:7px;font-size:11.5px;line-height:1.65}
.blrow .k{color:#6d7888;flex:none;width:30px}
.blrow .v{color:#b9c4d4;flex:1}
.mbtn{width:100%;background:#1d4ed8;border:1px solid #2563eb;border-radius:9px;padding:9px;
      font-size:13px;color:#fff;cursor:pointer;margin-top:13px}
.mbtn:hover{background:#2563eb}
.mbtn.danger{background:#7f1d1d;border-color:#b91c1c}
.mbtn.danger:hover{background:#b91c1c}
.tsum{font-size:13px;color:#b9c4d8;background:#1b2230;border:1px solid #232a38;
      border-radius:9px;padding:9px 11px}
.pickwrap{display:flex;flex-wrap:wrap;gap:5px;max-height:150px;overflow:auto;
      background:#12161e;border:1px solid #232a38;border-radius:9px;padding:7px}
.pchip{font-size:11.5px;background:#1b2230;border:1px solid #2b3444;border-radius:7px;
      padding:3px 8px;cursor:pointer;color:#c3cddb;white-space:nowrap}
.pchip i{font-style:normal;margin-left:4px;font-size:10.5px}
.pchip.on{background:#1d4ed8;color:#fff}
.pchip.used{opacity:.45}
.bchips{display:flex;flex-wrap:wrap;gap:5px;max-height:120px;overflow:auto;padding:2px}
.bchip2{font-size:11px;background:#1b2230;border:1px solid #2b3444;border-radius:7px;
        padding:3px 7px;cursor:pointer;color:#a8b3c4;user-select:none}
.bchip2.on{background:#1d4ed8;border-color:#2563eb;color:#fff}
.erow{display:flex;gap:6px;margin-bottom:5px;align-items:center}
.erow .idx{font-size:11px;color:#ffd166;width:20px;flex:none}
.erow select{margin:0}
.qbtn{width:auto;display:inline-block;padding:4px 9px;font-size:11.5px;margin:0 5px 5px 0;
      background:#1b2230;border:1px solid #2d3748;border-radius:7px}
.qbtn:hover{background:#26303f;border-color:#4dabf7}

/* ---------- 操作区按钮（2026-11-07 美化） ---------- */
.act{display:flex;align-items:center;gap:9px;text-align:left;position:relative;
     height:42px;padding:0 13px;border-radius:10px;font-size:13px;
     transition:transform .14s, box-shadow .18s, background .18s, border-color .18s}
.act .ic{width:23px;height:23px;border-radius:7px;display:flex;align-items:center;
     justify-content:center;font-size:12px;flex:none;font-weight:700}
.act .lb{flex:1}
.act .sub{font-size:11px;opacity:.62;font-weight:400}
.act:hover{transform:translateY(-1px)}
.act:active{transform:translateY(0)}

/* 主操作：搜索 */
.act-go{background:linear-gradient(180deg,#2f6bf0,#1d4ed8);border:1px solid #4d84f7;
     color:#fff;font-weight:600;box-shadow:0 2px 12px rgba(37,99,235,.30)}
.act-go .ic{background:rgba(255,255,255,.18)}
.act-go:hover{background:linear-gradient(180deg,#4d84f7,#2563eb);border-color:#7ea9fb;
     box-shadow:0 5px 18px rgba(37,99,235,.45)}

/* 次级：同步云端 */
.act-sync{background:#141d29;border:1px solid #24405c;color:#7cc0ff;font-weight:600}
.act-sync .ic{background:rgba(124,192,255,.15);color:#7cc0ff}
.act-sync:hover{background:#182634;border-color:#3b82f6;color:#a9d4ff;
     box-shadow:0 4px 14px rgba(59,130,246,.22)}

/* 危险：停止 */
.act-stop{background:#1b1315;border:1px solid #57232c;color:#ff9b9b;font-weight:600}
.act-stop .ic{background:rgba(255,120,120,.15);color:#ff8a8a;font-size:10px}
.act-stop:hover{background:#26161a;border-color:#dc2626;color:#ffc0c0;
     box-shadow:0 4px 14px rgba(220,38,38,.22)}
.act-stop.running{background:#2a1418;border-color:#dc2626;color:#ffc7c7;
     animation:stopPulse 1.6s ease-in-out infinite}
.act-stop.idle{opacity:.35;pointer-events:none}
@keyframes stopPulse{0%,100%{box-shadow:0 0 0 rgba(220,38,38,0)}50%{box-shadow:0 0 14px rgba(220,38,38,.35)}}
</style></head><body>
<header>
  <h1>BD2 黄金竞技场 · 控制台</h1>
  <div id="jserr" style="display:none;position:fixed;bottom:10px;right:10px;max-width:560px;
  background:#3a1418;border:1px solid #dc2626;color:#ffbdbd;padding:9px 12px;border-radius:9px;
  font-size:11.5px;line-height:1.6;z-index:400;white-space:pre-wrap;box-shadow:0 6px 24px rgba(0,0,0,.5)"></div>
<div class="tabs">
    <div class="tab on" data-t="team">阵容</div>
    <div class="tab" data-t="test">测试阵容</div>
    <div class="tab" data-t="lib">阵容库</div>
    <div class="tab" data-t="saved">保存的阵容</div>
    <div class="tab" data-t="rules">赛季规则</div>
    <div class="tab" data-t="bless">庇佑效果</div>
    <div class="tab" data-t="cost">服饰费用</div>
  </div>
  <span class="pill" id="jobst">空闲</span>
</header>

<div class="pane on" id="p-team"><div class="grid2">
  <div class="panel">
    <p class="tt">操作</p>
    <!-- 抓取已搬到云服务器自动跑，本地按钮暂时隐藏（要恢复就把 display:none 去掉） -->
    <button class="primary" onclick="run('capture',{n:1000})" style="display:none">① 全量抓取（约 4 分钟）</button>
    <button class="act act-sync" onclick="syncCloud()">
      <span class="ic">↓</span><span class="lb">同步云端数据</span>
      <span class="sub">拉最新</span></button>
    <div class="row"><input id="lo" value="2000"><input id="hi" value="2299"></div>
    <div class="row"><input id="sn" value="6" title="N（越大越准越慢）">
      <label style="font-size:12px;color:#a8b3c4;display:flex;align-items:center;gap:5px;white-space:nowrap">
      <input type="checkbox" id="sq" checked style="width:auto;margin:0">快速模式（默认开）</label></div>

    <div id="sysbox" style="background:#141a24;border:1px solid #232a38;border-radius:9px;
         padding:8px 10px;margin:8px 0;font-size:11.5px;color:#a8b3c4;line-height:1.7">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <span>机器状态</span>
        <span class="qbtn" style="margin:0;padding:1px 7px" onclick="loadSys()">刷新</span>
      </div>
      <div id="sysinfo" style="color:#6d7888">检测中…</div>
      <div class="row" style="margin-top:6px;align-items:center">
        <span style="white-space:nowrap">线程数</span>
        <input id="sw" value="0" title="并发进程数，建议不超过推荐值" style="width:80px;margin:0">
        <span class="qbtn" style="margin:0;padding:1px 7px" onclick="useRec()">用推荐值</span>
      </div>
    </div>
    <button class="act act-go" onclick="runSearch()">
      <span class="ic">③</span><span class="lb">搜索该分段阵容</span></button>
    <button class="act act-stop" id="btn_stop" onclick="stopJob()">
      <span class="ic">■</span><span class="lb">停止搜索</span></button>
    <p class="tt" style="margin-top:16px">状态</p>
    <div id="stat"></div>
  </div>
  <div class="panel">
    <p class="tt">当前阵容 <span id="cur_seg" style="color:#5c6675">-</span>
      <span class="qbtn" style="float:right;margin:0" onclick="loadCur()">刷新</span></p>
    <div id="cur_box" style="font-size:12px;color:#6d7888;max-width:430px">还没有搜索结果</div>
    <p class="tt" style="margin-top:10px">先攻庇佑</p><div id="cur_bf" class="bchips"></div>
    <p class="tt" style="margin-top:8px">后攻庇佑</p><div id="cur_bs" class="bchips"></div>
    <button class="primary" style="margin-top:10px;width:auto;padding:6px 16px;display:inline-block"
      onclick="saveCurCfg()">＋ 保存这套阵容</button>
    <p class="tt" style="margin-top:16px">运行日志</p><pre id="log">（暂无任务）</pre>
  </div>
</div></div>

<div class="pane" id="p-rules"><div class="grid2">
  <div class="panel">
    <p class="tt">赛季规则</p>
    <div class="f-label">赛季编号</div><input id="r_season" readonly>
    <div class="f-label">名称</div><input id="r_name" readonly>
    <div class="row">
      <div style="flex:1"><div class="f-label">行数</div><input id="r_rows" readonly></div>
      <div style="flex:1"><div class="f-label">列数</div><input id="r_cols" readonly></div>
    </div>
    <div class="row">
      <div style="flex:1"><div class="f-label">人数上限</div><input id="r_units" readonly></div>
      <div style="flex:1"><div class="f-label">费用上限</div><input id="r_cost" readonly></div>
    </div>
    <div class="row">
      <div style="flex:1"><div class="f-label">先攻庇佑点</div><input id="r_bf" readonly></div>
      <div style="flex:1"><div class="f-label">后攻庇佑点</div><input id="r_bs" readonly></div>
    </div>
    <div class="f-label">禁用格</div>
    <div id="r_grid"></div>

  </div>
  <div class="panel">
    <p class="tt">当前规则</p><div id="ruleshow"></div>
    <p class="tt" style="margin-top:18px">站位示意</p><div id="gridshow"></div>
  </div>
</div></div>

<div class="pane" id="p-bless"><div class="panel">
  <p class="tt">庇佑效果</p>
  <input id="bq" placeholder="搜索名称或效果…" oninput="loadBless()">
  <div class="scroll"><table><thead><tr>
    <th style="width:160px">名称</th><th style="width:70px">点数</th><th style="width:90px">类别</th>
    <th>效果</th></tr></thead><tbody id="btb"></tbody></table></div>
</div></div>

<div class="pane" id="p-cost"><div class="panel">
  <p class="tt">服饰费用</p>
  <input id="cq" placeholder="搜索角色名或服饰名…" oninput="loadCost()">
  <div class="scroll"><table><thead><tr>
    <th>角色·服饰</th><th style="width:100px">费用</th></tr></thead><tbody id="ctb"></tbody></table></div>
</div></div>

<div class="pane" id="p-lib"><div class="panel">
    <p class="tt">阵容库</p>
    <input id="lq" placeholder="搜索玩家名 / UID…（输入即时筛选）" oninput="loadLib()"
           style="margin-bottom:10px">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;flex-wrap:wrap">
      <span style="font-size:13px;color:#a8b3c4;white-space:nowrap">分數</span>
      <input id="llo" type="number" placeholder="最低" onkeydown="if(event.key==='Enter')loadLib()"
             style="width:110px;margin:0">
      <span style="color:#6d7888">～</span>
      <input id="lhi" type="number" placeholder="最高" onkeydown="if(event.key==='Enter')loadLib()"
             style="width:110px;margin:0">
      <button class="qbtn" onclick="loadLib()" style="background:#1d4ed8;border-color:#2563eb">查询</button>
      <button class="qbtn" onclick="setSeg('','')">清除</button>
      <span style="font-size:11.5px;color:#6d7888">留空 = 不限</span>
    </div>
    <div id="linfo" style="font-size:12px;color:#6d7888;margin-bottom:6px"></div>
    <div class="scroll" style="max-height:calc(100vh - 290px)"><table><thead><tr>
      <th style="width:60px">分数</th><th style="width:110px">名字</th><th style="width:90px">UID</th>
      <th style="width:70px">赛季</th><th>阵容</th></tr></thead><tbody id="ltb"></tbody></table></div>
</div></div>

<div class="pane" id="p-saved"><div class="panel">
    <p class="tt">保存的阵容</p>
    <div class="scroll" style="max-height:calc(100vh - 300px)"><table><thead><tr>
      <th style="width:200px">名称</th><th style="width:100px">赛季</th>
      <th style="width:80px">费用</th><th style="width:140px">保存时间</th>
      <th style="width:70px">操作</th></tr></thead><tbody id="stb"></tbody></table></div>
</div></div>


<div class="pane" id="p-test"><div class="grid2" style="grid-template-columns:1fr 1fr">
  <div class="panel">
    <p class="tt">我方阵容 <span id="t_our_sum" style="color:#5c6675">还没选</span>
      <span class="qbtn" style="float:right;margin:0 0 0 6px" onclick="openStatSet('our')">破度/爆发</span>
      <span class="qbtn" style="float:right;margin:0 0 0 6px" onclick="openImport('our')">导入收藏</span>
      <span class="qbtn" style="float:right;margin:0" onclick="saveOur()">保存</span>
      <span class="qbtn" style="float:right;margin:0 0 0 6px;border-color:#5c2530;color:#ff9b9b"
            onclick="resetOur()">重置</span></p>
    <div id="t_our_board"></div>
    <p class="tt" style="margin-top:10px">先攻庇佑 <span id="t_our_bfpt" style="color:#5c6675">0 / 6 点</span></p>
    <div id="t_our_bf" class="bchips"></div>
    <p class="tt" style="margin-top:8px">后攻庇佑 <span id="t_our_bspt" style="color:#5c6675">0 / 8 点</span></p>
    <div id="t_our_bs" class="bchips"></div>
  </div>
  <div class="panel">
    <p class="tt">对手</p>
    <div class="row" style="margin-bottom:8px">
      <select id="t_mode" onchange="testMode()">
        <option value="range">按分数区间（从对手池抽样）</option>
        <option value="lib">指定阵容库玩家</option>
        <option value="manual">手动指定阵容</option>
      </select>
    </div>
    <div id="t_opp_range">
      <div style="font-size:11.5px;color:#8b97a8;margin-bottom:6px">对手分数范围</div>
      <div class="row" style="align-items:center">
        <span style="font-size:12px;color:#a8b3c4;white-space:nowrap">从</span>
        <input id="t_lo" type="number" value="2400" title="最低分（含）" style="width:90px"
               oninput="showPoolN()">
        <span style="font-size:12px;color:#a8b3c4">分 到</span>
        <input id="t_hi" type="number" value="2500" title="最高分（含）" style="width:90px"
               oninput="showPoolN()">
        <span style="font-size:12px;color:#a8b3c4">分</span>
      </div>
      <div class="row" style="align-items:center;margin-top:6px">
        <span style="font-size:12px;color:#a8b3c4;white-space:nowrap">抽</span>
        <input id="t_sample" type="number" value="0" title="0 = 该区间全部对手；填数字 = 随机抽这么多套"
               style="width:90px" oninput="showPoolN()">
        <span style="font-size:11.5px;color:#6d7888">套（0 = 该区间全部）</span>
      </div>
      <div id="t_pooln" style="font-size:11.5px;color:#5c6675;margin-top:4px"></div>
    </div>
    <div id="t_opp_lib" style="display:none">
      <div class="row" style="align-items:center">
        <button id="t_libbtn" style="margin:0;flex:1;text-align:left" onclick="openLibPick()">
          点击选择阵容库玩家…</button>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-top:4px">
        <span id="t_libinfo" style="font-size:11.5px;color:#6d7888">未选择</span>
        <span style="display:flex;gap:6px">
          <span class="qbtn" style="margin:0" onclick="saveOpp()">保存他的阵容</span>
          <span class="qbtn" style="margin:0;border-color:#5c2530;color:#ff9b9b"
                onclick="resetOpp()">重置</span></span></div>
      <div id="t_lib_board" style="margin-top:8px"></div>
    </div>
    <div id="t_opp_manual" style="display:none">
      <div id="t_opp_sum" class="tsum">还没选对手阵容</div>
      <div style="text-align:right;margin-top:6px">
        <span class="qbtn" style="margin:0 0 0 6px" onclick="openStatSet('opp')">破度/爆发</span>
        <span class="qbtn" style="margin:0 0 0 6px" onclick="openImport('opp')">导入收藏</span>
        <span class="qbtn" style="margin:0" onclick="saveOpp()">保存</span>
        <span class="qbtn" style="margin:0 0 0 6px;border-color:#5c2530;color:#ff9b9b"
              onclick="resetOpp()">重置</span></div>
      <div id="t_opp_board" style="margin-top:6px"></div>
      <p class="tt" style="margin-top:10px">对手先攻庇佑 <span id="t_opp_bfpt" style="color:#5c6675">0 / 6 点</span></p>
      <div id="t_opp_bf" class="bchips"></div>
      <p class="tt" style="margin-top:8px">对手后攻庇佑 <span id="t_opp_bspt" style="color:#5c6675">0 / 8 点</span></p>
      <div id="t_opp_bs" class="bchips"></div>
    </div>
    <div class="row" style="margin-top:12px;align-items:center">
      <span style="font-size:12px;color:#a8b3c4;white-space:nowrap">每套打</span>
      <input id="t_n" type="number" value="3" title="每套对手阵容打几场（N）" style="width:70px">
      <span style="font-size:11.5px;color:#6d7888;white-space:nowrap">场（N）</span>
      <button class="act act-go" style="width:auto;flex:none;padding:0 26px"
              onclick="runTest()">
        <span class="ic">▶</span><span class="lb">开始测试</span></button>
    </div>
    <div id="t_result" style="margin-top:14px;font-size:13px;color:#6d7888">还没测试</div>
    <div id="t_hint" style="font-size:11px;color:#5c6675;line-height:1.65;margin-top:8px">
      先攻 = 我方先攻时的胜率　后攻 = 我方后攻时的胜率　综合 = 两者平均<br>
      总场次 = 对手套数 × 每套场数（每场用不同随机种子，避免刚好走运）
    </div>
  </div>
</div></div>

<div class="modal-bg" id="ccmodal" style="z-index:162" onclick="if(event.target===this)closeCloudCfg()">
  <div class="modal" style="max-width:480px">
    <div class="mhead"><span class="mtitle">云端数据来源</span>
      <span class="mclose" onclick="closeCloudCfg()">✕</span></div>
    <div class="mbody">
      <div style="font-size:11.5px;color:#6d7888;line-height:1.6;margin-bottom:10px">
        两种填法，任选其一：
      </div>
      <div style="font-size:12px;color:#8fa6c4;margin-bottom:5px">① 数据地址（推荐，直接下载）</div>
      <div class="row" style="align-items:center;margin-bottom:6px">
        <input id="cc_url" placeholder="https://你的域名/bd2/阵容总库.jsonl"
               style="margin:0">
      </div>
      <div class="row" style="align-items:center;margin-bottom:12px">
        <span style="font-size:11.5px;color:#5c6675;white-space:nowrap">口令(可选)</span>
        <input id="cc_token" placeholder="公开地址留空" style="margin:0;width:150px">
        <span style="font-size:11px;color:#5c6675">地址也可以填目录，会自动找 manifest.json</span>
      </div>

      <div style="font-size:12px;color:#8fa6c4;margin-bottom:5px">② 或者填服务器 SSH（走 SFTP）</div>
      <div class="row" style="align-items:center;margin-bottom:6px">
        <input id="cc_host" placeholder="服务器 IP / 域名" style="margin:0">
      </div>
      <div class="row" style="align-items:center;margin-bottom:6px">
        <span style="font-size:11.5px;color:#5c6675;width:44px">端口</span>
        <input id="cc_port" type="number" value="22" style="width:76px;margin:0">
        <span style="font-size:11.5px;color:#5c6675;margin-left:8px">用户</span>
        <input id="cc_user" value="root" style="width:100px;margin:0">
        <span style="font-size:11.5px;color:#5c6675;margin-left:8px">密码</span>
        <input id="cc_pass" type="password" placeholder="SSH 密码" style="width:120px;margin:0">
      </div>
      <div class="row" style="align-items:center;margin-bottom:6px">
        <span style="font-size:11.5px;color:#5c6675;width:44px">目录</span>
        <input id="cc_dir" value="/opt/bd2/capture" style="margin:0">
      </div>

      <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:14px">
        <button onclick="closeCloudCfg()" style="width:auto;padding:6px 16px;margin:0">取消</button>
        <button class="primary" onclick="saveCloudCfg()"
                style="width:auto;padding:6px 16px;margin:0">保存并同步</button>
      </div>
    </div>
  </div>
</div>

<div class="modal-bg" id="pmodal" style="z-index:130" onclick="if(event.target===this)closePicker()">
  <div class="modal" style="max-width:620px">
    <div class="mhead"><span class="mtitle" id="ptitle">选择服饰</span>
      <span class="mclose" onclick="closePicker()">✕</span></div>
    <div class="mbody">
      <input id="psearch" placeholder="搜索角色或服饰…" oninput="renderPickerList()">
      <div id="plist" style="max-height:60vh;overflow:auto"></div>
      <div id="pdel" style="margin-top:10px;text-align:right;display:none">
        <button onclick="delHere()" style="width:auto;padding:5px 14px;margin:0;
          border-color:#7f1d1d;color:#ff9b9b">删除这个单位</button>
      </div>
    </div>
  </div>
</div>


<div class="modal-bg" id="dmodal" style="z-index:200" onclick="if(event.target===this)_dlgCancel()">
  <div class="modal" style="max-width:400px">
    <div class="mhead"><span class="mtitle" id="dtitle">提示</span>
      <span class="mclose" onclick="_dlgCancel()">✕</span></div>
    <div class="mbody">
      <div id="dmsg" style="font-size:13px;color:#c3cddb;line-height:1.65;white-space:pre-wrap"></div>
      <input id="dinput" style="margin-top:10px;display:none">
      <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:16px">
        <button id="dcancel" onclick="_dlgCancel()"
          style="width:auto;padding:6px 18px;margin:0">取消</button>
        <button id="dok" class="primary" onclick="_dlgOk()"
          style="width:auto;padding:6px 18px;margin:0">确定</button>
      </div>
    </div>
  </div>
</div>

<div class="modal-bg" id="lmodal" style="z-index:155" onclick="if(event.target===this)closeLibPick()">
  <div class="modal" style="max-width:600px">
    <div class="mhead"><span class="mtitle">选择阵容库玩家</span>
      <span class="mclose" onclick="closeLibPick()">✕</span></div>
    <div class="mbody">
      <div class="row" style="align-items:center;margin-bottom:8px">
        <input id="lq2" placeholder="搜索名字…" oninput="libPickSearch()" style="margin:0">
      </div>
      <div class="row" style="align-items:center;margin-bottom:8px">
        <span style="font-size:12px;color:#a8b3c4;white-space:nowrap">分数</span>
        <input id="llo2" type="number" placeholder="最低" style="width:96px;margin:0"
               oninput="libPickSearch()">
        <span style="font-size:12px;color:#a8b3c4">~</span>
        <input id="lhi2" type="number" placeholder="最高" style="width:96px;margin:0"
               oninput="libPickSearch()">
      </div>
      <div id="linfo2" style="font-size:11.5px;color:#6d7888;margin-bottom:4px"></div>
      <div id="llist2" style="max-height:46vh;overflow:auto"></div>
    </div>
  </div>
</div>

<div class="modal-bg" id="bmodal" style="z-index:150" onclick="if(event.target===this)closeBattle()">
  <div class="modal" style="max-width:620px">
    <div class="mhead"><span class="mtitle" id="btitle">对战详情</span>
      <span class="mclose" onclick="closeBattle()">✕</span></div>
    <div class="mbody" id="bbody"></div>
  </div>
</div>

<div class="modal-bg" id="imodal" style="z-index:145" onclick="if(event.target===this)closeImport()">
  <div class="modal" style="max-width:460px">
    <div class="mhead"><span class="mtitle">导入收藏的阵容</span>
      <span class="mclose" onclick="closeImport()">✕</span></div>
    <div class="mbody"><div id="ilist" style="max-height:60vh;overflow:auto"></div></div>
  </div>
</div>

<div class="modal-bg" id="cmodal" style="z-index:135" onclick="if(event.target===this)closeCostume()">
  <div class="modal" style="max-width:560px">
    <div class="mhead"><span class="mtitle" id="ctitle">服饰详情</span>
      <span class="mclose" onclick="closeCostume()">✕</span></div>
    <div class="mbody" id="cbody"></div>
  </div>
</div>

<div class="modal-bg" id="smodal" style="z-index:140" onclick="if(event.target===this)closeStatSet()">
  <div class="modal" style="max-width:430px">
    <div class="mhead"><span class="mtitle" id="stitle">破度 / 爆发</span>
      <span class="mclose" onclick="closeStatSet()">✕</span></div>
    <div class="mbody">
      <div style="display:flex;gap:8px;align-items:center;margin-bottom:8px">
        <span style="font-size:12px;color:#a8b3c4">批量设置</span>
        <select id="s_brk" style="margin:0;width:110px">
          <option value="5">破 5（满破）</option><option value="4">破 4</option>
          <option value="3">破 3</option><option value="2">破 2</option>
          <option value="1">破 1</option><option value="0">破 0</option>
        </select>
        <select id="s_burst" style="margin:0;width:120px">
          <option value="3">爆 3（满爆）</option><option value="2">爆 2</option>
          <option value="1">爆 1</option><option value="0">不爆</option>
        </select>
        <button class="qbtn" style="margin:0" onclick="applyStatAll()">应用到全部</button>
      </div>
      <div id="s_list" style="max-height:46vh;overflow:auto"></div>
    </div>
  </div>
</div>

<div class="modal-bg" id="modal" onclick="if(event.target===this)closeModal()">
  <div class="modal">
    <div class="mhead"><span class="mtitle" id="mtitle"></span>
      <span class="mclose" onclick="closeModal()">✕</span></div>
    <div class="mbody" id="mbody"></div>
  </div>
</div>

<script>
const $=id=>document.getElementById(id), val=id=>$(id).value;
const ACOL={'火':'#ff6b4a','水':'#4aa8ff','风':'#4ad991','風':'#4ad991','光':'#ffd84a','暗':'#b06bff'};
const CCOL={50:'#ff4d6d',45:'#ff9f43',40:'#ffd166',35:'#06d6a0',30:'#4dabf7'};
let CURTEAM=null;
function closeModal(){ $('modal').classList.remove('on'); }
function showModal(title){ $('mtitle').textContent=title; $('modal').classList.add('on'); }
function renderTeam(j, opts){
  opts=opts||{};
  const cols=5, rows=5, us=j.units||[];
  const grid=Array.from({length:rows},()=>Array(cols).fill(null));
  us.forEach(u=>{ const r=Math.floor(u.pos/cols), c=u.pos%cols;
    if(r<rows && c<cols && grid[r][c]===null) grid[r][c]=u; });
  const cc=o=>CCOL[o.cost]||'#888';
  let h='';
  if(opts.stats) h+='<div class="swrap">'+opts.stats+'</div>';
  h+='<div class="boardbox"><div class="glab"><span></span>';
  for(let c=0;c<cols;c++) h+='<span>'+(c+1)+'列</span>';
  h+='</div>';
  for(let r=0;r<rows;r++){
    h+='<div class="brow"><div class="rlab">'+(r+1)+'</div>';
    for(let c=0;c<cols;c++){
      const u=grid[r][c];
      h+= u ? '<div class="slot on" style="--c:'+cc(u)+'"><span class="od">#'+u.order+'</span>'
              +'<div class="nm">'+u.char+'</div>'
              +'<div class="cs">'+u.costume+'</div>'
              +'<div class="cf"><span style="color:'+cc(u)+'">'+u.cost+'费</span> 破'+(u.brk||0)
              +(u.burst?(' 爆'+u.burst):'')+'</div></div>'
            : '<div class="slot"></div>';
    }
    h+='</div>';
  }
  h+='</div>';
  h+='<div class="ulist">';
  us.forEach(u=>{
    h+='<div class="urow" style="--c:'+cc(u)+'">'
      +'<div class="uord">#'+u.order+'</div>'
      +'<div class="uname2"><b>'+u.char+'</b><span>'+u.costume+'</span></div>'
      +'<div class="upos">'+(Math.floor(u.pos/cols)+1)+'行'+((u.pos%cols)+1)+'列</div>'
      +'<div class="umeta2"><span style="color:'+(ACOL[u.attr]||'#889')+'">'+(u.attr||'')+'</span> '
      +'<span style="color:'+cc(u)+'">'+u.cost+'</span> 破'+(u.brk||0)
      +(u.burst?(' <span style="color:#b06bff">爆'+u.burst+'</span>'):'')+'</div></div>';
  });
  h+='</div>';
  h+='<div class="hr"></div>';
  h+='<div class="blrow"><div class="k">先攻</div><div class="v">'+((j.bf||[]).join(' ＋ ')||'—')+'</div></div>';
  h+='<div class="blrow"><div class="k">后攻</div><div class="v">'+((j.bs||[]).join(' ＋ ')||'—')+'</div></div>';
  if(opts.canDelete) h+='<button class="mbtn danger" onclick="delThis()">删除这套阵容</button>';
  else if(opts.canSave!==false) h+='<button class="mbtn" onclick="saveThis()">＋ 保存这套阵容</button>';
  $('mbody').innerHTML=h;
  CURTEAM={id:opts.id||'', team:us.map(u=>[u.char,u.costume,u.pos,u.brk||0,u.burst||0]),
           bf:j.bf||[], bs:j.bs||[], seg:opts.seg||'', seg_lo:opts.seg_lo, seg_hi:opts.seg_hi};
}

async function delThis(){
  if(!CURTEAM||!CURTEAM.id) return;
  if(!(await uiConfirm('删除这套保存的阵容？'))) return;
  await fetch('/api/saved/del',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({id:CURTEAM.id})});
  closeModal(); loadSaved();
}
async function saveThis(){
  if(!CURTEAM) return;
  const nm=await uiPrompt('给这套阵容起个名字：', CURTEAM.seg||'');
  if(nm===null) return;
  const j=await (await fetch('/api/save',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:nm, team:CURTEAM.team, bf:CURTEAM.bf, bs:CURTEAM.bs,
                         seg:CURTEAM.seg, seg_lo:CURTEAM.seg_lo, seg_hi:CURTEAM.seg_hi})})).json();
  alert(j.msg); if(j.ok) closeModal();
}const TABKEY='bd2_tab';
function activateTab(name){
  const has=[...document.querySelectorAll('.tab')].some(x=>x.dataset.t===name);
  if(!has) name='team';
  document.querySelectorAll('.tab').forEach(x=>{
    if(x.dataset.t===name) x.classList.add('on'); else x.classList.remove('on');});
  document.querySelectorAll('.pane').forEach(x=>{
    if(x.id==='p-'+name) x.classList.add('on'); else x.classList.remove('on');});
  try{ localStorage.setItem(TABKEY,name); }catch(e){}
  if(name==='rules') loadRules();
  if(name==='bless') loadBless();
  if(name==='cost') loadCost();
  if(name==='lib') loadLib();
  if(name==='saved') loadSaved();
  if(name==='test') initTest();
  if(name==='team'){ loadSys(); loadCur(); }
}
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>activateTab(t.dataset.t));
let lastLen=-1;
async function runSearch(){
  const lo = val('lo'), hi = val('hi');
  try{
    const j = await (await fetch('/api/poolstat?lo=' + (lo || 0) + '&hi=' + (hi || 99999))).json();
    if(j.ok && j.inrange === 0){
      alert('该分段没有对手阵容\n\n' + lo + ' ~ ' + hi + ' 分：0 套\n'
        + '对手池分数范围：' + (j.min || '?') + ' ~ ' + (j.max || '?') + '（共 ' + j.total + ' 套）');
      return;
    }
  }catch(e){}
  run('search', {lo: lo, hi: hi, n: val('sn'), workers: +val('sw') || 0,
                 quick: $('sq').checked ? 1 : 0});
}
async function stopJob(){
  if(!(await uiConfirm('确定停止当前任务吗？\n（正在跑的搜索会被中断，已算出的结果不会保存）'))) return;
  const j = await (await fetch('/api/stop',{method:'POST',headers:{'Content-Type':'application/json'},
    body:'{}'})).json();
  alert(j.msg || (j.ok?'已停止':'没有任务'));
  lastLen = -1; poll();
}
async function run(task,args){
  const r=await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({task,args})});
  const j=await r.json(); if(!j.ok) alert(j.msg); else {lastLen=-1; poll();}
}
async function poll(){
  const j=await (await fetch('/api/log?since='+lastLen)).json();
  // ★ 停止按钮：空闲变灰、有任务时脉冲
  try{
    const bs=document.getElementById('btn_stop');
    if(bs){
      bs.classList.toggle('idle', !j.running);
      bs.classList.toggle('running', !!j.running);
    }
  }catch(e){}
  if(j.lines.length){lastLen=j.total;const el=$('log');
    const ab=el.scrollTop+el.clientHeight>=el.scrollHeight-30;
    el.textContent=j.lines.join('\n'); if(ab) el.scrollTop=el.scrollHeight;}
  if(window.__wasRunning && !j.running){ loadCur(); loadSys(); }
  window.__wasRunning = j.running;
  $('jobst').textContent=j.running?('运行中：'+j.name):'空闲';
  $('jobst').style.background=j.running?'#4d2c04':'#1b2230';
  $('jobst').style.color=j.running?'#ffb545':'#8b97a8';
  setTimeout(poll, j.running?900:2500);
}
async function stat(){
  const j=await (await fetch('/api/status')).json();
  let h='';
  if(j.saved!==undefined)
    h+='<div class="kv"><span>收藏阵容</span><b>'+j.saved+' 套</b></div>';
  if(j.lib)
    h+='<div class="kv"><span>阵容库</span><b>'+j.lib.min+' ~ '+j.lib.max+' 分</b></div>'
      +'<div class="kv"><span>&nbsp;&nbsp;人数</span><b>'+j.lib.n+' 人</b></div>';
  $('stat').innerHTML=h; setTimeout(stat,10000);
}
let RULES=null;
async function loadRules(){
  RULES=await (await fetch('/api/rules')).json();
  $('r_season').value=RULES.season; $('r_name').value=RULES.season_name;
  $('r_rows').value=RULES.rows; $('r_cols').value=RULES.cols;
  $('r_units').value=RULES.max_units; $('r_cost').value=RULES.max_cost;
  $('r_bf').value=RULES.bless_first; $('r_bs').value=RULES.bless_second;
  drawGrid(); showRules();
}
function drawGrid(){
  const rows=+$('r_rows').value||5, cols=+$('r_cols').value||5;
  const forb=new Set(RULES.forbidden||[]);
  let h='<div style="display:inline-grid;grid-template-columns:repeat('+cols+',44px);gap:5px">';
  for(let r=0;r<rows;r++)for(let c=0;c<cols;c++){
    const p=r*cols+c, off=forb.has(p);
    h+='<div data-p="'+p+'" style="height:40px;border-radius:7px;display:flex;align-items:center;justify-content:center;font-size:11px;border:1px solid '
      +(off?'#7a2b2b':'#2d3748')+';background:'+(off?'#2a1414':'#12161e')+';color:'+(off?'#ff8080':'#6d7888')+'">'+(off?'X':p)+'</div>';
  }
  h+='</div>'; $('r_grid').innerHTML=h;

  showGrid();
}
function showRules(){
  const r=RULES;
  $('ruleshow').innerHTML=
   '<div class="kv"><span>赛季</span><b>'+r.season_name+'</b></div>'+
   '<div class="kv"><span>阵形</span><b>'+r.rows+'x'+r.cols+'</b></div>'+
   '<div class="kv"><span>人数上限</span><b>'+r.max_units+' 人</b></div>'+
   '<div class="kv"><span>费用上限</span><b>'+r.max_cost+'</b></div>'+
   '<div class="kv"><span>先攻庇佑</span><b>'+r.bless_first+' 点</b></div>'+
   '<div class="kv"><span>后攻庇佑</span><b>'+r.bless_second+' 点</b></div>'+
   '<div class="kv"><span>禁用格</span><b>'+(r.forbidden||[]).join(', ')+'</b></div>'+
   '<div class="kv"><span>可用格数</span><b>'+(r.rows*r.cols-(r.forbidden||[]).length)+'</b></div>';
}
function showGrid(){
  const rows=+$('r_rows').value||5, cols=+$('r_cols').value||5;
  const forb=new Set(RULES.forbidden||[]);
  let h='<table style="width:auto;font-size:12px"><tr><th></th>';
  for(let c=0;c<cols;c++)h+='<th>'+(c+1)+'列</th>';
  h+='</tr>';
  for(let rr=0;rr<rows;rr++){
    h+='<tr><th>'+(rr+1)+'行</th>';
    for(let c=0;c<cols;c++){const p=rr*cols+c;
      h+='<td style="text-align:center;color:'+(forb.has(p)?'#ff8080':'#4dabf7')+'">'
        +(forb.has(p)?'禁':'可用')+'<br><span style="font-size:10px;color:#6d7888">'+p+'</span></td>';}
    h+='</tr>';
  }
  $('gridshow').innerHTML=h+'</table>';
}
async function loadBless(){
  const j=await (await fetch('/api/bless?q='+encodeURIComponent(val('bq')||''))).json();
  $('btb').innerHTML=j.list.map(x=>'<tr><td>'+x.name+'</td>'+
    '<td style="color:#ffd166">'+x.cost+'</td>'+
    '<td><span class="tag">'+(x.cat||'')+'</span></td>'+
    '<td>'+(x.desc||'')+'</td></tr>').join('')
    || '<tr><td colspan="4" style="color:#6d7888">没有匹配</td></tr>';
}
async function loadCost(){
  const j=await (await fetch('/api/cost?q='+encodeURIComponent(val('cq')||''))).json();
  $('ctb').innerHTML=j.list.map(x=>'<tr style="cursor:pointer" onclick="openCostume(\''
    +x.raw+'\')"><td class="link">'+x.ch+'·'+x.co+'</td>'+
    '<td style="color:#ffd166;font-weight:600">'+x.cost+'</td></tr>').join('')
    || '<tr><td colspan="2" style="color:#6d7888">没有匹配</td></tr>';
}
/* ---------- 阵容库 ---------- */
function setSeg(lo,hi){
  document.getElementById('llo').value=lo;
  document.getElementById('lhi').value=hi;
  loadLib();
}
async function loadLib(){
  const u='/api/lib?limit=200'
    +'&q='+encodeURIComponent(val('lq')||'')
    +'&lo='+encodeURIComponent(val('llo')||'')
    +'&hi='+encodeURIComponent(val('lhi')||'');
  const j=await (await fetch(u)).json();
  const seg = (val('llo')||val('lhi')) ? ('分數 '+(val('llo')||'0')+' ~ '+(val('lhi')||'∞')) : '全部分数';
  $('linfo').textContent='仅显示 '+(j.season||'当前赛季')+' ｜ '+seg+' ｜ 匹配 '+j.total+' 人（最多 200 条，按分数排序）';
  $('ltb').innerHTML=j.list.map(x=>
    '<tr style="cursor:pointer" onclick="openLib(\''+x.uid+'\')">'+
    '<td style="color:#ffd166;font-weight:600">'+x.score+'</td>'+
    '<td><a class="link" href="javascript:void(0)" onclick="openLib(\''+x.uid+'\')">'+x.name+'</a></td>'+
    '<td style="color:#6d7888">'+x.uid+'</td>'+
    '<td style="color:#a8b3c4">'+(x.season||'')+'</td>'+
    '<td style="font-size:11.5px;color:#a8b3c4">'+x.summary+'</td></tr>').join('')
    || '<tr><td colspan="5" style="color:#6d7888">没有匹配</td></tr>';
}
async function openLib(uid){
  const j=await (await fetch('/api/lib/one?uid='+uid)).json();
  if(!j.ok){ alert(j.msg); return; }
  const u=j.units||[];
  const cost=u.reduce((a,b)=>a+(b.cost||0),0);
  const st=(k,v,c)=>'<div class="schip">'+k+'<b'+(c?' style="color:'+c+'"':'')+'>'+v+'</b></div>';
  const stats = st('分数',j.score+' 分','#ffd166')
    + st('总费用',cost+' / 240')
    + st('赛季',j.season||'-')

    + st('UID',j.uid||'-')
    + st('抓取时间',(j.at||'').slice(5));
  showModal(j.name||'阵容');
  renderTeam(j, {stats:stats, seg:((j.name||'')+' '+(j.score||'')+'分')});
}

async function openSaved(id){
  const j=await (await fetch('/api/saved/one?id='+id)).json();
  if(!j.ok){ alert(j.msg); return; }
  const st=(k,v,c)=>'<div class="schip">'+k+'<b'+(c?' style="color:'+c+'"':'')+'>'+v+'</b></div>';
  const stats = st('总费用',(j.cost||'')+' / 240')
    + st('人数',(j.units||[]).length+' 人')
    + st('保存于',(j.at||'').slice(5));
  showModal(j.name||'保存的阵容');
  renderTeam(j, {stats:stats, seg:j.seg, seg_lo:j.seg_lo, seg_hi:j.seg_hi,
                 canSave:false, canDelete:true, id:id});
}

async function saveCur(){
  const nm=await uiPrompt('给这套阵容起个名字：','');
  if(nm===null) return;
  const j=await (await fetch('/api/save',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:nm})})).json();
  alert(j.msg); if(j.ok) loadSaved();
}
async function loadSaved(){
  const j=await (await fetch('/api/saved')).json();
  $('stb').innerHTML=j.list.map(x=>
    '<tr style="cursor:pointer" onclick="openSaved(\''+x.id+'\')">'+
    '<td><a class="link" href="javascript:void(0)">'+x.name+'</a></td>'+
    '<td style="color:#a8b3c4">'+(x.season||'')+'</td>'+
    '<td style="color:#ffd166;font-weight:600">'+(x.cost||'')+'</td>'+
    '<td style="color:#6d7888">'+(x.at||'')+'</td>'+
    '<td><span style="color:#ff8080" onclick="event.stopPropagation();delSaved(\''+x.id+'\')">删除</span></td></tr>').join('')
    || '<tr><td colspan="5" style="color:#6d7888">还没有保存过阵容</td></tr>';
}
async function delSaved(id){
  if(!(await uiConfirm('删除这套保存的阵容？'))) return;
  await fetch('/api/saved/del',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({id:id})});
  loadSaved();
}


/* ---------- 测试阵容（内嵌编辑器） ---------- */
let BOX=[], BLESS=[];
const POSALL=[0,1,2,3,5,7,8,9,10,11,12,13,14,15,16,17,19,21,22,23,24];
const FORB=[4,6,18,20];
const ED={which:'our',
  our:{team:[],bf:[],bs:[]},
  opp:{team:[],bf:[],bs:[]},
  placePos:null};
const EMIT={brk:5, burst:3};      // 默认满破满爆
const TGT={
  our:{board:'t_our_board', sum:'t_our_sum', bf:'t_our_bf', bs:'t_our_bs',
       bfpt:'t_our_bfpt', bspt:'t_our_bspt'},
  opp:{board:'t_opp_board', sum:'t_opp_sum', bf:'t_opp_bf', bs:'t_opp_bs',
       bfpt:'t_opp_bfpt', bspt:'t_opp_bspt'}
};
let _LOADING=null;
async function ensureData(){
  if(BOX.length && BLESS.length) return;
  if(_LOADING) return _LOADING;
  _LOADING=(async()=>{
    try{
      BOX=(await (await fetch('/api/box')).json()).list||[];
      BLESS=(await (await fetch('/api/bless?q=')).json()).list||[];
    }catch(e){ BOX=[]; BLESS=[]; }
  })();
  try{ await _LOADING; } finally { _LOADING=null; }
}
async function initTest(){
  await ensureData();
  render('our'); render('opp');
  testMode();
}
function unitInfo(u){
  // 优先用条目自带的字段（导入的收藏里可能是不在自己收藏中的服饰）
  const b = BOX.find(x => x.raw === u.raw) || {};
  return {ch: u.ch || b.ch || '?', co: u.co || b.co || '',
          cost: (u.cost !== undefined && u.cost !== null) ? u.cost : (b.cost || 0),
          attr: u.attr || b.attr || '', brk: (u.brk !== undefined ? u.brk : (b.brk || 5)),
          burst: (u.burst !== undefined ? u.burst : (b.burst || 0)),
          has_burst: (u.has_burst !== undefined ? u.has_burst : !!b.has_burst),
          owned: !!b.raw};
}
function costOf(raw){ const b=BOX.find(x=>x.raw===raw); return b?b.cost:0; }
function teamCost(which){
  return ED[which].team.reduce((a,u)=>a+((u.cost !== undefined && u.cost !== null) ? u.cost : costOf(u.raw)), 0);
}
function render(which){
  const t=TGT[which]; if(!t) return;
  renderBoard(which);
  renderBless(which,'bf'); renderBless(which,'bs');
  const st=ED[which], el=document.getElementById(t.sum);
  if(el){
    if(!st.team.length) el.innerHTML='还没选';
    else el.innerHTML='<b>'+st.team.length+' 人</b>　费用 <b style="color:'
      +(teamCost(which)>240?'#ff8080':'#ffd166')+'">'+teamCost(which)+' / 240</b>'
      +'　<span style="color:#4dabf7">先攻 '+st.bf.length+'</span>'
      +'　<span style="color:#06d6a0">后攻 '+st.bs.length+'</span>';
  }
}
function renderBoard(which){
  const t=TGT[which], st=ED[which];
  const map={}; st.team.forEach(u=>map[u.pos]=u);
  const COLS='20px repeat(5,78px)';
  let h='<div class="boardbox" style="padding:8px;display:inline-block">';
  h+='<div class="glab" style="grid-template-columns:'+COLS+'"><span></span>';
  for(let c=0;c<5;c++) h+='<span>'+(c+1)+'列</span>';
  h+='</div>';
  for(let r=0;r<5;r++){
    h+='<div class="brow" style="grid-template-columns:'+COLS+'"><div class="rlab">'+(r+1)+'</div>';
    for(let c=0;c<5;c++){
      const p=r*5+c, u=map[p];
      if(FORB.includes(p)){
        h+='<div class="slot" style="opacity:.28;height:60px"></div>'; continue;
      }
      if(u){
        const info=unitInfo(u);
        const cc=CCOL[info.cost]||'#888';
        h+='<div class="slot on" style="--c:'+cc+';cursor:pointer;height:60px'
          +(info.owned?'':';border-color:#8a6a3a')+'" title="'+(info.owned?'':'不在你的收藏里　')
          +info.ch+'·'+info.co+'" onclick="openPicker(\''+which+'\','+p+')">'
          +'<span class="od">#'+u.order+'</span>'
          +'<div class="nm">'+info.ch+'</div>'
          +'<div class="cs">'+info.co+'</div>'
          +'<div class="cf"><span style="color:'+cc+'">'+info.cost+'费</span>'
          +'<span style="color:#7b8798;font-size:10px"> 破'+info.brk
          +(info.burst?' 爆'+info.burst:'')+'</span></div></div>';
      }else{
        h+='<div class="slot" onclick="openPicker(\''+which+'\','+p+')" style="cursor:pointer;height:60px;'
          +'display:flex;align-items:center;justify-content:center;font-size:15px;color:#3a4761">＋</div>';
      }
    }
    h+='</div>';
  }
  h+='</div>';
  const tot=teamCost(which);
  h+='<div style="font-size:11.5px;color:'+(tot>240?'#ff8080':'#6d7888')+';margin-top:5px">'
    +'已选 '+st.team.length+' 人　'+tot+' / 240 费　'
    +'<span style="color:#5c6675">点「＋」放人 · 点人＝换服饰/删除</span></div>';
  document.getElementById(t.board).innerHTML=h;
}
function renderBless(which,p){
  const t=TGT[which], st=ED[which], on=st[p]||[];
  const host=document.getElementById(t[p]);
  if(!host) return;
  host.innerHTML=BLESS.map(b=>{
    const sel=on.includes(b.name);
    return '<span class="bchip2'+(sel?' on':'')+'" onclick="toggleB(\''+which+'\',\''+p
      +'\',\''+b.name+'\','+(b.cost||1)+')">'+b.name+' '+(b.cost||1)+'</span>';
  }).join('');
  let used=0; on.forEach(n=>{const b=BLESS.find(x=>x.name===n); used+=(b?b.cost:1);});
  const pt=document.getElementById(t[p+'pt']);
  if(pt) pt.textContent=used+' / '+budgetOf(p)+' 点';
}
function budgetOf(p){ return (p==='bf')?6:8; }
function toggleB(which,p,name,cost){
  const st=ED[which]; st[p]=st[p]||[];
  const i=st[p].indexOf(name);
  if(i>=0){ st[p].splice(i,1); }
  else{
    let used=0; st[p].forEach(n=>{const b=BLESS.find(x=>x.name===n); used+=(b?b.cost:1);});
    if(used+cost>budgetOf(p)){ alert('超过 '+budgetOf(p)+' 点上限'); return; }
    st[p].push(name);
  }
  renderBless(which,p);
  render(which);
}
function delUnit(which,pos){
  const st=ED[which];
  st.team=st.team.filter(u=>u.pos!==pos);
  st.team.sort((a,b)=>a.pos-b.pos).forEach((u,i)=>u.order=i+1);
  render(which);
}
/* 选服饰弹框 */
function openPicker(which,pos){
  ED.which=which; ED.placePos=pos;
  const st=ED[which];
  if(st.team.length>=7 && !st.team.some(u=>u.pos===pos)){ alert('最多 7 人'); return; }
  const _had = st.team.some(u=>u.pos===pos);
  ED.hadUnit = _had;
  document.getElementById('ptitle').textContent =
    (_had ? '更换服饰' : '选择服饰') + ' · ' + (Math.floor(pos/5)+1) + '行' + (pos%5+1) + '列';
  document.getElementById('pdel').style.display = _had ? '' : 'none';
  document.getElementById('psearch').value='';
  renderPickerList();
  document.getElementById('pmodal').classList.add('on');
}
function closePicker(){ document.getElementById('pmodal').classList.remove('on'); }
function delHere(){
  const which = ED.which, pos = ED.placePos;
  closePicker();
  if(pos !== null && pos !== undefined) delUnit(which, pos);
}
function renderPickerList(){
  const q=(document.getElementById('psearch').value||'').trim();
  const which=ED.which, st=ED[which];
  const used=new Set(st.team.map(u=>u.raw));
  const groups=[['火','#ff6b4a'],['水','#4aa8ff'],['风','#4ad991'],['光','#ffd84a'],['暗','#b06bff']];
  let h='';
  groups.forEach(([attr,col])=>{
    const list=BOX.filter(x=>x.attr===attr && (used.has(x.raw)||!q||(x.ch+x.co).indexOf(q)>=0));
    if(!list.length) return;
    h+='<div style="margin-bottom:10px"><div style="font-size:11.5px;color:'+col
      +';margin:0 0 5px;font-weight:600">'+attr+'属性　<span style="color:#5c6675">'+list.length+' 件</span></div>'
      +'<div style="display:flex;flex-wrap:wrap;gap:5px">';
    list.forEach(x=>{
      const dis=used.has(x.raw);
      const cc=CCOL[x.cost]||'#888';
      h+='<span class="pchip'+(dis?' used':'')+'"'+(dis?'':(' onclick="pickAt(\''+x.raw+'\')"'))
        +' style="border-color:'+cc+'">'+x.ch+'·'+x.co
        +'<i style="color:'+cc+'">'+x.cost+'</i>'
        +'<i style="color:#6d7888">破5'+(x.burst?' 爆3':'')+'</i></span>';
    });
    h+='</div></div>';
  });
  document.getElementById('plist').innerHTML=h
    ||('<div style="color:#6d7888;font-size:12px">'+(BOX.length?'没有匹配':'服饰数据还没加载')+'</div>');
}
function pickAt(raw){
  const which=ED.which, st=ED[which], pos=ED.placePos;
  if(st.team.some(u=>u.raw===raw)){ alert('这件已经上场了'); return; }
  const old=st.team.find(u=>u.pos===pos);
  const oldCost=old?costOf(old.raw):0, newCost=costOf(raw);
  const after=teamCost(which)-oldCost+newCost;
  if(after>240){ alert('费用超上限：'+teamCost(which)+' - '+oldCost+' + '+newCost+' = '+after+' > 240'); return; }
  st.team=st.team.filter(u=>u.pos!==pos);
  const bx=BOX.find(x=>x.raw===raw)||{};
  st.team.push({raw:raw, pos:pos, order:0, brk:EMIT.brk,
                burst:bx.burst?EMIT.burst:0,
                ch:bx.ch, co:bx.co, cost:bx.cost, attr:bx.attr, has_burst:bx.has_burst});
  st.team.sort((a,b)=>a.pos-b.pos).forEach((u,i)=>u.order=i+1);
  closePicker();
  render(which);
}
let _PN = 0;
async function showPoolN(){
  const el = document.getElementById('t_pooln');
  if(!el) return;
  const lo = document.getElementById('t_lo').value || 0;
  const hi = document.getElementById('t_hi').value || 99999;
  const sm = parseInt(document.getElementById('t_sample').value) || 0;
  try{
    const j = await (await fetch('/api/poolstat?lo=' + lo + '&hi=' + hi)).json();
    if(!j.ok) return;
    _PN = j.inrange;
    const use = sm > 0 ? Math.min(sm, j.inrange) : j.inrange;
    el.innerHTML = '该分数区间共 <b style="color:#ffd166">' + j.inrange + '</b> 套对手'
      + (sm > 0 ? ('，本次随机抽 <b style="color:#8fb6dd">' + use + '</b> 套') : '，本次<b style="color:#8fd9b6">全部测试</b>')
      + '　（池子共 ' + j.total + ' 套）';
  }catch(e){ el.textContent = ''; }
}
function testMode(){
  const m=(document.getElementById('t_mode').value)||'range';
  document.getElementById('t_opp_range').style.display=(m==='range')?'':'none';
  document.getElementById('t_opp_lib').style.display=(m==='lib')?'':'none';
  document.getElementById('t_opp_manual').style.display=(m==='manual')?'':'none';
  if(m==='lib' && !LIBPICK) document.getElementById('t_libinfo').textContent='未选择';
  if(m==='manual') render('opp');
}
function fmtTeam(which){
  return ED[which].team.map(u=>{
    const raw = u.raw || ((u.ch || '') + '·' + (u.co || ''));
    const s = raw.split('·');
    // ★ 没设置过就默认满破；有爆发的服饰默认爆3（用户 2026-11-07 要求）
    const _hb = (u.has_burst !== undefined) ? u.has_burst : !!u.burst;
    return [s[0], s.slice(1).join('·'), u.pos,
            u.brk !== undefined ? u.brk : 5,
            u.burst !== undefined ? u.burst : (_hb ? 3 : 0)];
  });
}
function openStatSet(which){
  ED.statWhich=which;
  document.getElementById('stitle').textContent=
    (which==='our'?'我方':'对手')+' 破度 / 爆发';
  document.getElementById('s_brk').value=EMIT.brk;
  document.getElementById('s_burst').value=EMIT.burst;
  renderStatList();
  document.getElementById('smodal').classList.add('on');
}
function closeStatSet(){ document.getElementById('smodal').classList.remove('on'); }
function renderStatList(){
  const which=ED.statWhich||'our', st=ED[which];
  const host=document.getElementById('s_list');
  if(!st.team.length){ host.innerHTML='<div style="color:#6d7888;font-size:12px">还没有选中任何服饰</div>'; return; }
  host.innerHTML=st.team.map((u,i)=>{
    const info=unitInfo(u);
    const cc=CCOL[info.cost]||'#888';
    const hasB = info.has_burst || info.burst > 0;
    return '<div class="erow" style="margin-bottom:6px">'
      +'<div class="idx">#'+u.order+'</div>'
      +'<div style="flex:1;font-size:12px;color:#c3cddb;overflow:hidden;white-space:nowrap">'
      +info.ch+'·'+info.co+'<span style="color:'+cc+'"> '+info.cost+'费</span></div>'
      +'<select style="width:88px;margin:0" onchange="setUnitStat('+i+',\'brk\',this.value)">'
      +[0,1,2,3,4,5].map(v=>'<option value="'+v+'"'+(u.brk===v?' selected':'')+'>破 '+v+'</option>').join('')
      +'</select>'
      +(hasB
        ? ('<select style="width:88px;margin:0" onchange="setUnitStat('+i+',\'burst\',this.value)">'
           +[0,1,2,3].map(v=>'<option value="'+v+'"'+(u.burst===v?' selected':'')+'>'
              +(v?'爆 '+v:'不爆')+'</option>').join('')
           +'</select>')
        : '<span style="width:88px;text-align:center;font-size:11px;color:#4a5666">无爆发</span>')
      +'</div>';
  }).join('');
}
function setUnitStat(i,key,val){
  const which=ED.statWhich||'our', st=ED[which];
  if(!st.team[i]) return;
  st.team[i][key]=parseInt(val);
  render(which);
}
function applyStatAll(){
  const which=ED.statWhich||'our', st=ED[which];
  EMIT.brk=parseInt(document.getElementById('s_brk').value);
  EMIT.burst=parseInt(document.getElementById('s_burst').value);
  st.team.forEach(u=>{
    u.brk=EMIT.brk;
    const hb=!!(BOX.find(x=>x.raw===u.raw)||{}).burst;
    u.burst=hb?EMIT.burst:0;
  });
  renderStatList(); render(which);
}
async function runTest(){
  if(!ED.our.team.length){ alert('请先在左边选择我方阵容'); return; }
  const mode=(document.getElementById('t_mode').value)||'range';
  const opp={mode:mode};
  if(mode==='range'){
    opp.lo=+document.getElementById('t_lo').value;
    opp.hi=+document.getElementById('t_hi').value;
    opp.sample=+document.getElementById('t_sample').value;
  }else if(mode==='lib'){
    if(!LIBPICK){ alert('请先点「选择阵容库玩家」选一个人'); return; }
    opp.uid = LIBPICK.uid;
  }else{
    if(!ED.opp.team.length){ alert('请先选对手阵容'); return; }
    opp.team=fmtTeam('opp');
    opp.bf=ED.opp.bf||[]; opp.bs=ED.opp.bs||[];
  }
  const body={our:{team:fmtTeam('our'), bf:ED.our.bf||[], bs:ED.our.bs||[]}, opp:opp,
              n:(+document.getElementById('t_n').value||3)};
  const el=document.getElementById('t_result');
  el.innerHTML='<span style="color:#ffd166">测试中，请稍等…</span>';
  try{
    const j=await (await fetch('/api/test',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(body)})).json();
    if(!j.ok){ el.innerHTML='<span style="color:#ff8080">'+(j.msg||'失败')+'</span>'; return; }
    el.innerHTML='<div class="swrap">'
      +'<div class="schip">先攻<b style="color:#4dabf7">'+j.f.toFixed(1)+'%</b></div>'
      +'<div class="schip">后攻<b style="color:#06d6a0">'+j.b.toFixed(1)+'%</b></div>'
      +'<div class="schip">综合<b style="color:#ffd166">'+j.comb.toFixed(1)+'%</b></div>'
      +'</div><div style="font-size:11.5px;color:#6d7888;margin-top:6px">对手 '+j.sets
      +' 套 × 每套 '+j.n+' 场 = 共 '+j.games+' 场</div>';
    LASTTEST = {our:ED.our.team.map(u=>[u.raw,u.pos]), opp:body.opp};
    let _rows = (j.losers || []).slice();
    let _title = '打不过的对手（' + (j.n_losers || 0) + ' 套，按败场排序）';
    if(!_rows.length){ _rows = (j.rows || []).slice(); _title = '对战回放（点一行看日志）'; }
    if(_rows.length){
      el.innerHTML += '<p class="tt" style="margin-top:12px">' + _title + '</p>'
        + '<div style="max-height:230px;overflow:auto;background:#12161e;border:1px solid #232a38;'
        + 'border-radius:9px;padding:6px">'
        + _rows.map(x =>
            '<div class="erow" style="margin-bottom:4px;cursor:pointer" onclick="openBattle('+x.idx+')">'
            + '<div style="width:118px;font-size:11.5px;overflow:hidden;white-space:nowrap">'
            + '<b style="color:#ffd166">'+x.score+'分</b>'
            + '<span style="color:#8fb6dd"> '+(x.name||'')+'</span></div>'
            + '<div style="flex:1;font-size:11px;color:#a8b3c4;overflow:hidden;white-space:nowrap">'
            + x.lineup + '</div>'
            + '<div style="font-size:11px;color:#4dabf7;width:52px;text-align:right">先'
            + x.fw + '/' + x.ft + '</div>'
            + '<div style="font-size:11px;color:#06d6a0;width:52px;text-align:right">后'
            + x.bw + '/' + x.bt + '</div>'
            + '<div style="font-size:11px;color:#8fb6dd;width:46px;text-align:right">看对战</div>'
            + '</div>').join('')
        + '</div>';
    }
  }catch(e){ el.innerHTML='<span style="color:#ff8080">请求失败</span>'; }
}


/* ---------- 服饰详情（费用页点击） ---------- */
let CD = null;
function closeCostume(){ document.getElementById('cmodal').classList.remove('on'); }
async function openCostume(raw){
  CD = {raw: raw, brk: 5, bst: 3};
  document.getElementById('ctitle').textContent = raw;
  document.getElementById('cmodal').classList.add('on');
  await loadCostume();
}
async function loadCostume(){
  const u = '/api/cost/one?raw=' + encodeURIComponent(CD.raw) + '&brk=' + CD.brk + '&bst=' + CD.bst;
  const d = await (await fetch(u)).json();
  if(!d.ok){ document.getElementById('cbody').innerHTML =
    '<span style="color:#ff8080">' + (d.msg || '读取失败') + '</span>'; return; }
  CD.d = d; renderCostume();
}
function rangeHTML(shape){
  const set = new Set((shape || []).map(p => p[0] + ',' + p[1]));
  const xs = [0], ys = [0];
  (shape || []).forEach(p => { xs.push(p[0]); ys.push(p[1]); });
  const x0 = Math.max(-4, Math.min.apply(null, xs)), x1 = Math.min(4, Math.max.apply(null, xs));
  const y0 = Math.max(-4, Math.min.apply(null, ys)), y1 = Math.min(4, Math.max.apply(null, ys));
  const n = x1 - x0 + 1;
  let h = '<div style="display:inline-grid;grid-template-columns:repeat(' + n + ',20px);gap:2px">';
  for(let y = y0; y <= y1; y++){
    for(let x = x0; x <= x1; x++){
      const on = set.has(x + ',' + y), core = (x === 0 && y === 0);
      const bg = core ? '#1d4ed8' : (on ? '#2f5a86' : '#151a23');
      h += '<div style="width:20px;height:20px;border-radius:4px;background:' + bg
         + ';display:flex;align-items:center;justify-content:center;font-size:9px;color:'
         + (core ? '#fff' : '#8fb6dd') + '">' + (core ? '◎' : (on ? '●' : '')) + '</div>';
    }
  }
  return h + '</div>';
}
function renderCostume(){
  const d = CD.d;
  const burstOpts = d.has_burst
    ? [0,1,2,3].map(v => '<option value="' + v + '"' + (d.bst === v ? ' selected' : '') +
        '>' + (v === 0 ? '爆 0（不点爆发）' : '爆 ' + v) + '</option>').join('')
    : '<option value="0" selected>无爆发</option>';
  const lvOpts = [0,1,2,3,4,5].map(v => '<option value="' + v + '"' +
      (d.brk === v ? ' selected' : '') + '>破 ' + v + (v === 5 ? '（满破）' : '') + '</option>').join('');
  let h = '<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px">'
    + '<span class="schip">费用<b style="color:#ffd166">' + d.cost + '</b></span>'
    + '<span class="schip">属性<b style="color:' + (ACOL[d.attr] || '#889') + '">' + (d.attr || '-') + '</b></span>'
    + '<span class="schip">类型<b>' + (d.type || '-') + '</b></span>'
    + '<span class="schip">段数<b style="color:#4dabf7">' + (d.hits || 0) + '</b></span>'
    + '<span class="schip">倍率<b style="color:#06d6a0">' + (d.per ? Math.round(d.per) : 0) + '%</b></span>'
    + '<span class="schip">目标<b>' + (d.target || '-') + '</b></span></div>'
    + '<div class="row" style="margin-bottom:10px">'
    + '<select id="c_brk" onchange="CD.brk=+this.value;loadCostume()" style="margin:0;width:132px">' + lvOpts + '</select>'
    + '<select id="c_bst" onchange="CD.bst=+this.value;loadCostume()" style="margin:0;width:158px"'
    + (d.has_burst ? '' : ' disabled') + '>' + burstOpts + '</select></div>'
    + '<div style="display:flex;gap:14px;align-items:flex-start;flex-wrap:wrap">'
    + '<div>' + rangeHTML(d.shape) + '</div>'
    + '<div style="flex:1;min-width:210px">'
    + '<div style="font-size:11.5px;color:#6d7888;margin-bottom:5px">技能范围　'
    + '<span style="color:#8fb6dd">' + (d.range_code || '-') + '</span>　覆盖 '
    + ((d.shape || []).length) + ' 格</div>';
  (d.skill || []).forEach(t => {
    h += '<div style="font-size:12px;color:#c3cddb;background:#161c26;border-radius:7px;'
      + 'padding:7px 9px;margin-bottom:5px;line-height:1.55">' + t + '</div>';
  });
  h += '</div></div>';
  if(d.has_burst){
    h += '<p class="tt" style="margin-top:12px">爆发各级</p>'
      + '<div style="font-size:11.5px;color:#a8b3c4;line-height:1.7">';
    (d.burst_text || []).forEach((t, i) => {
      const on = (i + 1) <= d.bst;
      h += '<div style="' + (on ? 'color:#8fd9b6' : 'color:#5c6675') + '">'
        + (on ? '✓ ' : '○ ') + 'Lv' + (i + 1) + '：' + t + '</div>';
    });
    h += '</div>';
  }
  if((d.potential_text || []).length){
    h += '<p class="tt" style="margin-top:10px">潜能</p>'
      + '<div style="font-size:11.5px;color:#8b97a8;line-height:1.7">';
    (d.potential_text || []).forEach(t => { h += '<div>· ' + t + '</div>'; });
    h += '</div>';
  }
  document.getElementById('cbody').innerHTML = h;
}


/* ---------- 机器状态 / 线程数 ---------- */
let SYS = null;
async function loadSys(){
  const el = document.getElementById('sysinfo');
  if(!el) return;
  try{
    const j = await (await fetch('/api/sysinfo')).json();
    if(!j.ok){ el.textContent = '检测失败: ' + (j.msg || ''); return; }
    SYS = j;
    const gb = v => (v / 1024).toFixed(1);
    el.innerHTML = 'CPU <b style="color:#c3cddb">' + j.cpu + '</b> 核 ｜ '
      + '内存 <b style="color:#c3cddb">' + gb(j.total_mb) + 'G</b> ／ 可用 '
      + '<b style="color:' + (j.avail_mb / j.total_mb < 0.25 ? '#ff8080' : '#8fd9b6') + '">'
      + gb(j.avail_mb) + 'G</b> ｜ 每进程 ' + Math.round(j.per_worker_mb) + 'MB<br>'
      + '推荐线程 <b style="color:#ffd166">' + j.recommend + '</b>'
      + '（内存上限 ' + Math.round(j.frac * 100) + '%、CPU 上限 '
      + Math.round((j.cpu_frac || 0.8) * 100) + '% = ' + (j.cpu_cap || j.cpu) + ' 核，'
      + '低优先级运行不影响前台）'
      + (j.busy ? ' ｜ <span style="color:#ffb545">有任务在跑</span>' : '');
    const sw = document.getElementById('sw');
    if(sw && (!sw.value || +sw.value === 0)) sw.value = j.recommend;
  }catch(e){ el.textContent = '检测失败'; }
}
function useRec(){
  if(SYS) document.getElementById('sw').value = SYS.recommend;
  else loadSys();
}


/* ---------- 当前阵容 ---------- */
let CURCFG = null;
async function loadCur(){
  const box = document.getElementById('cur_box');
  if(!box) return;
  const j = await (await fetch('/api/current')).json();
  if(!j.ok){ box.innerHTML = '<span style="color:#6d7888">' + (j.msg || '没有配置') + '</span>'; return; }
  CURCFG = j;
  const seg = (j.seg_lo || j.seg_hi) ? (j.seg_lo + '~' + j.seg_hi + ' 分') : (j.file || '');
  document.getElementById('cur_seg').textContent = seg;
  const map = {};
  (j.units || []).forEach(u => { map[u.pos] = u; });
  const COLS = '20px repeat(5,76px)';
  let h = '<div class="boardbox" style="padding:8px;display:inline-block">';
  h += '<div class="glab" style="grid-template-columns:' + COLS + '"><span></span>';
  for(let c = 0; c < 5; c++) h += '<span>' + (c + 1) + '列</span>';
  h += '</div>';
  for(let r = 0; r < 5; r++){
    h += '<div class="brow" style="grid-template-columns:' + COLS + '"><div class="rlab">' + (r + 1) + '</div>';
    for(let c = 0; c < 5; c++){
      const p = r * 5 + c, u = map[p];
      if(FORB.includes(p)){ h += '<div class="slot" style="opacity:.28;height:56px"></div>'; continue; }
      if(u){
        const cc = CCOL[u.cost] || '#888';
        h += '<div class="slot on" style="--c:' + cc + ';height:56px">'
          + '<span class="od">#' + u.order + '</span>'
          + '<div class="nm">' + u.char + '</div>'
          + '<div class="cs">' + u.costume + '</div>'
          + '<div class="cf"><span style="color:' + cc + '">' + u.cost + '费</span>'
          + '<span style="color:#7b8798;font-size:10px"> 破' + u.brk
          + (u.burst ? ' 爆' + u.burst : '') + '</span></div></div>';
      }else{
        h += '<div class="slot" style="height:56px"></div>';
      }
    }
    h += '</div>';
  }
  h += '</div>';
  const over = (j.cost || 0) > 240;
  h += '<div style="font-size:11.5px;color:' + (over ? '#ff8080' : '#6d7888') + ';margin-top:5px">'
    + (j.units || []).length + ' 人　费用 <b style="color:' + (over ? '#ff8080' : '#ffd166') + '">'
    + (j.cost || 0) + ' / 240</b>'
    + (j.f ? ('　先攻 <b style="color:#4dabf7">' + j.f.toFixed(1) + '%</b>') : '')
    + (j.b ? ('　后攻 <b style="color:#06d6a0">' + j.b.toFixed(1) + '%</b>') : '')
    + '</div>';
  box.innerHTML = h;
  const chips = arr => (arr || []).map(x => '<span class="bchip2 on">' + x + '</span>').join('')
    || '<span style="font-size:11px;color:#5c6675">（无）</span>';
  document.getElementById('cur_bf').innerHTML = chips(j.bf);
  document.getElementById('cur_bs').innerHTML = chips(j.bs);
}
async function saveCurCfg(){
  if(!CURCFG || !(CURCFG.units || []).length){ alert('还没有可保存的阵容'); return; }
  const nm = await uiPrompt('给这套阵容起个名字：', '');
  if(nm === null) return;
  const team = CURCFG.units.map(u => [u.raw.split('·')[0], u.raw.split('·').slice(1).join('·'),
                                      u.pos, u.brk, u.burst]);
  const body = {name: nm, team: team, bf: CURCFG.bf, bs: CURCFG.bs,
                seg: (CURCFG.seg_lo + '-' + CURCFG.seg_hi), seg_lo: CURCFG.seg_lo,
                seg_hi: CURCFG.seg_hi, f: CURCFG.f, b: CURCFG.b};
  const j = await (await fetch('/api/save', {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)})).json();
  alert(j.msg || (j.ok ? '已保存' : '保存失败'));
}


/* ---------- 导入收藏的阵容 ---------- */
function closeImport(){ document.getElementById('imodal').classList.remove('on'); }
async function openImport(which){
  ED.impTarget = which || 'our';
  await ensureData();
  const j = await (await fetch('/api/saved')).json();
  const host = document.getElementById('ilist');
  if(!(j.list || []).length){
    host.innerHTML = '<div style="color:#6d7888;font-size:12px">还没有保存过阵容</div>';
  }else{
    host.innerHTML = (j.list || []).map(x =>
      '<div class="urow" style="--c:#3b82f6;cursor:pointer" onclick="importSavedCfg(\'' + x.id + '\')">'
      + '<div class="uname2" style="flex:1"><b>' + x.name + '</b>'
      + '<span>' + (x.season || '') + '　' + (x.cost || 0) + ' 费　' + (x.n || 0) + ' 人</span></div>'
      + '<div class="umeta2" style="color:#ffd166">' + (x.cost || 0) + '费</div></div>').join('');
  }
  document.getElementById('imodal').classList.add('on');
}
async function importSavedCfg(id){
  const j = await (await fetch('/api/saved/one?id=' + id)).json();
  if(!j.ok){ alert(j.msg || '读取失败'); return; }
  const which = ED.impTarget || 'our';
  const st = ED[which];
  // ★ 用户规则: 我方一律满破满爆（有爆发就爆3）；对手用他自己的实际破度/爆发
  const _our = (which === 'our');
  st.team = (j.units || []).map((u, i) => ({
    raw: u.boxraw || u.raw || (u.char + '·' + u.costume),
    pos: (u.pos === undefined || u.pos === null) ? 0 : u.pos,
    order: i + 1,
    brk: _our ? 5 : ((u.brk === undefined || u.brk === null) ? 5 : u.brk),
    burst: _our ? (u.has_burst ? 3 : 0) : (u.burst || 0),
    ch: u.char, co: u.costume, cost: u.cost, attr: u.attr, has_burst: u.has_burst
  }));
  st.bf = (j.bf || []).slice();
  st.bs = (j.bs || []).slice();
  closeImport();
  render(which);
  alert('已导入到' + (which === 'our' ? '我方' : '对手') + '：' + (j.name || '')
    + '（' + st.team.length + ' 人 / ' + teamCost(which) + ' 费）');
}


/* ---------- 对战详情 ---------- */
let LASTTEST = null;
function closeBattle(){ document.getElementById('bmodal').classList.remove('on'); }
async function openBattle(idx){
  if(!LASTTEST){ alert('先点一次「开始测试」'); return; }
  document.getElementById('btitle').textContent = '对战详情';
  document.getElementById('bbody').innerHTML = '<span style="color:#ffd166">模拟中…</span>';
  document.getElementById('bmodal').classList.add('on');
  const out = [];
  for(const side of ['f','b']){
    const payload = {our:{team:LASTTEST.our.map(x=>{const p=x[0].split('·');
                        return [p[0], p.slice(1).join('·'), x[1],
                                (ED.our.team.find(u=>u.raw===x[0])||{}).brk,
                                (ED.our.team.find(u=>u.raw===x[0])||{}).burst];}),
                        bf:ED.our.bf, bs:ED.our.bs},
                     opp:LASTTEST.opp, idx:idx, side:side};
    try{
      const j = await (await fetch('/api/test/detail',{method:'POST',
        headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)})).json();
      out.push({side:side, j:j});
    }catch(e){ out.push({side:side, j:{ok:false,msg:'请求失败'}}); }
  }
  renderBattle(out);
}
function renderBattle(out){
  const oks = out.filter(o => o.j && o.j.ok);
  if(!oks.length){ document.getElementById('bbody').innerHTML =
    '<span style="color:#ff8080">' + (((out[0]||{}).j||{}).msg || '模拟失败') + '</span>'; return; }
  const d0 = oks[0].j;
  let h = '<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px">';
  oks.forEach(o => {
    const good = o.j.result === '胜';
    h += '<span class="schip">' + o.j.side + ' <b style="color:'
      + (good ? '#06d6a0' : '#ff8080') + '">' + o.j.result + '</b>'
      + '<span style="color:#6d7888;font-size:10.5px"> ' + o.j.rounds + ' 回合</span></span>';
  });
  h += '<span class="schip">对手 <b style="color:#ffd166">' + (d0.score || 0) + ' 分</b>'
    + (d0.name ? (' <span style="color:#8fb6dd">' + d0.name + '</span>') : '') + '</span></div>';
  h += '<div style="font-size:11.5px;color:#6d7888;margin-bottom:5px">对手阵容</div>'
    + '<div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:8px">'
    + (d0.units || []).map(u => '<span class="bchip2" style="cursor:default">#' + (u.pos + 1)
        + ' ' + u.name + '</span>').join('') + '</div>';
  // ★ 先攻和后攻【各显示一份】日志
  oks.forEach(o => {
    const logs = (o.j.log || []);
    h += '<div style="display:flex;justify-content:space-between;align-items:center;margin:10px 0 4px">'
      + '<span style="font-size:11.5px;color:#8fb6dd">' + o.j.side + ' 回合日志</span>'
      + '<span style="font-size:11px;color:' + (o.j.result === '胜' ? '#06d6a0' : '#ff8080') + '">'
      + o.j.result + '　' + o.j.rounds + ' 回合　' + logs.length + ' 行</span></div>'
      + '<pre style="max-height:260px;overflow:auto;background:#0f141b;border:1px solid #232a38;'
      + 'border-radius:9px;padding:9px;font-size:11px;line-height:1.55;color:#a8b3c4;white-space:pre-wrap;'
      + 'margin:0 0 8px">' + (logs.join('\n') || '（没有日志）') + '</pre>';
  });
  document.getElementById('bbody').innerHTML = h;
}


/* ---------- 阵容库选人弹窗 ---------- */
let LIBPICK = null, LIBMEM = [];
function closeLibPick(){ document.getElementById('lmodal').classList.remove('on'); }
function openLibPick(){
  document.getElementById('lmodal').classList.add('on');
  libPickSearch();
}
async function libPickSearch(){
  const q = document.getElementById('lq2').value || '';
  const lo = document.getElementById('llo2').value || '';
  const hi = document.getElementById('lhi2').value || '';
  const el = document.getElementById('llist2');
  el.innerHTML = '<div style="color:#ffd166;font-size:12px">查询中…</div>';
  const j = await (await fetch('/api/lib?limit=200&q=' + encodeURIComponent(q)
      + '&lo=' + encodeURIComponent(lo) + '&hi=' + encodeURIComponent(hi))).json();
  LIBMEM = j.list || [];
  document.getElementById('linfo2').textContent =
    '匹配 ' + (j.total || 0) + ' 人（最多显示 200，按分数排序）';
  el.innerHTML = (j.list || []).map(x =>
    '<div class="erow" style="cursor:pointer;margin-bottom:3px" onclick="pickLibPlayer(\'' + x.uid + '\')">'
    + '<div style="width:60px;color:#ffd166;font-size:12px">' + x.score + '分</div>'
    + '<div style="flex:1;font-size:12px;color:#c3cddb">' + x.name + '</div>'
    + '<div style="font-size:10.5px;color:#5c6675">' + (x.at || '') + '</div>'
    + '<div style="font-size:11px;color:#6d7888;width:70px;text-align:right">' + x.uid + '</div></div>').join('')
    || '<div style="color:#6d7888;font-size:12px">没有匹配</div>';
}
async function pickLibPlayer(uid){
  let hit = (LIBMEM || []).find(x => String(x.uid) === String(uid)) || {};
  if(!hit.name){
    try{
      const j = await (await fetch('/api/lib/one?uid=' + uid)).json();
      if(j.ok) hit = {score: j.score, name: j.name};
    }catch(e){}
  }
  const sc = hit.score || '', nm = hit.name || '';
  LIBPICK = {uid: uid, score: sc, name: nm};
  const _at = (LIBMEM || []).find(x => String(x.uid) === String(uid) || true) ? '' : '';
  document.getElementById('t_libbtn').textContent = '已选：' + (sc ? sc + '分 ' : '') + nm;
  document.getElementById('t_libinfo').textContent =
    '将用他的真实阵容 + 庇佑（uid ' + uid + '）';
  closeLibPick();
  showLibBoard(uid);
}


/* ---------- 只读棋盘（显示别人阵容） ---------- */
function boardRO(units){
  const map = {};
  (units || []).forEach(u => { map[u.pos] = u; });
  const COLS = '20px repeat(5,76px)';
  let h = '<div class="boardbox" style="padding:8px;display:inline-block">';
  h += '<div class="glab" style="grid-template-columns:' + COLS + '"><span></span>';
  for(let c = 0; c < 5; c++) h += '<span>' + (c + 1) + '列</span>';
  h += '</div>';
  for(let r = 0; r < 5; r++){
    h += '<div class="brow" style="grid-template-columns:' + COLS + '"><div class="rlab">' + (r + 1) + '</div>';
    for(let c = 0; c < 5; c++){
      const p = r * 5 + c, u = map[p];
      if(FORB.includes(p)){ h += '<div class="slot" style="opacity:.28;height:56px"></div>'; continue; }
      if(u){
        const cc = CCOL[u.cost] || '#888';
        h += '<div class="slot on" style="--c:' + cc + ';height:56px">'
          + '<span class="od">#' + (u.order || 0) + '</span>'
          + '<div class="nm">' + (u.char || '') + '</div>'
          + '<div class="cs">' + (u.costume || '') + '</div>'
          + '<div class="cf"><span style="color:' + cc + '">' + (u.cost || 0) + '费</span></div></div>';
      }else{
        h += '<div class="slot" style="height:56px"></div>';
      }
    }
    h += '</div>';
  }
  h += '</div>';
  return h;
}
async function showLibBoard(uid){
  const host = document.getElementById('t_lib_board');
  if(!host) return;
  host.innerHTML = '<span style="font-size:11.5px;color:#6d7888">读取阵容中…</span>';
  try{
    const j = await (await fetch('/api/lib/one?uid=' + uid)).json();
    if(!j.ok){ host.innerHTML = '<span style="color:#ff8080">' + (j.msg || '读取失败') + '</span>'; return; }
    const us = j.units || [];
    let tot = 0; us.forEach(u => { tot += (u.cost || 0); });
    host.innerHTML = boardRO(us)
      + '<div style="font-size:11.5px;color:#6d7888;margin-top:5px">'
      + us.length + ' 人　费用 ' + tot + ' / 240'
      + '　先攻庇佑 ' + ((j.bf || []).length) + ' 个　后攻庇佑 ' + ((j.bs || []).length) + ' 个'
      + '　<span style="color:#5c6675">抓取于 ' + (j.at || '') + '</span></div>';
  }catch(e){
    host.innerHTML = '<span style="color:#ff8080">读取失败</span>';
  }
}


/* ---------- 保存我方 / 对手 阵容 ---------- */
async function _doSave(name, team, bf, bs, tag){
  const body = {name: name, team: team, bf: bf || [], bs: bs || [],
                seg: tag || '', seg_lo: null, seg_hi: null};
  const j = await (await fetch('/api/save', {method: 'POST',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})).json();
  alert(j.msg || (j.ok ? '已保存' : '保存失败'));
}
async function saveOur(){
  if(!ED.our.team.length){ alert('我方还没有阵容'); return; }
  const nm = await uiPrompt('保存我方阵容，起个名字：', '我的阵容 ' + (teamCost('our') || 0) + '费');
  if(nm === null) return;
  await _doSave(nm, fmtTeam('our'), ED.our.bf, ED.our.bs, '测试阵容-我方');
}
async function saveOpp(){
  const mode = (document.getElementById('t_mode').value) || 'range';
  if(mode === 'range'){
    alert('当前是「按分数区间」模式，没有具体某一个人的阵容可存。\n'
        + '想存对手阵容请切到「指定阵容库玩家」或「手动指定阵容」。');
    return;
  }
  let team = [], bf = [], bs = [], tag = '';
  if(mode === 'lib'){
    if(!LIBPICK){ alert('请先选一个阵容库玩家'); return; }
    const j = await (await fetch('/api/lib/one?uid=' + LIBPICK.uid)).json();
    if(!j.ok){ alert(j.msg || '读取失败'); return; }
    team = (j.units || []).map(u => [u.char, u.costume, u.pos,
                                     (u.brk === undefined ? 5 : u.brk),
                                     (u.burst || 0)]);
    bf = j.bf || []; bs = j.bs || [];
    tag = '对手 ' + (j.score || 0) + '分 ' + (j.name || '');
  }else{
    if(!ED.opp.team.length){ alert('对手还没有阵容'); return; }
    team = fmtTeam('opp'); bf = ED.opp.bf; bs = ED.opp.bs;
    tag = '测试阵容-手动对手';
  }
  const nm = await uiPrompt('保存对手阵容，起个名字：',
                    (mode === 'lib' && LIBPICK) ? (LIBPICK.score + '分 ' + LIBPICK.name) : '对手阵容');
  if(nm === null) return;
  await _doSave(nm, team, bf, bs, tag);
}


/* ---------- 页面内弹框（替代 alert/confirm/prompt） ---------- */
let _DLG = null, _DLG_INPUT = false;
function _dlgOpen(opt){
  return new Promise(resolve => {
    _DLG = resolve;
    _DLG_INPUT = !!opt.input;
    document.getElementById('dtitle').textContent = opt.title || '提示';
    document.getElementById('dmsg').textContent = opt.msg || '';
    const inp = document.getElementById('dinput');
    const cancel = document.getElementById('dcancel');
    if(opt.input){
      inp.style.display = '';
      inp.value = opt.value || '';
      setTimeout(() => { try{ inp.focus(); inp.select(); }catch(e){} }, 30);
    }else{
      inp.style.display = 'none';
    }
    cancel.style.display = (opt.cancelText === null) ? 'none' : '';
    document.getElementById('dok').textContent = opt.okText || '确定';
    document.getElementById('dmodal').classList.add('on');
  });
}
function _dlgOk(){
  if(!_DLG) return;
  const v = _DLG_INPUT ? document.getElementById('dinput').value : true;
  const r = _DLG; _DLG = null;
  document.getElementById('dmodal').classList.remove('on');
  r(v);
}
function _dlgCancel(){
  if(!_DLG) return;
  const v = _DLG_INPUT ? null : false;
  const r = _DLG; _DLG = null;
  document.getElementById('dmodal').classList.remove('on');
  r(v);
}
function uiAlert(msg, title){
  return _dlgOpen({title: title || '提示', msg: msg, cancelText: null});
}
function uiConfirm(msg, title){
  return _dlgOpen({title: title || '确认', msg: msg}).then(v => v === true);
}
function uiPrompt(msg, def, title){
  return _dlgOpen({title: title || '请输入', msg: msg, input: true, value: def || ''});
}
window.addEventListener('error', function(e){
  const el = document.getElementById('jserr');
  if(el){ el.style.display = ''; el.textContent = '脚本错误: ' + (e.message || '') + '  (行 ' + (e.lineno||'?') + ')'; }
});
window.addEventListener('unhandledrejection', function(e){
  const el = document.getElementById('jserr');
  if(el){ el.style.display = ''; el.textContent = '异步错误: ' + ((e.reason && (e.reason.message||e.reason)) || ''); }
});
document.addEventListener('keydown', function(e){
  if(!_DLG) return;
  if(e.key === 'Enter'){ e.preventDefault(); _dlgOk(); }
  if(e.key === 'Escape'){ e.preventDefault(); _dlgCancel(); }
});

window.alert = function(m){ uiAlert(m); };

/* ---------- 重置（清空已选服饰 + 庇佑） ---------- */
function resetOur(){ return resetSide('our'); }
function resetOpp(){ return resetSide('opp'); }
async function resetSide(which){
  const isOur = (which === 'our');
  const st = ED[which];
  const hasAny = (st.team && st.team.length) || (st.bf && st.bf.length) || (st.bs && st.bs.length)
                 || (!isOur && LIBPICK);
  if(!hasAny){ alert('已经是空的'); return; }
  if(!(await uiConfirm('清空' + (isOur ? '我方' : '对手') + '已选的服饰和庇佑？'))) return;
  st.team = [];
  st.bf = [];
  st.bs = [];
  if(!isOur){
    LIBPICK = null;
    const b = document.getElementById('t_libbtn');
    if(b) b.textContent = '点击选择阵容库玩家…';
    const i = document.getElementById('t_libinfo');
    if(i) i.textContent = '未选择';
    const bd = document.getElementById('t_lib_board');
    if(bd) bd.innerHTML = '';
  }
  render(which);
}

/* ---------- 云端配置弹窗 ---------- */
async function cloudCfgInfo(){
  try{ return await (await fetch('/api/cloudcfg')).json(); }catch(e){ return {ok:false}; }
}
async function openCloudCfg(){
  const j = await cloudCfgInfo();
  document.getElementById('cc_url').value = j.url || '';
  document.getElementById('cc_token').value = j.token || '';
  document.getElementById('cc_host').value = j.host || '';
  document.getElementById('cc_port').value = j.port || 22;
  document.getElementById('cc_user').value = j.user || 'root';
  document.getElementById('cc_pass').value = '';
  document.getElementById('cc_pass').placeholder = j.has_password ? '（已保存，留空不改）' : 'SSH 密码';
  document.getElementById('cc_dir').value = j.remote_dir || '/opt/bd2/capture';
  document.getElementById('ccmodal').classList.add('on');
}
function closeCloudCfg(){ document.getElementById('ccmodal').classList.remove('on'); }
async function saveCloudCfg(){
  const body = {
    url: document.getElementById('cc_url').value.trim(),
    token: document.getElementById('cc_token').value.trim(),
    host: document.getElementById('cc_host').value.trim(),
    port: +document.getElementById('cc_port').value || 22,
    user: document.getElementById('cc_user').value.trim(),
    password: document.getElementById('cc_pass').value,
    remote_dir: document.getElementById('cc_dir').value.trim(),
  };
  const j = await (await fetch('/api/cloudcfg', {method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)})).json();
  if(!j.ok){ alert(j.msg || '保存失败'); return; }
  closeCloudCfg();
  run('sync');
}
/* 点「同步云端数据」：没配置就先弹窗 */
async function syncCloud(){
  const j = await cloudCfgInfo();
  if(!j.has_config){ openCloudCfg(); return; }
  run('sync');
}


poll(); stat();

/* ★ 必须放在脚本最后（BOX/BLESS 等用 let 声明，提前调用会 TDZ 报错） */
try{
  const _qTab = new URLSearchParams(location.search).get('tab');
  activateTab(_qTab || localStorage.getItem(TABKEY) || 'team');
}catch(e){ activateTab('team'); }
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype='application/json; charset=utf-8'):
        if isinstance(body, str):
            body = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        # ★ 禁用缓存：避免浏览器拿着旧页面导致"UI 和代码不一致"
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path in ('/', '/index.html'):
            # ★ 每次启动的地址带版本参数 → 浏览器一定拿新页面，不会吃旧缓存
            if not (q.get('v') or [''])[0]:
                self.send_response(302)
                self.send_header('Location', '/?v=%s' % BUILD.replace(':', ''))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                return
            return self._send(200, PAGE.replace('__BUILDSTAMP__', BUILD),
                              'text/html; charset=utf-8')
        if u.path == '/viz':
            p = os.path.join(HERE, '阵容可视化.html')
            if not os.path.exists(p):
                return self._send(404, '还没有生成可视化', 'text/plain; charset=utf-8')
            return self._send(200, io.open(p, encoding='utf-8').read(), 'text/html; charset=utf-8')
        if u.path == '/api/status':
            return self._send(200, json.dumps(pool_stats(), ensure_ascii=False))
        if u.path == '/api/rules':
            return self._send(200, json.dumps(bd2cfg.rules(), ensure_ascii=False))
        if u.path == '/api/bless':
            kw = (q.get('q') or [''])[0].strip()
            bm = jload(BLESS_PATH)
            lst = [v for v in bm.values() if isinstance(v, dict) and v.get('name')]
            if kw:
                lst = [v for v in lst if kw in v['name'] or kw in (v.get('desc') or '')]
            lst.sort(key=lambda x: (x.get('cost', 9), x['name']))
            return self._send(200, json.dumps({'list': lst}, ensure_ascii=False))
        if u.path == '/api/cost':
            kw = (q.get('q') or [''])[0].strip()
            nm = jload(NAME_PATH)
            seen = {}
            for k, v in nm.items():
                if not isinstance(v, dict):
                    continue
                cid = v.get('costumeId') or ''
                if cid and cid not in seen:
                    _c = v.get('cost')
                    seen[cid] = {'cid': cid, 'ch': _zh.t2s(v.get('ch')),
                                 'co': _zh.t2s(v.get('co')),
                                 'raw': '%s·%s' % (v.get('ch'), v.get('co')),
                                 'cost': 30 if _c is None else _c}   # 兜底: 无费用按30
            lst = list(seen.values())
            if kw:
                lst = [x for x in lst if kw in (x['ch'] or '') or kw in (x['co'] or '')]
            # 费用从高到低（同费用按角色名排）
            lst.sort(key=lambda x: (-(x['cost'] if isinstance(x['cost'], int) else 0),
                                    x['ch'] or '', x['co'] or ''))
            return self._send(200, json.dumps({'list': lst}, ensure_ascii=False))
        if u.path == '/api/lib':
            kw = (q.get('q') or [''])[0].strip()
            lim = int((q.get('limit') or ['200'])[0])
            lo = (q.get('lo') or [''])[0].strip()
            hi = (q.get('hi') or [''])[0].strip()
            rows = load_lib()
            if lo:
                try:
                    _lo = int(lo)
                    rows = [d for d in rows if int(d.get('score') or 0) >= _lo]
                except Exception:
                    pass
            if hi:
                try:
                    _hi = int(hi)
                    rows = [d for d in rows if int(d.get('score') or 0) <= _hi]
                except Exception:
                    pass
            if kw:
                rows = [d for d in rows
                        if kw in str(d.get('name') or '') or kw in str(d.get('uid') or '')]
            cols = int(bd2cfg.rules().get('cols') or 5)
            lst = [{'uid': str(d.get('uid')), 'name': d.get('name'),
                    'score': int(d.get('score') or 0), 'rank': d.get('rank'),
                    'season': d.get('season'), 'at': str(d.get('captured_at') or '').replace('T', ' ')[:16],
                    'n': len(d.get('units') or []), 'summary': lib_summary(d, cols)}
                   for d in rows[:lim]]
            return self._send(200, json.dumps({'total': len(rows), 'list': lst,
                                               'season': SEASON_TAG},
                                              ensure_ascii=False))
        if u.path == '/api/lib/one':
            uid = (q.get('uid') or [''])[0]
            cols = int(bd2cfg.rules().get('cols') or 5)
            hit = None
            for d in load_lib():
                if str(d.get('uid')) == uid:
                    hit = d
                    break
            if not hit:
                return self._send(200, json.dumps({'ok': False, 'msg': '没找到'}, ensure_ascii=False))
            us = []
            for u2 in sorted(hit.get('units') or [], key=lambda z: z.get('order') or 0):
                try:
                    p = int(u2.get('pos'))
                except Exception:
                    p = 0
                if p < 0:
                    p = 0
                _c, _k = norm_unit(u2.get('char'), u2.get('costume'))
                us.append(enrich_unit(u2.get('order'), p, _c, _k,
                                      u2.get('brk'), u2.get('burst')))
            return self._send(200, json.dumps({
                'ok': True, 'uid': uid, 'name': hit.get('name'), 'score': hit.get('score'),
                'rank': hit.get('rank'), 'season': hit.get('season'),
                'at': str(hit.get('captured_at') or '').replace('T', ' ')[:16],
                'bf': [_zh.t2s(x) for x in (hit.get('bless_first') or [])],
                'bs': [_zh.t2s(x) for x in (hit.get('bless_second') or [])],
                'units': us, 'cols': cols, 'rows': int(bd2cfg.rules().get('rows') or 5)}, ensure_ascii=False))
        if u.path == '/api/saved':
            lst = load_saved()
            _cur = str(bd2cfg.rules().get('season_name') or '')
            out = [{'id': x.get('id'), 'name': x.get('name'),
                    'seg': x.get('seg') or '', 'f': x.get('f'), 'b': x.get('b'),
                    'cost': x.get('cost'), 'at': x.get('at'),
                    'season': x.get('season') or _cur,
                    'n': len(x.get('team') or [])}
                   for x in lst]
            return self._send(200, json.dumps({'list': out}, ensure_ascii=False))
        if u.path == '/api/saved/one':
            sid = (q.get('id') or [''])[0]
            for x in load_saved():
                if str(x.get('id')) == sid:
                    # ★ 庇佑名归一化到当前列表里的写法（收藏里可能是繁体）
                    try:
                        _bl = json.load(io.open(os.path.join(HERE, 'bless_id_map.json'), encoding='utf-8'))
                        _blnames = []
                        for _k2, _v2 in _bl.items():
                            _nm2 = _v2.get('name') if isinstance(_v2, dict) else None
                            if _nm2:
                                _blnames.append(_nm2)
                        _blmap = {_zh.t2s(n): n for n in _blnames}
                        for _f2 in ('bf', 'bs'):
                            x[_f2] = [_blmap.get(_zh.t2s(n), n) for n in (x.get(_f2) or [])]
                    except Exception:
                        pass
                    us = []
                    for it in (x.get('team') or []):
                        # ★ 旧收藏里可能是抓包原始名（role680/id68001）→ 先归一化
                        _c, _k = norm_unit(it[0], it[1])
                        _u = enrich_unit(len(us) + 1, it[2], _c, _k,
                                         it[3] if len(it) > 3 else None,
                                         it[4] if len(it) > 4 else None)
                        _u['raw'] = '%s·%s' % (it[0], it[1])
                        _u['has_burst'] = bool(((db_costumes().get((_c, _k)) or (None, {}))[1] or {}).get('burst'))
                        _bk = box_key(_c, _k)
                        if _bk:
                            _u['boxraw'] = _bk
                        us.append(_u)
                    d2 = dict(x)
                    d2['units'] = us
                    d2['ok'] = True
                    return self._send(200, json.dumps(d2, ensure_ascii=False))
            return self._send(200, json.dumps({'ok': False, 'msg': '没找到'}, ensure_ascii=False))
        if u.path == '/saved_view':
            sid = (q.get('id') or [''])[0]
            hit = None
            for x in load_saved():
                if str(x.get('id')) == sid:
                    hit = x
                    break
            if not hit:
                return self._send(404, '没找到这套阵容', 'text/plain; charset=utf-8')
            cfg = {'team': hit.get('team') or [], 'bf': hit.get('bf') or [],
                   'bs': hit.get('bs') or [], 'f': hit.get('f'), 'b': hit.get('b'),
                   'bs_score': hit.get('b'), 'seg_lo': hit.get('seg_lo'),
                   'seg_hi': hit.get('seg_hi')}
            sub = '分段 %s ｜ 保存于 %s ｜ 先攻 %s ｜ 后攻 %s' % (
                hit.get('seg') or '-', hit.get('at') or '-',
                ('%.1f%%' % hit['f']) if hit.get('f') else '未测',
                ('%.1f%%' % hit['b']) if hit.get('b') else '未测')
            html = MH.render_one(cfg, hit.get('name') or '保存的阵容', sub)
            return self._send(200, html, 'text/html; charset=utf-8')
        if u.path == '/lib_view':
            uid = (q.get('uid') or [''])[0]
            hit = None
            for d in load_lib():
                if str(d.get('uid')) == uid:
                    hit = d
                    break
            if not hit:
                return self._send(404, '没找到这个玩家', 'text/plain; charset=utf-8')
            cols = int(bd2cfg.rules().get('cols') or 5)
            team = []
            for z in sorted(hit.get('units') or [], key=lambda y: y.get('order') or 0):
                try:
                    pp = int(z.get('pos'))
                except Exception:
                    pp = 0
                _c, _k = norm_unit(z.get('char'), z.get('costume'))
                _brk = str(z.get('brk') or '').replace('+', '')
                _bnum = 0
                if _brk and _brk not in ('-', ''):
                    try:
                        _bnum = int(_brk)
                    except Exception:
                        _bnum = 0
                _bs2 = 0
                _bt = str(z.get('burst') or '')
                if _bt.startswith('Lv'):
                    try:
                        _bs2 = int(_bt[2:])
                    except Exception:
                        _bs2 = 0
                team.append([_c, _k, pp if pp >= 0 else 0, _bnum, _bs2])
            cfg = {'team': team, 'bf': hit.get('bless_first') or [],
                   'bs': hit.get('bless_second') or [], 'f': None, 'b': None}
            sub = 'UID %s ｜ %s 分 ｜ %s' % (uid, hit.get('score'), hit.get('season') or '')
            html = MH.render_one(cfg, hit.get('name') or '阵容', sub)
            return self._send(200, html, 'text/html; charset=utf-8')
        if u.path == '/api/current':
            res = {'ok': False, 'msg': '还没有搜索结果的配置文件'}
            for fn in ('_S49_RESULT.json', '_S49_LAST.json', '_S49_2000.json', '_S49_2300.json'):
                fp = os.path.join(HERE, fn)
                if not os.path.exists(fp):
                    continue
                try:
                    cfg = json.load(io.open(fp, encoding='utf-8'))
                except Exception:
                    continue
                cost, attr = _maps()
                br = box_raw()
                units = []
                tot = 0
                for i, it in enumerate(cfg.get('team') or []):
                    c, k = norm_unit(it[0], it[1])
                    # ★ 2026-11-07 用户规则: 当前阵容是【我方】→ 满破满爆
                    b, bu = 5, (3 if has_burst(c, k) else 0)
                    cp = cost.get((c, k)) or 30
                    tot += cp
                    units.append({'order': i + 1,
                                  'char': _zh.t2s(c), 'costume': _zh.t2s(k),
                                  'raw': '%s·%s' % (c, k),
                                  'pos': int(it[2]) if str(it[2]).lstrip('-').isdigit() else 0,
                                  'cost': cp,
                                  'attr': _zh.t2s(attr.get((c, k)) or '?'),
                                  'brk': b, 'burst': bu})
                res = {'ok': True, 'file': fn, 'units': units, 'cost': tot,
                       'bf': cfg.get('bf') or [], 'bs': cfg.get('bs') or [],
                       'seg_lo': cfg.get('seg_lo'), 'seg_hi': cfg.get('seg_hi'),
                       'f': cfg.get('f'), 'b': cfg.get('b')}
                break
            return self._send(200, json.dumps(res, ensure_ascii=False))
        if u.path == '/api/sysinfo':
            try:
                import _mem
                cpu = os.cpu_count() or 4
                total, avail = _mem.stats()
                per = _mem.PER_WORKER_MB
                rec = _mem.fit_workers(cpu, quiet=True)
                running = bool(JOB['proc'] and JOB['proc'].poll() is None)
                res = {'ok': True, 'cpu': cpu,
                       'total_mb': round(total), 'avail_mb': round(avail),
                       'per_worker_mb': per, 'recommend': rec, 'max': cpu,
                       'frac': _mem.MEM_FRAC, 'cpu_frac': _mem.CPU_FRAC,
                       'cpu_cap': max(1, int(round(cpu * _mem.CPU_FRAC))),
                       'busy': running}
            except Exception as _e:
                res = {'ok': False, 'msg': str(_e)}
            return self._send(200, json.dumps(res, ensure_ascii=False))
        if u.path == '/api/cost/one':
            raw = (q.get('raw') or [''])[0]
            brk = (q.get('brk') or ['5'])[0]
            bst = (q.get('bst') or ['0'])[0]
            try:
                res = costume_detail(raw, brk, bst)
            except Exception as _e:
                res = {'ok': False, 'msg': '读取失败: %s' % _e}
            return self._send(200, json.dumps(res, ensure_ascii=False))
        if u.path == '/api/poolstat':
            try:
                lo = int((q.get('lo') or ['0'])[0] or 0)
                hi = int((q.get('hi') or ['99999'])[0] or 99999)
                pool = load_pool()
                if not pool:
                    return self._send(200, json.dumps(
                        {'ok': False, 'msg': '还没有对手池：先用云端同步或抓取数据，再建池'},
                        ensure_ascii=False))
                n = len([y for y in pool if lo <= (y[3] or 0) <= hi])
                _sc = [y[3] or 0 for y in pool]
                res = {'ok': True, 'lo': lo, 'hi': hi, 'inrange': n, 'total': len(pool),
                       'min': min(_sc) if _sc else 0, 'max': max(_sc) if _sc else 0}
            except Exception as _e:
                res = {'ok': False, 'msg': str(_e)}
            return self._send(200, json.dumps(res, ensure_ascii=False))
        if u.path == '/api/cloudcfg':
            cfg = {}
            try:
                cfg = json.load(io.open(os.path.join(HERE, 'cloud.json'), encoding='utf-8'))
            except Exception:
                cfg = {}
            ssh = cfg.get('ssh') or {}
            return self._send(200, json.dumps({
                'ok': True,
                'url': cfg.get('url') or '',
                'token': cfg.get('token') or '',
                'host': ssh.get('host') or '',
                'port': ssh.get('port') or 22,
                'user': ssh.get('user') or 'root',
                'remote_dir': ssh.get('remote_dir') or '/opt/bd2/capture',
                'has_password': bool(ssh.get('password')),
                'has_config': bool(cfg.get('url') or ssh.get('host')),
            }, ensure_ascii=False))
        if u.path == '/api/box':
            return self._send(200, json.dumps({'list': box_list()}, ensure_ascii=False))
        if u.path == '/api/log':
            since = int((q.get('since') or [-1])[0])
            with LOCK:
                lines = JOB['lines'][since + 1:] if since >= 0 else JOB['lines']
                total = len(JOB['lines']) - 1
                running = bool(JOB['proc'] and JOB['proc'].poll() is None)
                name = JOB['name']
            return self._send(200, json.dumps({'lines': lines, 'total': total,
                                               'running': running, 'name': name},
                                              ensure_ascii=False))
        return self._send(404, 'not found', 'text/plain; charset=utf-8')

    def do_POST(self):
        n = int(self.headers.get('Content-Length') or 0)
        try:
            req = json.loads(self.rfile.read(n).decode('utf-8') or '{}')
        except Exception:
            return self._send(400, json.dumps({'ok': False, 'msg': 'bad json'}, ensure_ascii=False))

        if self.path == '/api/stop':
            with LOCK:
                _p = JOB.get('proc')
                if not _p or _p.poll() is not None:
                    return self._send(200, json.dumps(
                        {'ok': False, 'msg': '当前没有正在运行的任务'}, ensure_ascii=False))
                _name = JOB.get('name') or ''
                try:
                    subprocess.run(['taskkill', '/F', '/T', '/PID', str(_p.pid)],
                                   capture_output=True)
                except Exception:
                    try:
                        _p.kill()
                    except Exception:
                        pass
                JOB['lines'].append('=== 已手动停止（%s） ===' % _name)
            return self._send(200, json.dumps(
                {'ok': True, 'msg': '已停止：%s' % _name}, ensure_ascii=False))
        if self.path == '/api/test/detail':
            try:
                res = test_detail(req)
            except Exception as _e:
                res = {'ok': False, 'msg': '出错: %s' % _e}
            return self._send(200, json.dumps(res, ensure_ascii=False))
        if self.path == '/api/test':
            try:
                res = run_test(req)
            except Exception as _e:
                res = {'ok': False, 'msg': '测试出错: %s' % _e}
            return self._send(200, json.dumps(res, ensure_ascii=False))
        if self.path == '/api/cloudcfg':
            url = (req.get('url') or '').strip()
            host = (req.get('host') or '').strip()
            if not url and not host:
                return self._send(200, json.dumps(
                    {'ok': False, 'msg': '数据地址 和 服务器地址 至少填一个'},
                    ensure_ascii=False))
            old = {}
            try:
                old = json.load(io.open(os.path.join(HERE, 'cloud.json'), encoding='utf-8'))
            except Exception:
                old = {}
            pwd = req.get('password')
            if pwd in (None, ''):
                pwd = ((old.get('ssh') or {}).get('password') or '')
            cfg = {'url': url, 'token': (req.get('token') or '').strip(), 'build_pool': 1,
                   'ssh': {}}
            if host:
                cfg['ssh'] = {
                    'host': host,
                    'port': int(req.get('port') or 22),
                    'user': (req.get('user') or 'root').strip(),
                    'password': pwd,
                    'remote_dir': (req.get('remote_dir') or '/opt/bd2/capture').strip(),
                }
            io.open(os.path.join(HERE, 'cloud.json'), 'w', encoding='utf-8', newline='').write(
                json.dumps(cfg, ensure_ascii=False, indent=1))
            return self._send(200, json.dumps({'ok': True, 'msg': '已保存'},
                                              ensure_ascii=False))
        if self.path == '/api/save':
            if req.get('team'):
                cfg = {'team': req['team'], 'bf': req.get('bf') or [],
                       'bs': req.get('bs') or [], 'seg_lo': req.get('seg_lo'),
                       'seg_hi': req.get('seg_hi'), 'f': req.get('f'), 'b': req.get('b')}
                nm = (req.get('name') or '').strip() or '保存的阵容'
                tot = 0
                try:
                    _cm, _ = _maps()
                    def _cst(_it):
                        _c2, _k2 = norm_unit(_it[0], _it[1])
                        return _cm.get((_c2, _k2)) or 30
                    tot = sum(_cst(it) for it in cfg['team'])
                except Exception:
                    pass
                lst = load_saved()
                lst.insert(0, {'id': str(int(time.time() * 1000)), 'name': nm,
                               'seg': req.get('seg') or '', 'seg_lo': cfg['seg_lo'],
                               'seg_hi': cfg['seg_hi'], 'team': cfg['team'],
                               'bf': cfg['bf'], 'bs': cfg['bs'], 'f': cfg['f'],
                               'b': cfg['b'], 'cost': tot,
                               'at': time.strftime('%Y-%m-%d %H:%M')})
                store_saved(lst)
                return self._send(200, json.dumps({'ok': True, 'msg': '已保存：%s' % nm}, ensure_ascii=False))
            src = os.path.join(HERE, '_S49_LAST.json')
            if not os.path.exists(src):
                src = os.path.join(HERE, '_S49_RESULT.json')
            if not os.path.exists(src):
                src = os.path.join(HERE, '_S49_2000.json')
            if not os.path.exists(src):
                return self._send(200, json.dumps({'ok': False, 'msg': '还没有可保存的阵容'}, ensure_ascii=False))
            cfg = json.load(io.open(src, encoding='utf-8'))
            nm = (req.get('name') or '').strip() or ('%s-%s' % (cfg.get('seg_lo'), cfg.get('seg_hi')))
            tot = 0
            try:
                _cm, _ = _maps()
                for _it in (cfg.get('team') or []):
                    _c2, _k2 = norm_unit(_it[0], _it[1])
                    tot += _cm.get((_c2, _k2)) or 30
            except Exception:
                pass
            # 从配置保存时：补上破度/爆发（配置里没存这两项）
            try:
                _box = json.load(io.open(os.path.join(HERE, 'my_box.json'), encoding='utf-8'))
                _burst = {}
                for _k, _v in _box.items():
                    if '·' in _k:
                        _a, _b = _k.split('·', 1)
                        _na, _nb = norm_unit(_a, _b)
                        _burst[(_na, _nb)] = _v.get('burst') or 0
                _team = []
                for _it in (cfg.get('team') or []):
                    _c2, _k2 = norm_unit(_it[0], _it[1])
                    _br = 5
                    _bu = _burst.get((_c2, _k2), 0)
                    _team.append([_c2, _k2, _it[2], _br, _bu])
                cfg = dict(cfg, team=_team)
            except Exception:
                pass
            lst = load_saved()
            lst.insert(0, {'id': str(int(time.time() * 1000)), 'name': nm,
                           'seg': '%s-%s' % (cfg.get('seg_lo'), cfg.get('seg_hi')),
                           'seg_lo': cfg.get('seg_lo'), 'seg_hi': cfg.get('seg_hi'),
                           'team': cfg.get('team'), 'bf': cfg.get('bf'), 'bs': cfg.get('bs'),
                           'f': cfg.get('f'), 'b': cfg.get('b'), 'cost': tot,
                           'season': str(bd2cfg.rules().get('season_name') or ''),
                           'at': time.strftime('%Y-%m-%d %H:%M')})
            store_saved(lst)
            return self._send(200, json.dumps({'ok': True, 'msg': '已保存：%s' % nm}, ensure_ascii=False))
        if self.path == '/api/saved/del':
            sid = str(req.get('id') or '')
            lst = [x for x in load_saved() if str(x.get('id')) != sid]
            store_saved(lst)
            return self._send(200, json.dumps({'ok': True}, ensure_ascii=False))
        if self.path in ('/api/rules', '/api/bless', '/api/cost'):
            return self._send(200, json.dumps(
                {'ok': False, 'msg': '只读模式：改数据请直接编辑对应的 json 文件'}, ensure_ascii=False))
        if self.path != '/api/run':
            return self._send(404, 'not found', 'text/plain; charset=utf-8')
        task = req.get('task')
        args = req.get('args') or {}
        if task == 'capture':
            ok, msg = start_job('全量抓取', [PY, '-u', 'bd2tool.py', 'capture', '--n', str(args.get('n', 1000))])
        elif task == 'sync':
            ok, msg = start_job('同步云端数据', [PY, '-u', '_sync_cloud.py'])
        elif task == 'pool':
            ok, msg = start_job('重建对手池', [PY, '-u', 'bd2tool.py', 'pool'])
        elif task == 'merge':
            full = str(args.get('full', 0)) == '1'
            ok, msg = start_job('整合总库' + ('（全赛季）' if full else '（本赛季）'),
                                [PY, '-u', 'bd2tool.py', 'merge'] + (['--full'] if full else []))
        elif task == 'search':
            lo, hi = str(args.get('lo', 2000)), str(args.get('hi', 99999))
            cmd = [PY, '-u', 'bd2tool.py', 'search', '--lo', lo, '--hi', hi]
            if args.get('n'):
                cmd += ['--n', str(args['n'])]
            if str(args.get('quick', 0)) == '1':
                cmd += ['--quick']
            env_w = {'WORKERS': str(args['workers'])} if args.get('workers') else None
            ok, msg = start_job('搜索 %s~%s%s' % (lo, hi, '(快速)' if str(args.get('quick', 0)) == '1' else ''),
                                cmd, env_w)
        elif task == 'verify':
            cfg = str(args.get('cfg', '_S49_2000.json'))
            env_w = {'WORKERS': str(args['workers'])} if args.get('workers') else None
            ok, msg = start_job('复核 %s' % cfg,
                                [PY, '-u', 'bd2tool.py', 'verify', '--cfg', cfg,
                                 '--lo', str(args.get('lo', 2000)), '--hi', str(args.get('hi', 99999)),
                                 '--n', str(args.get('n', 10))], env_w)
        elif task == 'html':
            ok, msg = start_job('生成可视化', [PY, '-u', 'bd2tool.py', 'html'])
        else:
            ok, msg = False, '未知任务'
        return self._send(200, json.dumps({'ok': ok, 'msg': msg}, ensure_ascii=False))


if __name__ == '__main__':
    srv = ThreadingHTTPServer(('127.0.0.1', PORT), H)
    url = 'http://127.0.0.1:%d' % PORT
    print('控制台已启动: %s' % url)
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('已停止')
