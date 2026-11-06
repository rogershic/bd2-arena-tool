# -*- coding: utf-8 -*-
"""快速版: 粗筛(N=1, 小样本) → 只精修榜首那套 → 高精度复核
   目标分段由 SEGLO 指定（默认 1800）
"""
import io, os, sys, time, json, copy, pickle, random, collections
import multiprocessing as mp
os.environ['USE_POT_MAX'] = '0'
os.environ['ENEMY_ALWAYS_CRIT'] = '1'
os.environ['CRIT_RANDOM'] = '1'
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bd2cfg

MAXCOST = bd2cfg.max_cost()
LED = bd2cfg.cells()
SEGLO = int(os.environ.get('SEGLO', '1800') or 1800)

# ★★★ 2026-11-06: 速度/精度参数全部可调（网页和命令行都能传）
#   耗时 ≈ 对手数 × 2(先/后攻) × N ；N 是最直接的加速开关
_QUICK = os.environ.get('QUICK', '0') == '1'
SAMPLE_SCREEN = int(os.environ.get('SAMPLE_SCREEN') or (50 if _QUICK else 80))
N_SCREEN      = int(os.environ.get('N_SCREEN') or 1)
SAMPLE_OPT    = int(os.environ.get('SAMPLE_OPT') or (60 if _QUICK else 120))
N_OPT         = int(os.environ.get('N_OPT') or (1 if _QUICK else 2))
N_VERIFY      = int(os.environ.get('N_VERIFY') or (3 if _QUICK else 6))
import _mem
import multiprocessing as _mp0
_WANT = int(os.environ.get('WORKERS') or min(20, (os.cpu_count() or 8)))
WORKERS = (_mem.fit_workers(_WANT, quiet=True) if _mp0.current_process().name == 'MainProcess'
           else max(1, _WANT))
if _mp0.current_process().name == 'MainProcess':
    _mem.set_low_priority()      # ★ 低于正常优先级，子进程继承 → 前台不卡

def _pool_n(want=None):
    """★ 每次建池都按【当前】可用内存重量，内存被别的程序占了就自动减进程数"""
    return _mem.fit_workers(want if want is not None else _WANT, quiet=True)

# ★ 只在主进程打印一次（worker 进程 import 时不要刷屏）
if __import__('multiprocessing').current_process().name == 'MainProcess':
    print('参数: 粗筛 %d套/N=%d ｜ 精修 %d套/N=%d ｜ 复核 全部/N=%d ｜ 并行 %d' % (
        SAMPLE_SCREEN, N_SCREEN, SAMPLE_OPT, N_OPT, N_VERIFY, WORKERS), flush=True)
SEGHI = int(os.environ.get('SEGHI', '99999') or 99999)
try:
    _R = bd2cfg.rules()
    ROWS, COLS = int(_R.get('rows') or 5), int(_R.get('cols') or 5)
    FORB = set(int(x) for x in (_R.get('forbidden') or [4, 6, 18, 20]))
except Exception:
    ROWS = COLS = 5
    FORB = {4, 6, 18, 20}
G = BURST = S = COST = None


def init(nscreen, seedn=1):
    global G, BURST, S, COST
    import _sim3 as _S
    _S.bless_points([])
    S = _S
    try:
        BOX = json.load(io.open(os.path.join(HERE, 'my_box.json'), encoding='utf-8'))
    except Exception:
        BOX = {}           # 没有个人服饰数据也能跑
    BURST = {}
    for k, v in BOX.items():
        if k == '_說明' or '·' not in k:
            continue
        ch, co = k.split('·', 1)
        BURST[(ch, co)] = max(BURST.get((ch, co), 0), v.get('burst') or 0)
    # ★ 2026-11-07 用户规则: 一律满破满爆 → 该服饰有爆发就爆 3
    #   my_box 只有我拥有的衣服，其它一律爆0
    #   → 用 chars_db 把【所有有爆发的服饰】都补成 3（简繁两套键）
    try:
        import _zh as _zhx
        for _c in json.load(io.open(os.path.join(HERE, 'chars_db.json'), encoding='utf-8')):
            for _x in (_c.get('costumes') or []):
                if _x.get('burst'):
                    _k1 = (_c.get('character'), _x.get('costumeName'))
                    BURST[_k1] = 3
                    BURST[(_zhx.t2s(_k1[0]), _zhx.t2s(_k1[1]))] = 3
    except Exception:
        pass
    NM = json.load(io.open(os.path.join(HERE, 'name_map.json'), encoding='utf-8'))
    COST = {(v['ch'], v['co']): v['cost'] for v in NM.values() if v.get('cost')}
    POOL, _ = pickle.load(io.open(os.path.join(HERE, '_opp_cache.pkl'), 'rb'))
    P = [y for y in POOL if SEGLO <= (y[3] or 0) <= SEGHI]
    # ★ 该区间一个对手都没有 → 直接给提示，不要跑下去除零
    if not P:
        _sc = [y[3] or 0 for y in POOL]
        print('  对手池里没有 %d~%d 分的人（池子分数范围 %d ~ %d，共 %d 套）'
          % (SEGLO, SEGHI, min(_sc) if _sc else 0, max(_sc) if _sc else 0, len(POOL)), flush=True)
        print('  换个区间再试（比如 %d~%d）' % (min(_sc) if _sc else 0, max(_sc) if _sc else 0), flush=True)
        sys.exit(0)
    if nscreen and nscreen < len(P):
        P = random.Random(seedn).sample(P, nscreen)
    G = P


def en(units):
    D = S.clone_team(units)
    for u in D:
        p = u.get('pos')
        if not isinstance(p, int):
            try:
                p = int(p)
            except Exception:
                p = 0
        u['pos'] = p if p >= 0 else 0
    return D


def ev(args):
    team, bf, bs, nrep = args
    if sum(COST.get((c, k), 999) for c, k, _ in team) > MAXCOST:
        return (-1.0, -1.0)
    t = []
    for i, (ch, co, pos) in enumerate(team):
        u = S.unit_stats(ch, co, i + 1, pos, 5, BURST.get((ch, co), 0))
        if not u:
            return (-1.0, -1.0)
        u['pos'] = pos
        u['order'] = i + 1
        t.append(u)
    if len(set(x['pos'] for x in t)) < len(t):
        return (-1.0, -1.0)
    a = b = 0
    for _i, y in enumerate(G):
        for r in range(nrep):
            random.seed(1000 + r + _i * 17)
            a += S.battle(S.clone_team(t), en(y[0]), True, list(bf), y[2])[0] == 'A'
            random.seed(2000 + r + _i * 17)
            b += S.battle(S.clone_team(t), en(y[0]), False, list(bs), y[1])[0] == 'A'
    n = len(G) * nrep
    if n <= 0:                      # ★ 该区间没有对手 → 不要除零
        return (-1.0, -1.0)
    return (100.0 * a / n, 100.0 * b / n)


def main():
    global COST
    NM0 = json.load(io.open(os.path.join(HERE, 'name_map.json'), encoding='utf-8'))
    COST = {(v['ch'], v['co']): v['cost'] for v in NM0.values() if v.get('cost')}
    DB = json.load(io.open(os.path.join(HERE, 'chars_db.json'), encoding='utf-8'))
    EN2CN = {}
    for c in DB:
        for co in (c.get('costumes') or []):
            EN2CN[((c.get('enName') or '').lower(), co.get('costumeName'))] = (c.get('character'), co.get('costumeName'))
    BM = json.load(io.open(os.path.join(HERE, 'bless_id_map.json'), encoding='utf-8'))
    PTS = {}
    for k, v in BM.items():
        if isinstance(v, dict) and v.get('name'):
            PTS[v['name']] = v.get('cost') or v.get('point') or 1

    POOL, _ = pickle.load(io.open(os.path.join(HERE, '_opp_cache.pkl'), 'rb'))
    # ★★★ 2026-11-06 用户规则:
    #   ① 找阵容要从【目标分段之上】的玩家阵容里抄（更强的阵容打这个分段）
    #   ② 完全相同的阵容只留一套，取【破度/爆发最高】的那一套
    # ★ 2026-11-06 用户要求: 候选用【全库去重后的阵容】，不再限制在本段之上
    #   （CAND_ABOVE=1 可切回"只用本段之上"的旧行为）
    CAND_ABOVE = os.environ.get('CAND_ABOVE', '0') == '1'
    _src = [y for y in POOL if (not CAND_ABOVE) or (y[3] or 0) > SEGHI]
    if CAND_ABOVE and len(_src) < 20:
        print('  本段之上的阵容只有 %d 套 → 退回全池', len(_src), flush=True)
        _src = list(POOL)
    print('  候选来源: %s（%d 套玩家阵容）' % ('本段之上' if CAND_ABOVE else '全池', len(_src)), flush=True)
    best_sig = {}      # sig -> ((破度和, 爆发和), (tm, bf, bs))
    cands = []
    freq = collections.Counter()

    def _num(v):
        import re as _re
        if v is None: return 0
        m = _re.search(r'(\d+)', str(v))
        return int(m.group(1)) if m else 0

    for y in _src:
        units = sorted(y[0], key=lambda z: z.get('order') or 0)
        tm = []
        ok = True
        used = set()
        for u in units:
            nm = u.get('name') or ''
            if '·' not in nm:
                ok = False
                break
            ch, co = nm.split('·', 1)
            k = EN2CN.get((ch.lower(), co)) or (ch, co)
            if k not in COST:
                ok = False
                break
            freq[k] += 1
            p = u.get('pos')
            if not isinstance(p, int):
                try:
                    p = int(p)
                except Exception:
                    p = 0
            if p < 0:
                p = 0
            if p in used or p not in LED:
                f = [q for q in LED if q not in used]
                if not f:
                    ok = False
                    break
                p = f[0]
            used.add(p)
            tm.append((k[0], k[1], p))
        if not ok or not (4 <= len(tm) <= 7):
            continue
        if sum(COST[(c, k)] for c, k, _ in tm) > MAXCOST:
            continue
        bf, bs = list(y[1] or []), list(y[2] or [])
        if sum(PTS.get(x.lstrip('~'), 1) for x in bf) > 6 or sum(PTS.get(x.lstrip('~'), 1) for x in bs) > 8:
            continue
        _w = sum(_num(u.get('brk')) for u in units)
        _b = sum(_num(u.get('burst')) for u in units)
        sig = tuple(sorted(tm))            # ② 阵容签名（含站位）
        prev = best_sig.get(sig)
        if prev is None or (_w, _b) > prev[0]:
            best_sig[sig] = ((_w, _b), (tuple(tm), bf, bs))
    cands = [v[1] for v in best_sig.values()]
    print('  去重后候选 %d 套（同阵容已按破度/爆发取最高）' % len(cands), flush=True)
    print('候选 %d 套 → 粗筛 N=%d / %d套样本' % (len(cands), N_SCREEN, SAMPLE_SCREEN), flush=True)

    ctx = mp.get_context()
    with ctx.Pool(processes=_pool_n(), initializer=init, initargs=(SAMPLE_SCREEN, 5)) as po:
        r = po.map(ev, [(t, bf, bs, N_SCREEN) for t, bf, bs in cands], chunksize=2)
    order = sorted(range(len(cands)), key=lambda i: -(r[i][0] + r[i][1]))
    b0 = cands[order[0]]
    s0 = r[order[0]]
    print('粗筛最佳: 先%.1f 后%.1f 综%.1f  %s' % (
        s0[0], s0[1], (s0[0] + s0[1]) / 2,
        ' | '.join('%s·%s@%d' % (c, k, p) for c, k, p in b0[0])), flush=True)
    print('  先攻: %s' % ' + '.join(b0[1]))
    print('  后攻: %s' % ' + '.join(b0[2]), flush=True)

    # 精修：快速模式只换人；慢速模式 = 换人 + 换站位 + 换顺位
    cards = [k for k, _ in freq.most_common(40)]
    FULL = (not _QUICK) or os.environ.get('SWAP_MODE') == 'full'
    USABLE = [p for p in range(ROWS * COLS) if p not in FORB]
    LIMIT = int(os.environ.get('OPT_TIME_LIMIT') or (300 if FULL else 150))
    t_opt = time.time()

    def _cost_ok(tt):
        return sum(COST.get((c, k), 999) for c, k, _ in tt) <= MAXCOST

    def _moves(team):
        """生成邻域：[(新阵容, 说明)]"""
        out = []
        # ① 换人：某个位置换成别的卡（站位/顺位不变）
        for i in range(len(team)):
            used = set((c, k) for j, (c, k, p) in enumerate(team) if j != i)
            for card in cards:
                if card in used:
                    continue
                tt = list(team)
                tt[i] = (card[0], card[1], tt[i][2])
                if _cost_ok(tt):
                    out.append((tuple(tt), '换人#%d→%s·%s' % (i + 1, card[0], card[1])))
        if not FULL:
            return out
        # ② 换站位：把自己挪到空格
        used_pos = set(p for _, _, p in team)
        for i in range(len(team)):
            for p in USABLE:
                if p in used_pos:
                    continue
                tt = list(team)
                tt[i] = (tt[i][0], tt[i][1], p)
                out.append((tuple(tt), '移站位#%d→%d' % (i + 1, p)))
        # ③ 交换两人站位
        for i in range(len(team)):
            for j in range(i + 1, len(team)):
                tt = list(team)
                tt[i] = (tt[i][0], tt[i][1], team[j][2])
                tt[j] = (tt[j][0], tt[j][1], team[i][2])
                out.append((tuple(tt), '换站位#%d↔#%d' % (i + 1, j + 1)))
        # ④ 换顺位：只交换卡的出手顺序，站位不动
        for i in range(len(team)):
            for j in range(i + 1, len(team)):
                tt = list(team)
                tt[i] = (team[j][0], team[j][1], team[i][2])
                tt[j] = (team[i][0], team[i][1], team[j][2])
                if _cost_ok(tt):
                    out.append((tuple(tt), '换顺位#%d↔#%d' % (i + 1, j + 1)))
        return out

    team = list(b0[0])
    with ctx.Pool(processes=_pool_n(), initializer=init, initargs=(SAMPLE_OPT, 9)) as po:
        cur = po.apply(ev, ((tuple(team), b0[1], b0[2], N_OPT),))
        print()
        print('精修起点 先%.1f 后%.1f 综%.1f%s' % (
            cur[0], cur[1], (cur[0] + cur[1]) / 2,
            '（换人+换站位+换顺位）' if FULL else '（只换人）'), flush=True)
        for it in range(6 if FULL else 2):
            if FULL and time.time() - t_opt > LIMIT:
                print('  精修到时间上限（%d秒），停' % LIMIT, flush=True)
                break
            mv = _moves(team)
            if not mv:
                print('  第%d轮: 没有可试的邻域' % (it + 1), flush=True)
                break
            jobs = [(t2, b0[1], b0[2], N_OPT) for t2, _ in mv]
            rr = po.map(ev, jobs, chunksize=8)
            k2 = max(range(len(rr)), key=lambda x: rr[x][0] + rr[x][1])
            score = rr[k2][0] + rr[k2][1]
            print('  第%d轮: 试了 %d 个邻域，最好 %s → 先%.1f 后%.1f 综%.1f' % (
                it + 1, len(mv), mv[k2][1], rr[k2][0], rr[k2][1], score / 2), flush=True)
            if score > cur[0] + cur[1] + 0.5:
                team = list(jobs[k2][0])
                cur = rr[k2]
                print('       采纳 → %s' % ' | '.join('%s·%s@%d' % (c, k, p) for c, k, p in team),
                      flush=True)
            else:
                print('       无改进，结束精修', flush=True)
                break

    # 复核
    with ctx.Pool(processes=_pool_n(), initializer=init, initargs=(0, 1)) as po:
        fin = po.apply(ev, ((tuple(team), b0[1], b0[2], N_VERIFY),))
    _npool = len([1 for y in pickle.load(io.open(os.path.join(HERE, '_opp_cache.pkl'), 'rb'))[0]
                  if SEGLO <= (y[3] or 0) <= SEGHI])
    print()
    print('★ %d+ 复核(N=%d, 全部%d套): 先%.1f 后%.1f 综%.1f' % (
        SEGLO, N_VERIFY, _npool, fin[0], fin[1], (fin[0] + fin[1]) / 2))
    print('   费 %d' % sum(COST.get((c, k), 0) for c, k, _ in team))
    for i, (c, k, p) in enumerate(team):
        print('   #%d %s·%s %d行%d列(pos%d) %d费' % (i + 1, c, k, p // 5 + 1, p % 5 + 1, p, COST.get((c, k), 0)))
    print('   先攻(%d点): %s' % (sum(PTS.get(x.lstrip('~'), 1) for x in b0[1]), ' + '.join(b0[1])))
    print('   后攻(%d点): %s' % (sum(PTS.get(x.lstrip('~'), 1) for x in b0[2]), ' + '.join(b0[2])))
    json.dump({'team': [list(x) for x in team], 'bf': b0[1], 'bs': b0[2],
               'f': fin[0], 'b': fin[1], 'seg': SEGLO,
               'seg_lo': SEGLO, 'seg_hi': SEGHI},
              io.open(os.path.join(HERE, '_S49_FAST.json'), 'w', encoding='utf-8', newline=''),
              ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
