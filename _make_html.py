# -*- coding: utf-8 -*-
"""生成阵容可视化 HTML（离线单文件，双击即可打开）
   数据全部从配置文件实时读取，不写死：
     阵容/站位/破度/爆发 ← 配置 json 的 team
     两套庇佑           ← 配置 json 的 bf / bs（点数从 bless_id_map 算）
     胜率               ← 配置 json 的 f(先攻) / b(后攻) / bs_score(精修后)
     规则               ← season_map.json（bd2cfg）
"""
import io, os, sys, json, datetime

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bd2cfg
import _zh

NM = json.load(io.open(os.path.join(HERE, 'name_map.json'), encoding='utf-8'))
COST = {(v['ch'], v['co']): v['cost'] for v in NM.values() if v.get('cost')}
BM = json.load(io.open(os.path.join(HERE, 'bless_id_map.json'), encoding='utf-8'))
PTS, BDESC = {}, {}
for _k, _v in BM.items():
    if isinstance(_v, dict) and _v.get('name'):
        PTS[_v['name']] = _v.get('cost') or _v.get('point') or 1
        BDESC[_v['name']] = _v.get('desc', '')

DB = json.load(io.open(os.path.join(HERE, 'chars_db.json'), encoding='utf-8'))
ATTR = {}
for c in DB:
    for x in (c.get('costumes') or []):
        ATTR[(c.get('character'), x.get('costumeName'))] = c.get('attribute')
ACOLOR = {'火': '#ff6b4a', '水': '#4aa8ff', '風': '#4ad991', '光': '#ffd84a', '暗': '#b06bff'}


def cost_color(c):
    return {50: '#ff4d6d', 45: '#ff9f43', 40: '#ffd166', 35: '#06d6a0', 30: '#4dabf7'}.get(c, '#888')


def load(fn):
    p = os.path.join(HERE, fn)
    if not os.path.exists(p):
        return None
    try:
        return json.load(io.open(p, encoding='utf-8'))
    except Exception:
        return None


def burst_of(ch, co):
    """爆发等级从 my_box 读"""
    try:
        box = load('my_box.json') or {}
        for k, v in box.items():
            if '·' in k:
                a, b = k.split('·', 1)
                if (a, b) == (ch, co):
                    return v.get('burst') or 0
    except Exception:
        pass
    return 0


def card(tag, title, cfg, accent, seg_label):
    if not cfg:
        return '<div class="card"><div class="card-head" style="border-color:%s">' \
               '<span class="tag" style="background:%s">%s</span><span class="cname">%s</span>' \
               '</div><div style="color:#6d7888;padding:20px">还没有这个分段的配置</div></div>' % (
                   accent, accent, tag, title)
    team = cfg.get('team') or []
    rows, cols = int(bd2cfg.rules().get('rows') or 5), int(bd2cfg.rules().get('cols') or 5)
    grid = [[None] * cols for _ in range(rows)]
    def _unpack(item):
        c, k, p = item[0], item[1], item[2]
        _brk = item[3] if len(item) > 3 else None
        _bst = item[4] if len(item) > 4 else None
        try:
            p = int(p)
        except Exception:
            p = 0
        if p < 0:
            p = 0
        return c, k, p, _brk, _bst

    for item in team:
        c, k, p, _brk, _bst = _unpack(item)
        if p // cols < rows:
            grid[p // cols][p % cols] = (c, k, _brk, _bst)
    tot = sum(COST.get((it[0], it[1]), 0) for it in team)
    r = bd2cfg.rules()
    forb = set(int(x) for x in (r.get('forbidden') or []))

    h = ['<div class="card">']
    h.append('<div class="card-head" style="border-color:%s"><span class="tag" style="background:%s">%s</span>'
             '<span class="cname">%s</span><span class="cost">%d 费 / %d</span></div>'
             % (accent, accent, tag, title, tot, int(r.get('max_cost') or 240)))
    h.append('<div class="gridwrap"><table class="grid">')
    h.append('<tr><th></th>' + ''.join('<th>%d列</th>' % (c + 1) for c in range(cols)) + '</tr>')
    for rr in range(rows):
        h.append('<tr><th>%d行</th>' % (rr + 1))
        for cc in range(cols):
            p = rr * cols + cc
            cell = grid[rr][cc]
            if p in forb:
                h.append('<td class="empty">禁</td>')
            elif not cell:
                h.append('<td class="empty">·</td>')
            else:
                ch, co, _brk, _bst = cell
                ccst = COST.get((ch, co), 0)
                at = ATTR.get((ch, co), '?')
                bs = _bst if _bst is not None else burst_of(ch, co)
                brk = _brk if _brk is not None else ''
                try:
                    _bn = int(str(brk).replace('+', '') or 0)
                except Exception:
                    _bn = 0
                h.append('<td class="unit" style="border-color:%s"><div class="uname">%s</div>'
                         '<div class="uco">%s</div><div class="umeta"><span style="color:%s">%s</span>'
                         '<span style="color:%s">%d费</span>'
                         '<span style="color:#ffd166">破%d</span>%s</div></td>'
                         % (cost_color(ccst), _zh.t2s(ch), _zh.t2s(co), ACOLOR.get(at, '#999'), at,
                            cost_color(ccst), ccst, _bn,
                            ('<span style="color:#b06bff">爆%d</span>' % bs) if bs else ''))
        h.append('</tr>')
    h.append('</table></div>')

    h.append('<div class="sec"><div class="sec-t">出手顺序</div><div class="order">')
    for i, item in enumerate(team):
        c, k, p, _b2, _s2 = _unpack(item)
        ccst = COST.get((c, k), 0)
        h.append('<span class="ochip" style="border-color:%s"><b>#%d</b> %s·%s <i>%d行%d列</i></span>'
                 % (cost_color(ccst), i + 1, _zh.t2s(c), _zh.t2s(k), p // cols + 1, p % cols + 1))
    h.append('</div></div>')

    for label, key, budget in (('先攻', 'bf', int(r.get('bless_first') or 6)),
                               ('后攻', 'bs', int(r.get('bless_second') or 8))):
        bl = cfg.get(key) or []
        pts = sum(PTS.get(x.lstrip('~'), 1) for x in bl)
        h.append('<div class="sec"><div class="sec-t">%s庇佑 <span class="pts">%d / %d 点</span></div>'
                 '<div class="bless">' % (label, pts, budget))
        for x in bl:
            nm = x.lstrip('~')
            h.append('<span class="bchip" title="%s"><b>%s</b><i>%d点</i></span>'
                     % (BDESC.get(nm, '').replace('"', '&quot;'), _zh.t2s(x), PTS.get(nm, 1)))
        h.append('</div></div>')

    f, b = cfg.get('f'), cfg.get('b')
    bss = cfg.get('bs_score')
    # 0 或负数视为未测（老配置里是 0）
    if not f or f <= 0:
        f = None
    if not b or b <= 0:
        b = None
    if not bss or bss <= 0:
        bss = None
    h.append('<div class="sec"><div class="sec-t">胜率 <span class="pts">%s</span></div>' % seg_label)
    if f is None and b is None and bss is None:
        h.append('<div class="pending">还没复核</div>')
    else:
        for lab, v, col in (('先攻', f, '#4dabf7'), ('后攻', bss if bss is not None else b, '#06d6a0')):
            if v is None:
                h.append('<div class="bar"><div class="bl">%s<em>未测</em></div></div>' % lab)
                continue
            h.append('<div class="bar"><div class="bl">%s</div><div class="bt">'
                     '<div class="bfill" style="width:%.1f%%;background:%s"></div>'
                     '<span class="bv">%.1f%%</span></div></div>' % (lab, v, col, v))
        vals = [v for v in (f, bss if bss is not None else b) if v is not None]
        if len(vals) == 2:
            h.append('<div class="bar"><div class="bl">综合</div><div class="bt">'
                     '<div class="bfill" style="width:%.1f%%;background:%s"></div>'
                     '<span class="bv">%.1f%%</span></div></div>'
                     % ((vals[0] + vals[1]) / 2, accent, (vals[0] + vals[1]) / 2))
    h.append('</div></div>')
    return '\n'.join(h)


STYLE = r"""*{scrollbar-width:thin;scrollbar-color:#3a4761 transparent}
::-webkit-scrollbar{width:9px;height:9px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:#33405a;border-radius:9px;border:2px solid transparent;
       background-clip:padding-box}
::-webkit-scrollbar-thumb:hover{background:#4a5c7d;background-clip:padding-box}
::-webkit-scrollbar-corner{background:transparent}

*{box-sizing:border-box}
body{margin:0;padding:24px;background:#0f1218;color:#e8ecf5;font-family:-apple-system,"Microsoft YaHei",sans-serif}
h1{font-size:22px;margin:0 0 4px}
.sub{color:#7d8899;font-size:13px;margin-bottom:20px;line-height:1.7}
.wrap{display:flex;gap:20px;flex-wrap:wrap;align-items:flex-start}
.card{background:#171c26;border:1px solid #232a38;border-radius:14px;padding:18px;width:580px}
.card-head{display:flex;align-items:center;gap:10px;padding-bottom:12px;margin-bottom:14px;border-bottom:2px solid #333}
.tag{color:#0f1218;font-weight:700;font-size:13px;padding:2px 9px;border-radius:6px}
.cname{font-size:16px;font-weight:600;flex:1}
.cost{color:#8b97a8;font-size:13px}
.gridwrap{overflow-x:auto}
table.grid{border-collapse:separate;border-spacing:6px;margin:0 auto}
table.grid th{color:#6d7888;font-size:11px;font-weight:400;padding:2px}
td{width:100px;height:68px;border-radius:9px;vertical-align:middle;text-align:center;background:#12161e;border:1px solid #232a38}
td.empty{color:#2a3140;background:transparent;border:1px dashed #232a38;font-size:13px}
td.unit{background:#1b2230;border:1.5px solid #444}
.uname{font-size:12px;font-weight:600;line-height:1.2}
.uco{font-size:12px;color:#b9c4d4;line-height:1.3}
.umeta{display:flex;justify-content:center;gap:5px;font-size:10px;margin-top:3px;flex-wrap:wrap}
.sec{margin-top:16px}
.sec-t{font-size:12px;color:#8b97a8;margin-bottom:7px;letter-spacing:.5px}
.pts{color:#5c6675}
.order{display:flex;flex-wrap:wrap;gap:6px}
.ochip{background:#12161e;border:1px solid #333;border-radius:7px;padding:4px 8px;font-size:11px}
.ochip b{color:#ffd166;margin-right:3px}
.ochip i{color:#6d7888;font-style:normal;margin-left:4px}
.bless{display:flex;flex-wrap:wrap;gap:6px}
.bchip{background:#1b2230;border:1px solid #2d3748;border-radius:7px;padding:4px 9px;font-size:11.5px}
.bchip i{color:#7d8899;font-style:normal;margin-left:5px;font-size:10px}
.bar{margin:9px 0}
.bl{font-size:12px;color:#b9c4d4;margin-bottom:4px;display:flex;justify-content:space-between}
.bl em{color:#6d7888;font-style:normal;font-size:11px}
.bt{position:relative;background:#12161e;border-radius:6px;height:22px;overflow:hidden}
.bfill{height:100%;border-radius:6px}
.bv{position:absolute;right:8px;top:2px;font-size:12px;font-weight:700;color:#fff}
.pending{color:#6d7888;font-size:12.5px}
.note{margin-top:22px;background:#171c26;border:1px solid #232a38;border-radius:12px;padding:16px;font-size:12.5px;color:#a8b3c4;line-height:1.85;max-width:1200px}
.note b{color:#e8ecf5}
"""

HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>BD2 黄金竞技场 S__SEASON__ 阵容</title>
<style>
*{scrollbar-width:thin;scrollbar-color:#3a4761 transparent}
::-webkit-scrollbar{width:9px;height:9px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:#33405a;border-radius:9px;border:2px solid transparent;
       background-clip:padding-box}
::-webkit-scrollbar-thumb:hover{background:#4a5c7d;background-clip:padding-box}
::-webkit-scrollbar-corner{background:transparent}
*{box-sizing:border-box}
body{margin:0;padding:24px;background:#0f1218;color:#e8ecf5;font-family:-apple-system,"Microsoft YaHei",sans-serif}
h1{font-size:22px;margin:0 0 4px}
.sub{color:#7d8899;font-size:13px;margin-bottom:20px;line-height:1.7}
.wrap{display:flex;gap:20px;flex-wrap:wrap;align-items:flex-start}
.card{background:#171c26;border:1px solid #232a38;border-radius:14px;padding:18px;width:580px}
.card-head{display:flex;align-items:center;gap:10px;padding-bottom:12px;margin-bottom:14px;border-bottom:2px solid #333}
.tag{color:#0f1218;font-weight:700;font-size:13px;padding:2px 9px;border-radius:6px}
.cname{font-size:16px;font-weight:600;flex:1}
.cost{color:#8b97a8;font-size:13px}
.gridwrap{overflow-x:auto}
table.grid{border-collapse:separate;border-spacing:6px;margin:0 auto}
table.grid th{color:#6d7888;font-size:11px;font-weight:400;padding:2px}
td{width:100px;height:68px;border-radius:9px;vertical-align:middle;text-align:center;background:#12161e;border:1px solid #232a38}
td.empty{color:#2a3140;background:transparent;border:1px dashed #232a38;font-size:13px}
td.unit{background:#1b2230;border:1.5px solid #444}
.uname{font-size:12px;font-weight:600;line-height:1.2}
.uco{font-size:12px;color:#b9c4d4;line-height:1.3}
.umeta{display:flex;justify-content:center;gap:5px;font-size:10px;margin-top:3px;flex-wrap:wrap}
.sec{margin-top:16px}
.sec-t{font-size:12px;color:#8b97a8;margin-bottom:7px;letter-spacing:.5px}
.pts{color:#5c6675}
.order{display:flex;flex-wrap:wrap;gap:6px}
.ochip{background:#12161e;border:1px solid #333;border-radius:7px;padding:4px 8px;font-size:11px}
.ochip b{color:#ffd166;margin-right:3px}
.ochip i{color:#6d7888;font-style:normal;margin-left:4px}
.bless{display:flex;flex-wrap:wrap;gap:6px}
.bchip{background:#1b2230;border:1px solid #2d3748;border-radius:7px;padding:4px 9px;font-size:11.5px}
.bchip i{color:#7d8899;font-style:normal;margin-left:5px;font-size:10px}
.bar{margin:9px 0}
.bl{font-size:12px;color:#b9c4d4;margin-bottom:4px;display:flex;justify-content:space-between}
.bl em{color:#6d7888;font-style:normal;font-size:11px}
.bt{position:relative;background:#12161e;border-radius:6px;height:22px;overflow:hidden}
.bfill{height:100%;border-radius:6px}
.bv{position:absolute;right:8px;top:2px;font-size:12px;font-weight:700;color:#fff}
.pending{color:#6d7888;font-size:12.5px}
.note{margin-top:22px;background:#171c26;border:1px solid #232a38;border-radius:12px;padding:16px;font-size:12.5px;color:#a8b3c4;line-height:1.85;max-width:1200px}
.note b{color:#e8ecf5}
</style></head><body>
<h1>BD2 黄金竞技场 · S__SEASON__ 阵容</h1>
<div class="sub">生成时间 __TIME__　｜　规则：__NU__人 / __MC__费 / 先攻 __BF__点 / 后攻 __BS__点 / 禁用格 __FORB__　｜　数据全部从配置文件实时读取</div>
<div class="wrap">
__CARDS__
</div>
<div class="note">
<b>说明</b><br>
· 站位格里的数字 = pos 值（pos = 行×__COLS__+列，0 开始）；标「禁」的是本赛季禁用格<br>
· 胜率来自配置里的复核结果（先攻 f / 后攻 bs_score）；显示「未测」说明还没用高 N 复核<br>
· 换阵容时【站位、出手顺序、两套庇佑】都要按这里重设，缺一不可<br>
· 模型口径：敌方必暴击 + 随机暴击；历史误差约 ±3~5 点
</div>
</body></html>"""


def seg_label(cfg):
    lo, hi = cfg.get('seg_lo'), cfg.get('seg_hi')
    if lo is None:
        lo = cfg.get('seg')
    if isinstance(lo, dict):
        ks = sorted(int(k) for k in lo if str(k).isdigit())
        return ('%d 分以上' % ks[0]) if ks else '未标注分段'
    if lo is None:
        return '未标注分段'
    if hi is None or int(hi) >= 99999:
        return '%d 分以上' % int(lo)
    return '%d-%d 分段' % (int(lo), int(hi))


def render_one(cfg, title='保存的阵容', subtitle=''):
    """渲染单套阵容成完整 HTML 页面（给控制台点击查看用）"""
    body = card('阵容', title, cfg, '#4dabf7', title)
    return ("""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>%s</title><style>%s</style></head><body>
<h1>%s</h1>
<div class="sub">%s</div>
<div class="wrap">%s</div>
</body></html>""" % (title, STYLE, title, subtitle, body))


def main():
    r = bd2cfg.rules()
    # ① 上次搜索结果（有就优先显示，标题用配置里记录的真实分段）
    last = load('_S49_LAST.json') or load('_S49_FAST.json')
    # ② 两套常驻配置
    A = load('_S49_2000.json')
    B = load('_S49_2300.json')

    # ★ 2026-11-06 用户要求: 可视化【只显示最新一套】，想看历史就点保存阵容留档
    cur = last or A or B
    cards = []
    if cur:
        cards.append(card('最新', seg_label(cur), cur, '#4dabf7', seg_label(cur)))
    else:
        cards.append(card('—', '还没有搜索结果', None, '#4dabf7', ''))
    forb = r.get('forbidden') or []
    out = (HTML
           .replace('__SEASON__', str(r.get('season')))
           .replace('__TIME__', datetime.datetime.now().strftime('%Y-%m-%d %H:%M'))
           .replace('__NU__', str(r.get('max_units')))
           .replace('__MC__', str(r.get('max_cost')))
           .replace('__BF__', str(r.get('bless_first')))
           .replace('__BS__', str(r.get('bless_second')))
           .replace('__FORB__', '、'.join('%d行%d列' % (int(x) // int(r.get('cols') or 5) + 1,
                                                       int(x) % int(r.get('cols') or 5) + 1) for x in forb))
           .replace('__COLS__', str(r.get('cols')))
           .replace('__CARDS__', '\n'.join(cards)))
    p = os.path.join(HERE, '阵容可视化.html')
    io.open(p, 'w', encoding='utf-8', newline='').write(out)
    print('已生成: %s (%.1f KB)' % (p, len(out.encode('utf-8')) / 1024.0))


if __name__ == '__main__':
    main()
