# -*- coding: utf-8 -*-
"""阵容历史库 —— 把每次抓到的防守阵容按「分数 ↔ 阵容」永久存档

背景（用户 2026-10-22）:
  「新赛季记得抓到的阵容信息都要保存，多少分-什么阵容，
    因为后面大家分数冲上去了，就没有这些低段位的阵容了」
  ⇒ 低分段阵容是一次性资源：赛季初不存，以后再也抓不到

用法:
  python _archive_lineups.py <报告文件> [赛季号] [标签]
  默认: 防守阵容_最新300名.txt  赛季47  当前快照

输出:
  阵容历史库.jsonl   每行一条 = 某次快照里某个玩家的阵容
  字段: captured_at / season / tag / rank / score / uid / name / guild /
        win / lose / units[{order,pos,char,costume,cp,lv,brk,burst,pot}] /
        bless_first / bless_second
"""
import io
import _data
import os
import re
import sys
import json
import datetime

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import sys as _bd2sys
HERE = (os.environ.get('BD2_HOME') or
        (os.path.dirname(os.path.abspath(_bd2sys.executable))
         if getattr(_bd2sys, 'frozen', False)
         else os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(HERE, sys.argv[1] if len(sys.argv) > 1 else '防守阵容_最新300名.txt')
SEASON = sys.argv[2] if len(sys.argv) > 2 else '47'
TAG = sys.argv[3] if len(sys.argv) > 3 else 'snapshot'
OUT = os.path.join(HERE, '阵容历史库.jsonl')

if not os.path.exists(SRC):
    print('❌ 找不到报告文件:', SRC)
    sys.exit(1)

# ★ 裸 ID → 名称（报告里未识别的庇佑会写成 ID110 这种）
_ID2NAME = {}
try:
    _m = json.load(io.open(_data.p('bless_id_map.json'), encoding='utf-8'))
    _ID2NAME = {int(k): v['name'] for k, v in _m.items()}
except Exception:
    pass


def _norm_bless(lst):
    """统一成【纯名字】：去掉 "(4)" 之类的点数后缀，裸 ID 翻成名字"""
    out = []
    for x in lst:
        x = re.sub(r'\(\d+\)$', '', x).strip()
        m = re.match(r'^ID(\d+)$', x)
        if m:
            out.append(_ID2NAME.get(int(m.group(1)), x))
        elif x:
            out.append(x)
    return out


lines = io.open(SRC, encoding='utf-8').read().splitlines()
now = datetime.datetime.now().isoformat(timespec='seconds')

recs = []
cur = None
for ln in lines:
    s = ln.rstrip()
    m = re.match(r'\s*UID\s+(\d+)\s+\[([^\]]*)\]', s)
    if m:
        if cur:
            recs.append(cur)
        cur = {'uid': m.group(1), 'name': m.group(2), 'rank': None, 'score': None,
               'guild': None, 'win': None, 'lose': None, 'units': [],
               'bless_first': [], 'bless_second': []}
        mr = re.search(r'名次#(-?\d+)', s)
        ms = re.search(r'胜利分(-?\d+)', s)
        mg = re.search(r'\[([^\]]*)\]', s.split(']')[0] + ']' if ']' in s else '')
        mw = re.search(r'战绩 (\S+)胜 / (\S+)负', s)
        if mr:
            cur['rank'] = int(mr.group(1))
        if ms:
            cur['score'] = int(ms.group(1))
        if mw:
            w, l = mw.group(1), mw.group(2)
            cur['win'] = int(w) if w.isdigit() else None
            cur['lose'] = int(l) if l.isdigit() else None
        # 公会名 = 第 2 个方括号
        gs = re.findall(r'\[([^\]]*)\]', s)
        if len(gs) >= 2:
            cur['guild'] = gs[1]
        continue
    if cur is None:
        continue
    m2 = re.match(r'\s*#(\d+)\s+pos(-?\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)', s)
    if m2:
        cur['units'].append({
            'order': int(m2.group(1)), 'pos': int(m2.group(2)),
            'char': m2.group(3), 'costume': m2.group(4),
            'cp': m2.group(5), 'lv': m2.group(6),
            'brk': m2.group(7), 'burst': m2.group(8), 'pot': m2.group(9),
        })
        continue
    if s.strip().startswith('先攻庇佑:'):
        cur['bless_first'] = [x.strip().lstrip('~') for x in s.split(':', 1)[1].split('+') if x.strip() and x.strip() != '-']
        continue
    if s.strip().startswith('后攻庇佑:'):
        cur['bless_second'] = [x.strip().lstrip('~') for x in s.split(':', 1)[1].split('+') if x.strip() and x.strip() != '-']
        continue
if cur:
    recs.append(cur)

# 只保留有阵容的
recs = [r for r in recs if r['units']]
for r in recs:
    r['bless_first'] = _norm_bless(r['bless_first'])
    r['bless_second'] = _norm_bless(r['bless_second'])
    r['captured_at'] = now
    r['season'] = SEASON
    r['tag'] = TAG

# 去重 key: 赛季+uid+分+阵容指纹（避免同一快照重复写）
def fp(r):
    u = '|'.join('%s:%s:%s' % (x['order'], x['pos'], x['char'] + x['costume']) for x in
                 sorted(r['units'], key=lambda x: x['order']))
    b = '|'.join(r['bless_first']) + '#' + '|'.join(r['bless_second'])
    return '%s|%s|%s|%s|%s' % (r['season'], r['uid'], r['score'], u, b)

# ★★★ 2026-11-05 用户要求: 同一个 UID 只保留【最新一条】，旧的直接覆盖（不再追加）
#   实现: 先读入现有全部记录 → 按 captured_at 取每人最新 → 用本次抓到的覆盖 → 整体写回
store = {}
if os.path.exists(OUT):
    for ln in io.open(OUT, encoding='utf-8'):
        ln = ln.strip()
        if not ln:
            continue
        try:
            d = json.loads(ln)
        except Exception:
            continue
        u = str(d.get('uid') or '')
        if not u:
            continue
        key = (d.get('captured_at') or '', len(d.get('units') or []))
        if u not in store or key > (store[u].get('captured_at') or '', len(store[u].get('units') or [])):
            store[u] = d

before = len(store)
added = replaced = 0
for r in recs:
    u = str(r.get('uid') or '')
    if not u:
        continue
    if u in store:
        replaced += 1
    else:
        added += 1
    store[u] = r          # 本次抓到的永远覆盖（它是最新的）

tmp = OUT + '.tmp'
with io.open(tmp, 'w', encoding='utf-8', newline='') as f:
    for u in sorted(store):
        f.write(json.dumps(store[u], ensure_ascii=False) + '\n')
os.replace(tmp, OUT)

total = len(store)
print('本次快照: %d 个玩家有阵容' % len(recs))
print('新增 %d 人，覆盖更新 %d 人' % (added, replaced))
print('阵容历史库总计: %d 条（= %d 个 UID，每人一条）→ %s' % (total, total, OUT))

# 分数分布概览
from collections import Counter
sc = sorted(r['score'] for r in recs if r['score'])
if sc:
    print('本次分数范围: %d ~ %d' % (sc[0], sc[-1]))
