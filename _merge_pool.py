# -*- coding: utf-8 -*-
"""把【所有】阵容来源合并成一个总库：同 UID 只留最新一条，旧的丢弃
   输出: 阵容总库.jsonl（按 uid 排序，每人一条）
"""
import glob
import io
import json
import os
import shutil
import sys
import datetime

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '阵容总库.jsonl')

# 所有解析过的阵容来源（不含 raw 抓包和 txt 报告）
pats = ['阵容历史库*.jsonl', '阵容历史库*.jsonl.bak_*']
srcs = []
for p in pats:
    srcs += glob.glob(os.path.join(HERE, p))
srcs = sorted(set(srcs))

print('扫描到 %d 个来源:' % len(srcs))
for s in srcs:
    print('   %-46s %8.1f MB' % (os.path.basename(s), os.path.getsize(s) / 1048576.0))

best = {}
n_read = 0
n_bad = 0
for s in srcs:
    for line in io.open(s, encoding='utf-8', errors='replace'):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            n_bad += 1
            continue
        uid = str(d.get('uid') or '')
        units = d.get('units') or []
        if not uid or not units:
            n_bad += 1
            continue
        n_read += 1
        key = (str(d.get('captured_at') or ''), len(units))
        cur = best.get(uid)
        if cur is None or key > cur[0]:
            best[uid] = (key, d)

print()
print('读入 %d 条（坏行 %d），合并后 %d 个 UID（%d 条被覆盖删除）' % (
    n_read, n_bad, len(best), n_read - len(best)))

# 备份旧总库
if os.path.exists(OUT):
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    shutil.copy2(OUT, OUT + '.bak_' + stamp)

with io.open(OUT, 'w', encoding='utf-8', newline='') as f:
    for uid in sorted(best):
        f.write(json.dumps(best[uid][1], ensure_ascii=False) + '\n')

# 统计
import collections
seas = collections.Counter(str(v[1].get('season') or '?') for v in best.values())
sc = sorted(int(v[1].get('score') or 0) for v in best.values())
print()
print('总库: %s' % OUT)
print('  赛季分布: %s' % dict(seas))
print('  分数范围: %d ~ %d' % (sc[0], sc[-1]))
print('  文件大小: %.1f MB' % (os.path.getsize(OUT) / 1048576.0))
