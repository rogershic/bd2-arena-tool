# -*- coding: utf-8 -*-
"""BD2 黄金竞技场 一体化工具（CLI）
用法:
  python bd2tool.py status                      # 看当前状态
  python bd2tool.py capture [--n 1000]          # 全量抓取（排行榜→阵容→入库→建池）
  python bd2tool.py pool                        # 只重建对手池
  python bd2tool.py search --lo 2000 --hi 2299  # 分段搜索阵容
  python bd2tool.py verify --cfg _S49_2000.json --lo 2000 --hi 2299 --n 10
  python bd2tool.py html                        # 重新生成可视化页面
"""
import argparse
import io
import shutil
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# ★ 2026-11-07: 主配置文件改名（旧的 _S49_2000.json 是历史命名，容易误解）
RESULT_CFG = '_S49_RESULT.json'
LEGACY_CFG = '_S49_2000.json'    # 旧名，兼容老命令


def sync_result_cfg(src):
    """把 src 同步成主配置（同时更新 _S49_LAST.json 和旧名镜像）"""
    for dst in (RESULT_CFG, '_S49_LAST.json', LEGACY_CFG):
        try:
            shutil.copy(src, os.path.join(HERE, dst))
        except Exception as e:
            print('  同步 %s 失败: %s' % (dst, e))
    ok = os.path.exists(os.path.join(HERE, RESULT_CFG))
    if ok:
        print('  已同步为 %s / _S49_LAST.json（旧名 %s 保留镜像）' % (RESULT_CFG, LEGACY_CFG))
    else:
        print('  ✘ 同步主配置失败，后续步骤已跳过')
PY = r'D:\soft\python3.10\python.exe'
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_ENV = {
    'PYTHONIOENCODING': 'utf-8',
    'PYTHONHASHSEED': '0',
    'USE_POT_MAX': '0',
    'ENEMY_ALWAYS_CRIT': '1',
    'CRIT_RANDOM': '1',
    'BD2_SEASON': '49',
    'BD2_LOGIN_FILE': 'batch_capture_s49.jsonl',
    'BD2_SEASON_TAG': '赛季49',
    'BD2_MINSCORE': '1400',
}


def env(**kw):
    e = dict(os.environ)
    e.update(BASE_ENV)
    for k, v in kw.items():
        e[k] = str(v)
    return e


def run(script, *args, **kw):
    """跑一个脚本，输出直接透传到控制台"""
    cmd = [PY, '-u', script] + [str(a) for a in args]
    print('\n▶ %s %s' % (script, ' '.join(str(a) for a in args)), flush=True)
    p = subprocess.run(cmd, cwd=HERE, env=env(**kw))
    if p.returncode != 0:
        raise SystemExit('❌ %s 失败 (code %d)' % (script, p.returncode))


def step(msg):
    print('\n' + '=' * 58)
    print('  ' + msg)
    print('=' * 58, flush=True)


# ---------------- 各功能 ----------------

def do_status():
    step('当前状态')
    rp = os.path.join(HERE, 'ranking_full_new.json')
    pp = os.path.join(HERE, '_opp_cache.pkl')
    dp = os.path.join(HERE, '阵容历史库.jsonl')
    if os.path.exists(rp):
        rank = json.load(io.open(rp, encoding='utf-8'))
        sc = [p['score'] for p in rank]
        print('  排行榜   : %d 人  %d ~ %d（榜首 %s）' % (
            len(rank), min(sc), max(sc),
            max(rank, key=lambda p: p['score'])['name']))
    if os.path.exists(pp):
        import pickle
        POOL, _ = pickle.load(io.open(pp, 'rb'))
        sc = [y[3] or 0 for y in POOL]
        print('  对手池   : %d 套  %d ~ %d' % (len(POOL), min(sc), max(sc)))
        for lo in (2400, 2300, 2200, 2100, 2000, 1900):
            print('             %d+ : %3d 套' % (lo, sum(1 for s in sc if s >= lo)))
    if os.path.exists(dp):
        n = sum(1 for _ in io.open(dp, encoding='utf-8', errors='replace'))
        print('  阵容历史库: %d 条（每人一条）' % n)
    print()
    print('  已保存的配置:')
    got = False
    for f in sorted(os.listdir(HERE)):
        if f.startswith('_S49') and f.endswith('.json'):
            try:
                d = json.load(io.open(os.path.join(HERE, f), encoding='utf-8'))
                if isinstance(d, dict) and d.get('team'):
                    got = True
                    print('    %-22s %d人  先攻%d个/后攻%d个庇佑  %s' % (
                        f, len(d['team']), len(d.get('bf') or []), len(d.get('bs') or []),
                        d.get('note', d.get('seg', ''))))
            except Exception:
                pass
    if not got:
        print('    （还没有保存过阵容配置）')


def do_capture(n=1000):
    step('① 拉排行榜')
    run('_s47_fetch_rank.py', n)
    step('② 生成抓取队列')
    cur = json.load(io.open(os.path.join(HERE, 'ranking_full_new.json'), encoding='utf-8'))
    cur.sort(key=lambda x: -x['score'])
    with io.open(os.path.join(HERE, 'uid_queue.txt'), 'w', encoding='utf-8', newline='') as f:
        for p in cur:
            f.write('%d\n' % p['uid'])
    print('  写入 %d 个 UID' % len(cur))
    step('③ 抓每个人阵容（约 80 秒）')
    old = os.path.join(HERE, 'piggy_raw.jsonl')
    if os.path.exists(old):
        os.replace(old, os.path.join(HERE, 'piggy_raw_prev.jsonl'))
    io.open(old, 'w').close()
    run('_fetch_all_now.py', n)
    step('④ 生成报告')
    run('report_lineups.py')
    step('⑤ 入库（同 UID 覆盖）')
    ts = __import__('datetime').datetime.now().strftime('%m-%d %H:%M')
    run('_archive_lineups.py', '防守阵容_最新300名.txt', '赛季49', 'S49 %s 全量' % ts)
    step('⑥ 合并进总库（本赛季）')
    run('_merge_pool.py')
    step('⑦ 建对手池（整合总库 + 本赛季）')
    _merged = os.path.join(HERE, '阵容总库.jsonl')
    if os.path.exists(_merged):
        run('build_pool.py', BD2_DB='阵容总库.jsonl', BD2_ALL='1',
            BD2_MINSCORE='0', BD2_SEASON_TAG='赛季49')
    else:
        run('build_pool.py')
    do_status()


def do_pool():
    step('重建对手池')
    # ★ 2026-11-06: 默认用【整合总库 + 本赛季】，否则只有榜内 1000 人、高分段样本太少
    merged = os.path.join(HERE, '阵容总库.jsonl')
    if os.path.exists(merged):
        print('  数据源: 阵容总库.jsonl（本赛季49，含榜外玩家）')
        run('build_pool.py', BD2_DB='阵容总库.jsonl', BD2_ALL='1',
            BD2_MINSCORE='0', BD2_SEASON_TAG='赛季49')
    else:
        print('  数据源: 阵容历史库.jsonl（只含当前榜）')
        run('build_pool.py')
    do_status()


def do_search(lo, hi, n=None, quick=False, sample=None, seedfile=None):
    lo, hi = str(lo), str(hi)
    kw = {'SEGLO': lo, 'SEGHI': hi}
    if quick:
        kw['QUICK'] = '1'
    if n:
        kw['N_VERIFY'] = str(n)
    if sample:
        kw['SAMPLE_SCREEN'] = str(sample)
        kw['SAMPLE_OPT'] = str(sample)
    step('搜索阵容：%s ~ %s%s' % (lo, hi, '（快速模式）' if quick else ''))
    if seedfile:
        run('_s49opt2.py', SEEDFILE=seedfile, **kw)
    else:
        run('_s49fast.py', **kw)
    # ★ 把刚搜出来的阵容同步成主配置，避免精修用旧阵容当起点（踩过坑）
    fast = os.path.join(HERE, '_S49_FAST.json')
    if not os.path.exists(fast):
        print('  ✘ 搜索没有产出结果（_S49_FAST.json 不存在），停止后续步骤')
        return
    if os.path.exists(fast):
        sync_result_cfg(fast)
        print('  ※ %s 里装的就是【本次搜索出的阵容+庇佑+胜率】' % RESULT_CFG)
        print('    候选阵容来自全库去重，对手来自 %s~%s 分段的全部对手' % (lo, hi))
    nrep = str(n or (3 if quick else 6))
    step('后攻庇佑精修（N=%s）' % nrep)
    run('_s49bs4.py', SEGLO=lo, SEGHI=hi, NS=('100' if quick else '180'), NREP=nrep,
        CFGFILE=RESULT_CFG, N_FINAL=nrep, TIME_LIMIT=('120' if quick else '240'))
    step('先攻庇佑精修（N=%s）' % nrep)
    run('_s49bs5.py', SEGLO=lo, SEGHI=hi, NS=('100' if quick else '180'), NREP=nrep,
        CFGFILE=RESULT_CFG, FIRST='1', TIME_LIMIT=('120' if quick else '240'))
    step('最终复核 + 写回胜率（N=%s）' % nrep)
    do_verify(RESULT_CFG, lo, hi, int(nrep), save=True)
    sync_result_cfg(os.path.join(HERE, RESULT_CFG))
    step('生成可视化')
    do_html()


_last_scores = {}


def do_verify(cfg, lo, hi, N, save=False):
    _t = '本次搜索结果' if os.path.basename(cfg).startswith('_S49_') else cfg
    step('复核 %s 在 %s~%s（N=%s）  文件: %s' % (_t, lo, hi, N, os.path.basename(cfg)))
    code = r'''
import io,os,sys,json,copy,pickle,random
os.environ['USE_POT_MAX']='0'; os.environ['ENEMY_ALWAYS_CRIT']='1'; os.environ['CRIT_RANDOM']='1'
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
HERE=__HERE__
sys.path.insert(0,HERE)
import _sim3 as S
S.bless_points([])
try:
    BOX=json.load(io.open(os.path.join(HERE,'my_box.json'),encoding='utf-8'))
except Exception:
    BOX={}   # 没个人数据也能复核
BURST={}
for k,v in BOX.items():
    if k=='_說明' or '·' not in k: continue
    ch,co=k.split('·',1); BURST[(ch,co)]=max(BURST.get((ch,co),0),v.get('burst') or 0)
POOL,_=pickle.load(io.open(os.path.join(HERE,'_opp_cache.pkl'),'rb'))
C=json.load(io.open(os.path.join(HERE,'__CFG__'),encoding='utf-8'))
def en(u):
    X=S.clone_team(u)
    for x in X:
        q=x.get('pos')
        if not isinstance(q,int):
            try: q=int(q)
            except Exception: q=0
        x['pos']=q if q>=0 else 0
    return X
t=[]
for i,(ch,co,pos) in enumerate(C['team']):
    u=S.unit_stats(ch,co,i+1,pos,5,BURST.get((ch,co),0)); u['pos']=pos; u['order']=i+1; t.append(u)
g=[y for y in POOL if int('__LO__')<=(y[3] or 0)<=int('__HI__')]
N=int('__N__')
a=b=0
for _i,y in enumerate(g):
    for r in range(N):
        random.seed(1000+r+_i*17); a+= S.battle(S.clone_team(t),en(y[0]),True,list(C['bf']),y[2])[0]=='A'
        random.seed(2000+r+_i*17); b+= S.battle(S.clone_team(t),en(y[0]),False,list(C['bs']),y[1])[0]=='A'
n=len(g)*N
print()
print('  %s套 N=%d  先 %.1f%%  后 %.1f%%  综合 %.1f%%' % (len(g),N,100.0*a/n,100.0*b/n,50.0*(a+b)/n))
print('__SCORES__ %.4f %.4f' % (100.0*a/n, 100.0*b/n))
'''
    code = (code.replace('__HERE__', repr(HERE)).replace('__CFG__', cfg)
                .replace('__LO__', str(lo)).replace('__HI__', str(hi))
                .replace('__N__', str(N)))
    p = subprocess.run([PY, '-u', '-c', code], cwd=HERE, env=env(),
                       stdout=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
    for _line in (p.stdout or '').splitlines():
        if _line.startswith('__SCORES__'):
            _pr = _line.split()
            _last_scores[cfg] = (float(_pr[1]), float(_pr[2]))
        else:
            print(_line)
    if p.returncode != 0:
        raise SystemExit('❌ 复核失败')
    if save:
        import io as _io, json as _json
        cf = os.path.join(HERE, cfg)
        d = _json.load(_io.open(cf, encoding='utf-8'))
        fv, bv = _last_scores.get(cfg) or (None, None)
        if fv is not None:
            d['f'] = fv
            d['b'] = bv
            d['bs_score'] = bv
            d['check_n'] = N
            _json.dump(d, _io.open(cf, 'w', encoding='utf-8', newline=''),
                       ensure_ascii=False, indent=1)
            print('  已写回 %s: 先攻 %.1f / 后攻 %.1f' % (cfg, fv, bv))


def do_merge(full=False):
    step('① 合并所有来源 → 阵容总库.jsonl（同 UID 只留最新）')
    run('_merge_pool.py')
    step('② 用总库重建对手池')
    if full:
        print('  模式: 全量（所有赛季 / 不看榜内）')
        run('build_pool.py', BD2_DB='阵容总库.jsonl', BD2_ALL='1',
            BD2_MINSCORE='0', BD2_SEASON_TAG='ALL')
    else:
        print('  模式: 只取本赛季49（推荐，站位不会被旧赛季污染）')
        run('build_pool.py', BD2_DB='阵容总库.jsonl', BD2_ALL='1',
            BD2_MINSCORE='0', BD2_SEASON_TAG='赛季49')
    do_status()


def do_sync():
    step('从云端同步数据')
    run('_sync_cloud.py')
    do_status()


def do_html():
    step('生成可视化页面')
    run('_make_html.py')
    path = os.path.join(HERE, '阵容可视化.html')
    print('\n  打开方式: %s' % path)


def main():
    ap = argparse.ArgumentParser(description='BD2 黄金竞技场一体化工具')
    sub = ap.add_subparsers(dest='cmd')

    sub.add_parser('status')
    p = sub.add_parser('capture')
    p.add_argument('--n', type=int, default=1000)
    sub.add_parser('pool')
    sub.add_parser('sync')
    p = sub.add_parser('search')
    p.add_argument('--lo', type=int, required=True)
    p.add_argument('--hi', type=int, default=99999)
    p.add_argument('--seed', default=None, help='用指定 JSON 当种子阵容')
    p.add_argument('--n', type=int, default=None, help='复核/精修用的 N（越大越准越慢，默认6）')
    p.add_argument('--sample', type=int, default=None, help='抽样对手数（默认粗筛80/精修120）')
    p.add_argument('--quick', action='store_true', help='快速模式：小样本+N=1，只用来排序')
    p = sub.add_parser('verify')
    p.add_argument('--cfg', required=True)
    p.add_argument('--lo', type=int, default=2000)
    p.add_argument('--hi', type=int, default=99999)
    p.add_argument('--n', type=int, default=10)
    p.add_argument('--no-save', action='store_true', help='只算不写回配置')
    p = sub.add_parser('merge')
    p.add_argument('--full', action='store_true', help='连旧赛季一起进池（默认只取本赛季）')
    sub.add_parser('html')

    a = ap.parse_args()
    if a.cmd == 'status':
        do_status()
    elif a.cmd == 'capture':
        do_capture(a.n)
    elif a.cmd == 'sync':
        do_sync()
    elif a.cmd == 'pool':
        do_pool()
    elif a.cmd == 'search':
        do_search(a.lo, a.hi, n=a.n, quick=a.quick, sample=a.sample, seedfile=a.seed)
    elif a.cmd == 'verify':
        do_verify(a.cfg, a.lo, a.hi, a.n, save=not a.no_save)
        if not a.no_save:
            do_html()
    elif a.cmd == 'merge':
        do_merge(a.full)
    elif a.cmd == 'html':
        do_html()
    else:
        ap.print_help()


if __name__ == '__main__':
    main()
