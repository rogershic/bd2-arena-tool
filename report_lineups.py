# -*- coding: utf-8 -*-
"""把 piggy_raw.jsonl 解密后的 RankDetail 还原成可读防守阵容报告"""
import json, base64, os, re, io, collections
import _data
from Crypto.Cipher import AES

import sys as _bd2sys
HERE = (os.environ.get('BD2_HOME') or
        (os.path.dirname(os.path.abspath(_bd2sys.executable))
         if getattr(_bd2sys, 'frozen', False)
         else os.path.dirname(os.path.abspath(__file__))))
def load_keys():
    """当前 key 优先, 其次是历史 key(换 key 后老数据仍要能解)"""
    ks = []
    p = os.path.join(HERE, 'current_userkey.txt')
    if os.path.exists(p):
        ks.append(open(p).read().strip().encode())
    h = os.path.join(HERE, 'userkey_history.txt')
    if os.path.exists(h):
        for ln in open(h):
            s = ln.strip()
            if len(s) == 32:
                b = s.encode()
                if b not in ks: ks.append(b)
    return ks

KEYS = load_keys()
KEY = KEYS[0]

def unpad(b):
    n = b[-1]
    return b[:-n] if 1 <= n <= 16 else b

def rv(b, i):
    v = 0; s = 0
    while i < len(b):
        x = b[i]; i += 1
        v |= (x & 0x7f) << s
        if not x & 0x80: return v, i
        s += 7
    return None, i

def parse(b):
    out = []; i = 0
    while i < len(b):
        tag, i = rv(b, i)
        if tag is None: break
        f, wt = tag >> 3, tag & 7
        if wt == 0:
            v, i = rv(b, i); out.append((f, 0, v))
        elif wt == 2:
            n, i = rv(b, i)
            if n is None: break          # ★ 截断的 proto 数据, 跳过
            out.append((f, 2, b[i:i+n])); i += n
        elif wt == 5:
            out.append((f, 5, b[i:i+4])); i += 4
        elif wt == 1:
            out.append((f, 1, b[i:i+8])); i += 8
        else:
            break
    return out

def d(entries):
    return {f: v for f, wt, v in entries if wt == 0}

COSTUME = {}
def load_costume():
    for fn in ('modding_all.txt', 'costume_id_map.txt'):
        p = os.path.join(HERE, fn)
        if not os.path.exists(p): continue
        for ln in open(p, encoding='utf-8', errors='replace'):
            m = re.search(r'char0*(\d+)\s+([^\t]+)\t([^\t\r\n]+)', ln)
            if m:
                COSTUME[int(m.group(1))] = (m.group(2).strip(), m.group(3).strip())
                continue
            parts = [x for x in ln.strip().replace('\t', ' ').split(' ') if x]
            if len(parts) >= 3 and parts[0].isdigit():
                COSTUME.setdefault(int(parts[0]), (parts[1], ' '.join(parts[2:])))
            elif len(parts) == 2 and parts[0].isdigit():
                COSTUME.setdefault(int(parts[0]), (parts[1], ''))

ROLE = {}
def load_role():
    p = _data.p('role_id_map.txt')
    if os.path.exists(p):
        for ln in open(p, encoding='utf-8', errors='replace'):
            parts = ln.strip().split('\t')
            if len(parts) >= 2 and parts[0].isdigit():
                ROLE[int(parts[0])] = parts[1].strip()

def name_of(cid):
    if cid in CN:
        return CN[cid]
    if cid in COSTUME:
        ch, co = COSTUME[cid]
        return ch, co
    rid = cid // 100
    for k, v in COSTUME.items():
        if k // 100 == rid:
            return v[0], ('id%d' % cid)
    if rid in ROLE: return ROLE[rid], ('id%d' % cid)
    return ('role%d' % rid), ('id%d' % cid)

def decrypt_rows():
    best = {}   # uid -> 最完整(pb 最大)的那条, 避免空/旧记录盖掉好记录
    for l in open(os.path.join(HERE, 'piggy_raw.jsonl'), encoding='utf-8'):
        r = json.loads(l)
        if not r.get('data'): continue
        ct = base64.b64decode(r['data'])
        pb = None
        # ★ 优先用每条数据自带的 key(2026-10-17 新抓取方案每条记录 key)
        klist = []
        if r.get('key') and len(r['key']) == 32:
            klist.append(r['key'].encode())
        klist += KEYS
        for k in klist:
            try:
                pt = unpad(AES.new(k, AES.MODE_CBC, iv=b'\x00'*16).decrypt(ct))
                try: cand = base64.b64decode(pt)
                except Exception: cand = pt
                if cand[:1] in (b'\x08', b'\x0a'):
                    pb = cand
                    break
            except Exception:
                continue
        if pb is None: continue
        u = r['uid']
        # ★ 新抓的覆盖旧的(后出现的记录覆盖先出现的), 反映玩家当前最新防守配置
        best[u] = pb
    return collections.OrderedDict(best)

CN = {}
NICK = {}
RANK = {}
GUILD = {}
BLESS = {}
def load_nick():
    """uid -> 昵称/名次/胜利分/公会 (来自排行榜 ColosseumRanking)"""
    # ★ 2026-10-22: 优先读 _s47_fetch_rank.py 产出的最新榜单（list 格式）
    pn = os.path.join(HERE, 'ranking_full_new.json')
    if os.path.exists(pn):
        try:
            arr = json.load(io.open(pn, encoding='utf-8'))
            if isinstance(arr, list):
                for v in arr:
                    ku = int(v['uid'])
                    NICK[ku] = v.get('name')
                    RANK[ku] = (v.get('rank'), v.get('score'))
                    GUILD[ku] = v.get('guild')
                return
        except Exception:
            pass
    p = os.path.join(HERE, 'ranking_full.json')
    if not os.path.exists(p):
        p = os.path.join(HERE, 'ranking_names.json')
    if os.path.exists(p):
        j = json.load(io.open(p, encoding='utf-8'))
        for k, v in j.items():
            ku = int(k)
            if isinstance(v, dict):
                NICK[ku] = v.get('name')
                RANK[ku] = (v.get('rank'), v.get('score'))
                GUILD[ku] = v.get('guild')
            else:
                NICK[ku] = v

def load_bless():
    """数字ID -> 庇佑中文名/类别/点数"""
    p = _data.p('bless_id_map.json')
    if os.path.exists(p):
        BLESS.update(json.load(io.open(p, encoding='utf-8')))

def varints(b):
    out = []; i = 0
    while i < len(b):
        v = 0; s = 0
        while i < len(b):
            x = b[i]; i += 1
            v |= (x & 0x7f) << s
            if not x & 0x80: break
            s += 7
        out.append(v)
    return out

def bless_text(ids):
    """把 ID 列表转成 '突袭准备(1) + 极限诅咒I(1) ...'; 推测的加 ~ 前缀"""
    parts = []
    for n in ids:
        b = BLESS.get(str(n))
        if b:
            nm = b.get('name') or '?'
            if not b.get('confirmed'):
                nm = '~' + nm          # 插值推测, 未经游戏内核对
            parts.append('%s(%s)' % (nm, b.get('cost') if b.get('cost') else '?'))
        else:
            parts.append('ID%d' % n)
    return ' + '.join(parts) if parts else '-'

def load_cn():
    """中文译名表: costumeId <TAB> 中文角色名 <TAB> 中文服装名"""
    p = _data.p('cn_map.txt')
    if os.path.exists(p):
        for ln in io.open(p, encoding='utf-8'):
            ln = ln.strip()
            if not ln or ln.startswith('#'): continue
            parts = ln.split('\t')
            if len(parts) >= 2 and parts[0].isdigit():
                CN[int(parts[0])] = (parts[1], parts[2] if len(parts) > 2 else '')

def render_grid(slots):
    """slots: list of (pos, label) —— 固定 5 行 5 列（5x5 战场）"""
    lines = []
    grid = {}
    for pos, lab in slots:
        grid[pos] = lab
    COLS, ROWS = 5, 4
    lines.append('        ' + ''.join(['%-13s' % ('第%d列' % (c + 1)) for c in range(COLS)]))
    for r in range(ROWS):
        row = ['%-13s' % grid.get(r * COLS + c, '·') for c in range(COLS)]
        lines.append('   第%d行 ' % (r + 1) + ''.join(row))
    return lines

def main():
    load_costume(); load_role(); load_cn(); load_nick(); load_bless()
    print('costume entries', len(COSTUME), 'role entries', len(ROLE))
    protos = decrypt_rows()
    # 只保留前 N 名 (uid_queue.txt 中的 UID)
    # 默认不再按 uid_queue.txt 过滤: 队列是旧赛季快照, 会挡住新点出来的防守者。
    # 需要按队列过滤时设 REPORT_QUEUE_FILTER=1
    qfile = os.path.join(HERE, 'uid_queue.txt')
    if os.path.exists(qfile) and os.environ.get('REPORT_QUEUE_FILTER', '0') == '1':
        qset = set(int(x) for x in io.open(qfile, encoding='utf-8').read().split())
        protos = {k: v for k, v in protos.items() if k in qset}
    protos = sorted(protos.items(), key=lambda kv: (RANK.get(kv[0], (99999, 0))[0], kv[0]))
    protos = collections.OrderedDict(protos)
    lines = []
    lines.append('=' * 78)
    lines.append('  黄金竞技场 防守阵容抓取结果 (本次会话)')
    lines.append('  方式: 搭游戏自身连接 piggyback -> ColosseumRankDetail')
    lines.append('  本次 UserKey: %s' % KEY.decode())
    lines.append('')
    lines.append('  字段说明 / 校准状态:')
    lines.append('    破度 = 服装 f3.3 (1~5, 对应界面右上角 +N)              [已确认]')
    lines.append('    爆发 = 服装 f3.10 (1/2/3, 对应左侧三瓣火, 缺值待校准)   [待校准]')
    lines.append('    潜能*= 服装 f3.8 节点数 (界面左下三个点的对应关系尚未   [待校准]')
    lines.append('           确认, 当前按字节数显示, 仅供参考)')
    lines.append('    站位图固定 5 行 5 列')
    lines.append('    名次/胜利分/公会 = 排行榜条目 f7.2 / f7.1 / f6.2 (已与游戏内截图逐名核对)')
    lines.append('=' * 78)
    for uid, pb in protos.items():
        top = parse(pb)
        info = d(top)
        f4s = [v for f, wt, v in top if f == 4 and wt == 2]
        slots = []; charmap = {}; costumemap = {}; slotitems = []
        for seg in f4s:
            for sf, swt, sv in parse(seg):
                if swt != 2: continue
                inner = parse(sv)
                dd = d(inner)
                if sf == 1:
                    slotitems.append(dd)
                elif sf == 2:
                    charmap[dd.get(1)] = dd        # 角色inven -> 角色信息(CP/等级/主服装)
                elif sf == 3:
                    costumemap[dd.get(1)] = inner  # 服装inven -> 完整服装条目(含破度/爆发/潜能)
        rows = []
        first_ids = []; second_ids = []
        for seg in f4s:
            for sf, swt, sv in parse(seg):
                if sf == 7 and swt == 2: first_ids = varints(sv)    # 先攻
                elif sf == 8 and swt == 2: second_ids = varints(sv) # 后攻
        for s in slotitems:
            cinfo = charmap.get(s.get(1)) or {}
            ce = costumemap.get(s.get(4))          # 槽位自带的服装条目(含破度/爆发/潜能)
            cdd = d(ce) if ce else {}
            cid = cdd.get(2) or cinfo.get(13)
            ch, co = name_of(cid) if cid else ('?', '?')
            cp = cinfo.get(3); lv = cinfo.get(4)
            # 破度 = f3.3 (+N), 爆发 = f3.10 (1/2/3 三瓣火), 潜能 = f3.8(字节类型, 需单独取)
            limit = cdd.get(3)
            burst = cdd.get(10)
            pot = None
            if ce:
                for xf, xwt, xv in ce:
                    if xf == 8 and xwt == 2:
                        pot = xv
                        break
            pot_n = ('%d点' % len(pot)) if pot else '-'
            rows.append({'pos': s.get(2), 'order': s.get(3), 'ch': ch, 'co': co,
                         'cp': cp, 'lv': lv, 'cid': cid,
                         'limit': limit, 'burst': burst, 'pot': pot_n})
        lines.append('')
        lines.append('-' * 78)
        rk = RANK.get(uid)
        lines.append('  UID %d%s    %s    %s    战绩 %s胜 / %s负    %d 人防守'
                     % (uid, ('  [%s]' % NICK[uid]) if uid in NICK else '',
                        ('名次#%-4s 胜利分%-5s' % (rk[0], rk[1])) if rk else '(不在榜内)        ',
                        ('[%s]' % GUILD[uid]) if uid in GUILD and GUILD[uid] else '',
                        info.get(2), info.get(3), len(rows)))
        def wpad(s, n):
            s = s or '-'
            return s + ' ' * max(1, n - sum(2 if ord(c) > 0x2000 else 1 for c in s))
        lines.append('  出手顺序   站位    ' + wpad('角色', 14) + wpad('服装', 18)
                     + 'CP      Lv    破度   爆发   潜能*')
        for r in sorted(rows, key=lambda x: (x['order'] or 99)):
            lim = ('+%s' % r['limit']) if r['limit'] is not None else '-'
            bu = ('Lv%s' % r['burst']) if r['burst'] is not None else '-'
            lines.append('    #%-6d pos%-4d %s %s %-7s %-5s %-6s %-6s %s'
                         % (r['order'] or 0, (r['pos'] if r['pos'] is not None else -1), wpad((r['ch'] or '').replace(' ', ''), 14), wpad((r['co'] or '').replace(' ', ''), 18),
                            r['cp'] or '-', r['lv'] or '-', lim, bu, r['pot']))
        g = render_grid([(r['pos'], '%s(%s)' % (r['ch'].split()[0], r['order'] or 0)) for r in rows])
        lines.append('  站位图 (5列):')
        lines += ['  ' + x for x in g]
        lines.append('  先攻庇佑: %s' % bless_text(first_ids))
        lines.append('  后攻庇佑: %s' % bless_text(second_ids))
    open(os.path.join(HERE, '防守阵容_最新300名.txt'), 'w', encoding='utf-8').write('\n'.join(lines))
    try:
        import sys
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    print('\n'.join(lines))

main()
