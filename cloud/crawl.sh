#!/usr/bin/env bash
# 云端抓取：抓排行榜 → 抓每个人阵容 → 报告 → 去重入库（合并到总库）
# 只做"取数据 + 去重入库"，不建对手池（对手池在本地建，省服务器资源）
set -euo pipefail

CAP="${BD2_DIR:-/opt/bd2/capture}"
N="${BD2_N:-1000}"
SEASON_TAG="${BD2_SEASON_TAG:-赛季49}"
PY="${PY:-python3.9}"
export BD2_LOGIN_FILE="${BD2_LOGIN_FILE:-batch_capture_s49.jsonl}"
# ★ 必须指定赛季号！不设就默认 48 = 【上赛季】的榜（分数 2441~3761，混进库就错了）
export BD2_SEASON="${BD2_SEASON:-49}"

cd "$CAP"
LOG="$CAP/logs/crawl_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$CAP/logs"

echo "===== 开始抓取 $(date '+%F %T') =====" | tee -a "$LOG"

# ① 拉排行榜（不覆盖已有抓包）
echo "① 拉排行榜" | tee -a "$LOG"
"$PY" -u _s47_fetch_rank.py "$N" 2>&1 | tee -a "$LOG"

# ② 生成 UID 队列
echo "② 生成队列" | tee -a "$LOG"
"$PY" - "$N" <<'PYEOF' 2>&1 | tee -a "$LOG"
import io, json, os, sys
H = os.path.dirname(os.path.abspath(__file__)) if '__file__' in dir() else os.getcwd()
H = os.environ.get('BD2_DIR', '/opt/bd2/capture')
cur = json.load(io.open(os.path.join(H, 'ranking_full_new.json'), encoding='utf-8'))
cur.sort(key=lambda x: -x['score'])
with io.open(os.path.join(H, 'uid_queue.txt'), 'w', encoding='utf-8', newline='') as f:
    for p in cur:
        f.write('%d\n' % p['uid'])
print('  写入 %d 个 UID' % len(cur))
PYEOF

# ③ 抓阵容（保留上一轮原始数据，方便追溯）
echo "③ 抓取阵容" | tee -a "$LOG"
[ -f "$CAP/piggy_raw.jsonl" ] && mv -f "$CAP/piggy_raw.jsonl" "$CAP/piggy_raw_prev.jsonl"
: > "$CAP/piggy_raw.jsonl"
"$PY" -u _fetch_all_now.py "$N" 2>&1 | tee -a "$LOG"

# ④ 生成报告
echo "④ 生成报告" | tee -a "$LOG"
"$PY" -u report_lineups.py 2>&1 | tail -n 5 | tee -a "$LOG"

# ⑤ 入库（同 UID 覆盖）
echo "⑤ 入库" | tee -a "$LOG"
"$PY" -u _archive_lineups.py "防守阵容_最新300名.txt" "$SEASON_TAG" "S49 $(date '+%m-%d %H:%M') 云端" 2>&1 | tail -n 5 | tee -a "$LOG"

# ⑥ 去重合并 → 阵容总库.jsonl
echo "⑥ 合并去重进总库" | tee -a "$LOG"
"$PY" -u _merge_pool.py 2>&1 | tail -n 5 | tee -a "$LOG"

# ⑦ 写清单（本地工具靠它判断要不要同步）
echo "⑦ 写清单" | tee -a "$LOG"
"$PY" - <<'PYEOF' 2>&1 | tee -a "$LOG"
import io, json, os, time
H = os.environ.get('BD2_DIR', '/opt/bd2/capture')
files = {}
for fn in ('阵容总库.jsonl', '阵容历史库.jsonl', 'ranking_full_new.json'):
    p = os.path.join(H, fn)
    if os.path.exists(p):
        st = os.stat(p)
        n = sum(1 for _ in io.open(p, encoding='utf-8', errors='replace'))
        files[fn] = {'bytes': st.st_size, 'lines': n,
                     'mtime': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st.st_mtime))}
man = {'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'files': files}
io.open(os.path.join(H, 'cloud_manifest.json'), 'w', encoding='utf-8', newline='').write(
    json.dumps(man, ensure_ascii=False, indent=1))
print('  清单: %s' % json.dumps(man, ensure_ascii=False))
PYEOF

echo "===== 完成 $(date '+%F %T') =====" | tee -a "$LOG"

# 只保留最近 50 个日志
ls -1t "$CAP"/logs/crawl_*.log 2>/dev/null | tail -n +51 | xargs -r rm -f
