# -*- coding: utf-8 -*-
"""建对手池 v2（2026-10-26 用户要求）
   ① 同一 uid 只保留【最新】阵容（阵容变了就更新）
   ② 分数用【当前排行榜】的分数（不在该分段的，旧数据自动剔除）
"""
import io, os, sys, json, pickle, re
os.environ['USE_POT_MAX'] = '0'
# 2026-10-27 修正: 阵容历史库不记录爆发 -> 之前所有人默认爆0, 严重低估对手
OPP_BURST = 3
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
MIN_SCORE = int(os.environ.get('BD2_MINSCORE', '1900'))   # ★ 新赛季初期榜单低 → 用 1500
sys.path.insert(0, HERE)
import _sim3 as S
try:
    EN2CN = json.load(io.open(os.path.join(HERE, 'en2cn.json'), encoding='utf-8'))
except Exception:
    EN2CN = {}
# name_map: 「角色·服饰」整体键 -> {ch, co, cost}  (英文名兜底用)
try:
    NM_ALL = json.load(io.open(os.path.join(HERE, 'name_map.json'), encoding='utf-8'))
except Exception:
    NM_ALL = {}

# ★ 2026-11-07 用户规则: 对手一律满破，服饰有爆发就按爆3
import _zh                      # 繁→简（DB 是繁体名，抓包记录是简体名，必须统一）

BURST_COS = set()
try:
    for _c in json.load(io.open(os.path.join(HERE, 'chars_db.json'), encoding='utf-8')):
        for _x in (_c.get('costumes') or []):
            if _x.get('burst'):
                BURST_COS.add((_zh.t2s(_c.get('character')),
                               _zh.t2s(_x.get('costumeName'))))
except Exception:
    pass


def _has_burst(ch, co):
    """该服饰有没有爆发（简繁都归一后再查）"""
    return ((_zh.t2s(ch), _zh.t2s(co)) in BURST_COS
            or (ch, co) in BURST_COS)


OPP_BRK = 5
OPP_BURST = 3

CO_ALIAS = {                       # 游戏里显示英文、我们库里有中文的服饰
    'Sealed': '封印的欲望',
    'SealedDesires': '封印的欲望',
}

def _parse_brk(x):
    """'+5' -> 5, '-' -> 0, 100 -> 0"""
    s = str(x or '').strip().lstrip('+')
    try:
        v = int(s)
        return v if 0 <= v <= 5 else 0
    except Exception:
        return 0


def _parse_burst(x):
    """'Lv3' -> 3, 'Lv1' -> 1, '-' -> 0, '3' -> 3"""
    s = str(x or '').strip()
    if s in ('', '-', 'None'):
        return 0
    if s.lower().startswith('lv'):
        s = s[2:]
    try:
        v = int(s)
        return v if 0 <= v <= 3 else 0
    except Exception:
        return 0



# ★★★ 2026-11-05 S49 新规则: 禁用格改成 pos 4 / 6 / 18 / 20（用户截图确认）
#   旧 S48 的 8 格（1,3,7,10,14,17,21,23）已全部解禁
#   用 BD2_BLOCKED 环境变量可覆盖，便于兼容旧赛季回测
_env_forb = os.environ.get('BD2_BLOCKED')
if _env_forb:
    FORB = {int(x) for x in _env_forb.split(',') if x.strip()}
else:
    import bd2cfg as _cfg
    FORB = {int(x) for x in (_cfg.rules().get('forbidden') or [4, 6, 18, 20])}
USABLE = [p for p in range(25) if p not in FORB]

# ---------- 当前排行榜：uid -> 分数 ----------
rk = json.load(io.open(os.path.join(HERE, 'ranking_full_new.json'), encoding='utf-8'))
CUR = {}
for r in rk:
    u = str(r.get('uid') or '')
    if u:
        CUR[u] = r.get('score') or 0
print('当前榜 %d 人' % len(CUR))

# ---------- 历史库：每个 uid 取最新一条 ----------
# ★★★ 2026-11-05 新增: 新赛季规则变了（S49: 7人/240费/禁用格4,6,18,20）
#     上赛季的旧阵容不能混进来 → 只取【当前赛季】标签的记录
#     赛季标签用 BD2_SEASON_TAG 指定（默认 '赛季49'）
SEASON_TAG = os.environ.get('BD2_SEASON_TAG') or '赛季49'
# ★★★ 2026-11-06: 支持指定数据库（默认历史库；可指向合并后的"阵容总库.jsonl"）
DBFILE = os.environ.get('BD2_DB') or '阵容历史库.jsonl'
ONLY_RANK = (os.environ.get('BD2_ALL', '0') != '1')   # BD2_ALL=1 → 榜外的人也进池
recs = [json.loads(l) for l in io.open(os.path.join(HERE, DBFILE), encoding='utf-8') if l.strip()]
print('数据库: %s（%d 条）｜ 只取榜内=%s' % (DBFILE, len(recs), ONLY_RANK))
_skip_season = 0
best = {}
for r in recs:
    u = str(r.get('uid') or '')
    if not u:
        continue
    _sea = str(r.get('season') or '')
    if SEASON_TAG != 'ALL' and _sea and SEASON_TAG not in _sea:
        _skip_season += 1
        continue
    if len(r.get('units') or []) < 4:   # ★ s48 初期很多人只放4人防守, 允许4~5人
        continue
    key = (r.get('captured_at') or '', len(r.get('units') or []))
    if u not in best or key > (best[u].get('captured_at') or '', len(best[u].get('units') or [])):
        best[u] = r
print('历史库去重: %d -> %d 人' % (len(recs), len(best)))

dropped_stale = 0
dropped_norank = 0
pool = []
filled = 0
for uid, r in best.items():
    if uid not in CUR:
        if ONLY_RANK:
            dropped_norank += 1
            continue                  # ② 不在当前榜 → 剔除
        sc = int(r.get('score') or 0)  # ★ BD2_ALL=1: 用他最后一次抓到的分数
    else:
        sc = CUR[uid]                 # ② 用当前分数
    if sc < MIN_SCORE:                # ★ 可配置: BD2_MINSCORE (默认1900; 新赛季初期榜低要调小)
        dropped_stale += 1
        continue
    units = r['units']
    used = set()
    for u in units:
        p = u.get('pos')
        try:
            p = int(p)
        except Exception:
            p = 0
        if p < 0:
            p = 0                      # ★ pos-1 = 第1行第1列(pos0)，实测占17.8%，不是"未放置"
        used.add(p)
    free = [p for p in USABLE if p not in used]
    out = []
    ok = True
    for u in units:
        pos = u.get('pos')
        try:
            pos = int(pos)
        except Exception:
            pos = 0
        if pos < 0:
            pos = 0                    # ★ 同上
        if pos not in USABLE:
            pos = free.pop(0) if free else 0
            filled += 1
        brk = u.get('brk'); brk = int(''.join(c for c in str(brk) if c.isdigit()) or 0)
        burst = u.get('burst')
        if isinstance(burst, str):
            m = re.search(r'(\d+)', burst)
            burst = int(m.group(1)) if m else 0
        elif burst is None:
            burst = 0
        ch = u.get('char') or ''
        co = u.get('costume') or ''
        x = S.unit_stats(ch, co, u.get('order') or 1, pos,
                         _parse_brk(u.get('brk')), _parse_burst(u.get('burst')))
        if not x:
            # ★ 英文名兜底: 游戏里未译的中文条目会以英文出现(如 Aquila·SealedDesires)
            _ch2 = EN2CN.get(ch, ch)
            _co2 = CO_ALIAS.get(co, co)
            if (_ch2, _co2) != (ch, co):
                x = S.unit_stats(_ch2, _co2, u.get('order') or 1, pos,
                         _parse_brk(u.get('brk')), _parse_burst(u.get('burst')))
        if not x:
            # ★★★ 2026-11-05 再加一层: 用 name_map 的「角色·服饰」整体键兜底
            #   例 'Aquila·SealedDesires' → name_map 里能找到 {ch:阿奇拉, co:封印的欲望}
            _ent = NM_ALL.get('%s·%s' % (ch, co)) or NM_ALL.get('%s·%s' % (_ch2, _co2))
            if _ent:
                x = S.unit_stats(_ent.get('ch'), _ent.get('co'), u.get('order') or 1, pos,
                         _parse_brk(u.get('brk')), _parse_burst(u.get('burst')))
        if not x:
            ok = False; break
        x['pos'] = pos; x['order'] = u.get('order') or 1
        # ★ 2026-11-07 用户规则: 对手用【他自己实际的破度/爆发】（抓包里有真数据）
        #   满破满爆只用于【我方】候选阵容（见 _s49fast.py）
        x['brk'] = _parse_brk(u.get('brk'))
        x['burst'] = _parse_burst(u.get('burst'))
        out.append(x)
    if not ok or len(out) < 4:        # ★ s48 初期 735 人是【4人防守】(pos-1 就是 pos0), 不能丢
        continue
    bf = r.get('bless_first') or []
    bs = r.get('bless_second') or []
    # ★ 2026-11-07 用户要求: 池子里带上 uid 和昵称（对战详情要显示"输给谁"）
    pool.append((out, bf, bs, sc, str(uid), (r.get('name') or '')))

print('剔除：不在当前榜 %d 人 / 分数跌破1900 %d 人' % (dropped_norank, dropped_stale))
print('建成 %d 套（补位 %d）' % (len(pool), filled))
for lo, hi in ((2500,2599),(2600,2699),(2700,9999),(2400,2499),(1900,1999)):
    print('   %d-%d: %d 套' % (lo, min(hi,9999), sum(1 for x in pool if lo <= (x[3] or 0) <= hi)))

pickle.dump(pool, io.open(os.path.join(HERE, '_opp_1900.pkl'), 'wb'))
try:
    box = json.load(io.open(os.path.join(HERE, 'my_box.json'), encoding='utf-8'))
except Exception:
    box = {}
BYCO = {}
for k, v in box.items():
    if k == '_說明' or '·' not in k:
        continue
    ch, co = k.split('·', 1)
    d = dict(v); d['break'] = 5
    BYCO.setdefault(co, d)
pickle.dump((pool, BYCO), io.open(os.path.join(HERE, '_opp_cache.pkl'), 'wb'))
print('已写 _opp_1900.pkl / _opp_cache.pkl')
