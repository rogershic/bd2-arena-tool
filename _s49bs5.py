# -*- coding: utf-8 -*-
"""针对当前 _S49_2300.json 的阵容，单独把【后攻】庇佑爬到最优
   从现有后攻组出发，逐条增/删/换，预算 8 点，抽样加速
"""
import io, os, sys, json, copy, pickle, random
import multiprocessing as mp
os.environ['USE_POT_MAX'] = '0'
os.environ['ENEMY_ALWAYS_CRIT'] = '1'
os.environ['CRIT_RANDOM'] = '1'
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SEGLO = int(os.environ.get('SEGLO', '2000') or 2000)
NS = int(os.environ.get('NS', '200') or 200)
NREP = int(os.environ.get('NREP', '6') or 6)
CFGFILE = os.environ.get('CFGFILE') or (
    '_S49_RESULT.json' if os.path.exists(os.path.join(HERE, '_S49_RESULT.json'))
    else '_S49_2300.json')
CFG = json.load(io.open(os.path.join(HERE, CFGFILE), encoding='utf-8'))
SEGHI = int(os.environ.get('SEGHI', '99999') or 99999)
import _mem
import multiprocessing as _mp0
_WANT = int(os.environ.get('WORKERS') or min(20, (os.cpu_count() or 8)))
# ★ 只在主进程算一次（子进程再算会刷屏，且子进程不用它建池）
WORKERS = (_mem.fit_workers(_WANT, quiet=True) if _mp0.current_process().name == 'MainProcess'
           else max(1, _WANT))
if _mp0.current_process().name == 'MainProcess':
    _mem.set_low_priority()      # ★ 低于正常优先级，子进程继承 → 前台不卡

def _pool_n(want=None):
    """★ 每次建池都按【当前】可用内存重量，内存被别的程序占了就自动减进程数"""
    return _mem.fit_workers(want if want is not None else _WANT, quiet=True)

TIME_LIMIT = int(os.environ.get('TIME_LIMIT', '150') or 150)
import time as _time
if __import__('multiprocessing').current_process().name == 'MainProcess':
    print('配置: %s ｜ 区间 %d~%d ｜ 目标: %s' % (
        CFGFILE, SEGLO, SEGHI, '先攻' if os.environ.get('FIRST','0')=='1' else '后攻'), flush=True)
TEAM = [tuple(x) for x in CFG['team']]
BF = list(CFG['bf'])
GS = BURST = S = None
BM = json.load(io.open(os.path.join(HERE, 'bless_id_map.json'), encoding='utf-8'))
PTS = {}
for k, v in BM.items():
    if isinstance(v, dict) and v.get('name'):
        PTS[v['name']] = v.get('cost') or v.get('point') or 1
ALLB = sorted(PTS.keys())


def init():
    global GS, BURST, S
    import _sim3 as _S
    _S.bless_points([])
    S = _S
    try:
        BOX = json.load(io.open(os.path.join(HERE, 'my_box.json'), encoding='utf-8'))
    except Exception:
        BOX = {}          # 没有个人服饰数据也能跑
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
    POOL, _ = pickle.load(io.open(os.path.join(HERE, '_opp_cache.pkl'), 'rb'))
    P = [y for y in POOL if SEGLO <= (y[3] or 0) <= SEGHI]
    GS = random.Random(21).sample(P, min(NS, len(P)))


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
    bs, nrep = args
    FIRST = os.environ.get('FIRST','0')=='1'
    t = []
    for i, (ch, co, pos) in enumerate(TEAM):
        u = S.unit_stats(ch, co, i + 1, pos, 5, BURST.get((ch, co), 0))
        u['pos'] = pos
        u['order'] = i + 1
        t.append(u)
    v = 0
    for _i, y in enumerate(GS):
        for r in range(nrep):
            random.seed(2000 + r + _i * 17)
            if FIRST:
                v += S.battle(S.clone_team(t), en(y[0]), True, list(bs), list(y[2]))[0] == 'A'
            else:
                v += S.battle(S.clone_team(t), en(y[0]), False, list(bs), list(y[1]))[0] == 'A'
    return 100.0 * v / (len(GS) * nrep)


def main():
    cur = list(CFG['bf'] if os.environ.get('FIRST','0')=='1' else CFG['bs'])
    ctx = mp.get_context()
    with ctx.Pool(processes=_pool_n(), initializer=init) as po:
        _t0 = _time.time()
        cv = po.apply(ev, ((cur, NREP),))
        print('起点 %.1f%%  %s' % (cv, ' + '.join(cur)), flush=True)
        for it in range(6):
            if _time.time() - _t0 > TIME_LIMIT:
                print('  ⏱ 到时限 %ds，停止' % TIME_LIMIT, flush=True); break
            cand = []
            for add in ALLB:
                if add in cur:
                    continue
                _bud = 6 if os.environ.get('FIRST','0')=='1' else 8
                if sum(PTS.get(x, 1) for x in cur) + PTS.get(add, 1) <= _bud:
                    cand.append(cur + [add])
            for rm in list(cur):
                for add in ALLB:
                    if add in cur:
                        continue
                    nb = [x for x in cur if x != rm] + [add]
                    if sum(PTS.get(x, 1) for x in nb) <= _bud:
                        cand.append(nb)
                nb2 = [x for x in cur if x != rm]
                if nb2:
                    cand.append(nb2)
            # 去重
            seen = set()
            uniq = []
            for c in cand:
                k = tuple(sorted(c))
                if k in seen:
                    continue
                seen.add(k)
                uniq.append(c)
            rr = po.map(ev, [(c, NREP) for c in uniq], chunksize=6)
            k = max(range(len(rr)), key=lambda x: rr[x])
            if rr[k] > cv + 0.3:
                cur = uniq[k]
                cv = rr[k]
                print('  第%d轮 → %.1f%%  %s' % (it + 1, cv, ' + '.join(cur)), flush=True)
            else:
                print('  第%d轮 无改进' % (it + 1), flush=True)
                break
    # 全量复核
    global NS
    NS = 0
    with ctx.Pool(processes=_pool_n(), initializer=init) as po:
        full = po.apply(ev, ((cur, 12),))
    print()
    print('★ 最终 %.1f%%（全量 N=12）' % full)
    print('   %s  (%d点)' % (' + '.join(cur), sum(PTS.get(x, 1) for x in cur)))
    if os.environ.get('FIRST','0')=='1':
        CFG['bf'] = cur
    else:
        CFG['bs'] = cur
    json.dump(CFG, io.open(os.path.join(HERE, CFGFILE), 'w', encoding='utf-8', newline=''),
              ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
