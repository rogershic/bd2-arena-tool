# -*- coding: utf-8 -*-
"""黄金竞技场 战斗模拟器 v2 —— 区分 先攻/后攻 两套庇佑"""
import json
import _data
import io, os, re, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import sys as _bd2sys
HERE = (os.environ.get('BD2_HOME') or
        (os.path.dirname(os.path.abspath(_bd2sys.executable))
         if getattr(_bd2sys, 'frozen', False)
         else os.path.dirname(os.path.abspath(__file__))))
db = json.load(io.open(_data.p('chars_db.json'), encoding='utf-8'))
# ★ 我的真实练度(破度/爆发), 见 my_box.json; 未配置的角色按满练(break=5, burst=3)算
try:
    # ★ 2026-10-21: 支持 MY_BOX_FILE 环境变量，方便切换大号/小号练度
    _box_file = os.environ.get('MY_BOX_FILE', 'my_box.json')
    MY_BOX = json.load(io.open(os.path.join(HERE, _box_file), encoding='utf-8'))
except Exception:
    MY_BOX = {}

# ★★ 2026-10-18 新增: my_burst.json —— 本账号各服装的爆发等级
#   (换账号只需改这个文件; 未列出的默认爆发 0)
MY_BURST = {}
MY_BREAK_DEFAULT = 5
try:
    _mb = json.load(io.open(os.path.join(HERE, 'my_burst.json'), encoding='utf-8'))
    for _nm in (_mb.get('爆发1') or []):
        MY_BURST[_nm.strip()] = 1
    for _nm in (_mb.get('爆发3') or []):
        MY_BURST[_nm.strip()] = 3
    if _mb.get('_破度') is not None:
        MY_BREAK_DEFAULT = int(_mb['_破度'])
except Exception:
    MY_BURST = {}

TRAD = {'恶作剧幽灵': '惡作劇幽靈', '战地医护兵': '戰地醫護兵', '回归偶像': '回歸偶像',
        '堕落之星': '墮落之星', '泳池派对': '泳池派對', '海边度假': '海邊度假',
        '梦中的新娘': '夢中的新娘', '苍蓝魔女': '蒼藍魔女', '代号S': '代號S',
        '魔法学校教授': '魔法學校教授', '天御鸟命': '天御鳥命', '白雷': '白雷', 'DJ': 'DJ',
        '死亡之夜': '死亡之夜', '忌妒之夜': '忌妒之夜', '代号O': '代號O', '爱丽丝': '愛麗絲',
        '杀人娃娃': '殺人娃娃', '使者': '使者', '魔兽学家': '魔獸學家',
        '和蔼的无情': '和藹的無情', '战场猛兽': '戰場猛獸', '钢铁君主': '鋼鐵君主',
        # ↓ 补齐(此前解析失败 → 含这些服装的防守被跳过)
        '无限宇宙之全一': '無限宇宙之全一', '无穷之锁': '無窮之鎖', '印鉴掠夺者': '印鑑掠奪者',
        '女仆代号C': '女僕代號C', '残破木乃伊': '殘破木乃伊', '海洋先锋': '海洋先鋒',
        '贯穿的魔弓': '貫穿的魔弓', '星光守护者': '星光守護者', '找回的命运': '找回的命運',
        '致命之眼': '致命之眼'}
CHAR_TRAD = {'葛兰西特': '葛蘭西特', '安洁莉卡': '安潔莉卡', '伊柯利普斯': '伊柯利普斯',
             '莎赫拉查德': '莎赫拉查德', '出云天花': '出雲天花', '尤里': '尤里', '贝那卡': '貝那卡',
             '马莫尼勒': '馬莫尼勒', '悠丝缇亚': '悠絲緹亞', '爱丽洁': '愛麗潔', '克蕾西亚': '克蕾西亞',
             '莱克莉斯': '萊克莉斯', '布莱德': '布萊德', '奥尔施塔因': '奧爾施塔因',
             '莱维亚': '萊維亞', '日影': '日影', '阿奇拉': '阿奇拉',
             # ↓ 补齐(此前这些角色解析失败, 导致含他们的防守被静默跳过)
             '山城恋': '山城戀', '羽前京香': '羽前京香', '卢班希亚': '盧班希亞',
             '露比雅': '露比雅', '涅肯达莉亚': '涅肯達莉亞', '艾尼尔': '艾尼爾',
             '提尔': '提爾', '神圣悠丝缇亚': '神聖悠絲緹亞'}

# ★ 补齐繁简映射: 之前报告里的简体名找不到对应繁体装扮 → 单位被静默丢弃
#   (实证: 19749254 KiraHezi 的 拉菲娜·钢铁引擎 解析失败 → 整个阵容被跳过, 从未参与胜率计算)
TRAD.update({
    '钢铁引擎': '鋼鐵引擎',
    '签名女王': '簽名女王',
    '虚无之星': '虛無之星',
    '启示之梦': '啓示之夢',
    '许多多': '許多多',
    '黑暗之王': '黑暗之王',
})
CHAR_TRAD.update({
    '拉菲娜': '拉菲娜',
    '米卡埃拉': '米卡埃拉',
    '达丽安': '達麗安',
})
HPM = float(os.environ.get('HP_MULT', '1'))   # ★ 全局生命倍率(校准用)
TITLE = {'生命力': 'HP', '攻擊力': 'ATK', '魔法力': 'MATK', '防禦力': 'DEF', '魔法抵抗': 'MR',
         '光屬性傷害': 'ADMG', '暗屬性傷害': 'ADMG', '火屬性傷害': 'ADMG',
         '水屬性傷害': 'ADMG', '風屬性傷害': 'ADMG', '致命率': 'CR', '致命傷害': 'CDMG'}

_ci = {}
for ch in db:
    for co in ch.get('costumes', []):
        _ci[(ch.get('character'), co.get('costumeName'))] = (ch, co)

KEY_ALIAS = {'MATK': 'ATK', 'MDEF': 'MR', 'MAGICATK': 'ATK', 'MAGICDEF': 'MR'}

def add(acc, k, v):
    """★ 修正: 键名若已带 % 且值也带 %, 不再拼成 'HP%%'
    ★ 关键: 'MATK%' 要先去掉 % 映射成 'ATK', 再加回 %, 否则 MATK% 和 ATK% 分成两个 key
       (海边度假 bonding MATK% 64% 存成 MATK%, 潜能 18.9% 存成 ATK%, atk 只读 ATK% → 漏 64%)
    """
    m = re.match(r'^([\d.]+)(%?)$', str(v).replace(',', ''))
    if m:
        is_pct = m.group(2) == '%'
        base = k.rstrip('%')                     # 先去掉 %
        base = KEY_ALIAS.get(base, base)         # 再映射 MATK→ATK 等
        key = base + ('%' if is_pct else '')
        acc[key] = acc.get(key, 0) + float(m.group(1))

try:
    _RANGE_T = json.load(io.open(_data.p('range_table.json'), encoding='utf-8'))
except Exception as _re_:
    _RANGE_T = {}
    import sys as _sys
    _sys.stderr.write('[警告] 缺少 range_table.json → 所有技能范围都会退化成"只打主目标"，'
                      '结果全错！请确认包装完整（%s）\n' % _re_)

# ★★ 2026-10-22: 简→繁 自动兜底（手工别名表收不全，如 鲁→魯、赛尔→賽爾、剑后→劍後）
#   顺序: 手工 TRAD/CHAR_TRAD → opencc s2t → 都不行才放弃
try:
    from opencc import OpenCC as _OpenCC
    _CC = _OpenCC('s2t')
except Exception:
    _CC = None
_S2T_CACHE = {}


_ZH_S2T = None


def _zh_s2t_table():
    """没有 opencc 时的兜底：用 _zh 的 繁→简 表反推出 简→繁 表"""
    global _ZH_S2T
    if _ZH_S2T is not None:
        return _ZH_S2T
    m = {}
    try:
        import _zh as _z
        for a, b in (_z._build() or {}).items():      # a=繁 b=简
            if a != b and b not in m:
                m[b] = a
    except Exception:
        pass
    _ZH_S2T = m
    return m


def _s2t(x):
    if not x:
        return x
    if x not in _S2T_CACHE:
        if _CC is not None:
            _S2T_CACHE[x] = _CC.convert(x)
        else:
            _m = _zh_s2t_table()
            _S2T_CACHE[x] = ''.join(_m.get(c, c) for c in x)
    return _S2T_CACHE[x]


# opencc 会把「后(queen)」误转成「後」、「托」误转成「託」→ 按实际库名纠正
_S2T_FIX = {'劍後': '劍后', '反烏託邦': '反烏托邦'}


def _s2t_fix(x):
    return _S2T_FIX.get(_s2t(x), _s2t(x))


def unit_stats(sc, sco, order, pos, brk=None, bst=None):
    # brk/bst: 外部传入的真实破度/爆发(防守方用抓到的值), 不传则回退 my_box.json / 满练
    # 潜能: 敌人一律按满17点算(留余量)
    hit = _ci.get((CHAR_TRAD.get(sc, sc), TRAD.get(sco, sco)))
    if not hit:
        # ★ 简繁自动兜底
        hit = (_ci.get((_s2t_fix(sc), _s2t_fix(sco)))
               or _ci.get((_s2t_fix(CHAR_TRAD.get(sc, sc)), _s2t_fix(TRAD.get(sco, sco))))
               or _ci.get((_s2t(sc), _s2t(sco))))
    if not hit:
        return None
    ch, co = hit
    # ★ 按 my_box.json 取该角色真实练度(默认满练)
    _cfg = MY_BOX.get('%s·%s' % (ch.get('character'), co.get('costumeName')), {}) or {}
    # ★ 破度: 本账号全服饰 +5, 但防守方会传入真实值
    _brk = int(brk) if brk is not None else int(_cfg.get('break', MY_BREAK_DEFAULT))
    # ★ 爆发优先级: 外部传入 > my_box.json > (USE_MY_BURST=1 时才用 my_burst.json) > 默认 3
    #   USE_MY_BURST 默认关闭 → 保持原有行为(满爆发估算)
    #   换账号时: 把新配置写入 my_burst.json, 并设 USE_MY_BURST=1
    # ★ 优先级: 外部传入 > USE_MY_BURST=1时用 my_burst.json > my_box.json > 默认
    if bst is not None:
        _bst = int(bst)
    elif os.environ.get('USE_MY_BURST', '0') == '1':
        # ★★ 2026-10-19 實測: 同一服裝名可能有多個角色 (例: 泳池派對 有安潔莉卡/悠絲縑2亞/拉德爾...)
        #   爆發等級是【角色+服裝】級別, 不能只看服裝名
        _cn = (co.get('costumeName') or '').strip()
        _ch = (ch.get('character') or '').strip()
        _bst = int(MY_BURST.get('%s·%s' % (_ch, _cn), MY_BURST.get(_cn, 0)))
    elif _cfg.get('burst') is not None:
        _bst = int(_cfg['burst'])
    else:
        # ★ 默认: 该服装【有爆发条目】就算满爆(3), 游戏没出爆发的算 0
        _bst = 3 if (co.get('burst') or []) else 0
    # ---- 技能范围掩码: 优先「潜能/爆发」的 Range 扩展, 否则用基础 range ----
    _rc = co.get('range') or ''
    for sp in (co.get('skillPotential') or []):
        if sp.get('type') == 'Range' and sp.get('value'):
            _rc = sp['value']
    for b in (co.get('burst') or [])[:_bst]:          # ★ 爆发「技能范围增加」(只算已解锁的等级)
        # ★★ 2026-10-22 修正: 部分服装的爆发本身就是一条 Range 记录
        #   形如 {"level":1,"spCost":1,"type":"Range","value":"fire_032"}（阿奇拉/艾尼爾/山城戀）
        #   旧代码只看 extraEffects → 这 3 件的爆发范围一直没生效
        if b.get('type') == 'Range' and b.get('value'):
            _rc = b['value']
        for ef in b.get('extraEffects') or []:
            if ef.get('type') == 'Range' and ef.get('value'):
                _rc = ef['value']
    _m = re.search(r'_(\w+)$', _rc)
    shape = _RANGE_T.get(_m.group(1) if _m else _rc, [[0, 0]])
    # ★★★ BURST_RANGE（2026-10-27）：burst 的 type="Range" 会切换 AOE 形状
    #   例 贯穿的魔弓 爆2 = "Range: dark_015" → 从 dark_054(4格) 变 dark_015(6格)
    #   旧实现完全忽略 → 爆2 看起来「没收益」，实际多覆盖 50% 面积
    for _b in (co.get('burst') or []):
        _blv = _b.get('level') or 0
        if _blv > (_bst or 0):
            continue
        if _b.get('type') != 'Range':
            continue
        _rv = str(_b.get('value') or '')
        _rm = re.search(r'(\d{3})', _rv)
        if _rm and _rm.group(1) in _RANGE_T:
            shape = _RANGE_T[_rm.group(1)]
    a = {}
    for s in (ch.get('evgraving') or []):          # 刻印: 全部计入
        add(a, s.get('key') or TITLE.get(s.get('type'), ''), s.get('value'))
    for s in (ch.get('awakening') or []):          # 觉醒
        k_ = s.get('key') or TITLE.get(s.get('type'), '')
        # ★★ 2026-10-18 用户实测纠正: 觉醒的攻击力% 【要计入面板】!
        #   小公主: (429+34)×(1+12%觉醒+15.6%永久+52%羈绊+80%收藏) = 1,202 = 面板 1,201 ✓
        #   (旧实现跳过 ATK% → 1,146，差 4.6%)
        add(a, k_, s.get('value'))
    # ★★ 2026-10-18 用户确认: 同角色【所有服装】的永久潜能都叠加
    #   (莎赫拉查德 4 件服装 各 +5.2% 魔法力 → +20.8%)
    # ★★ permanentStats(永久潛能): 同角色【所有服装都叠加】计入面板
    #   实证: 魔女 (385+34)×(1+52%羈绊+20.8%永久+12%觉醒+80%收藏) = 1,109.5 = 面板 ✓
    for _co2 in (ch.get('costumes') or []):
        for s in (_co2.get('permanentStats') or []):
            add(a, s.get('key') or '', s.get('value', ''))
    for s in (co.get('bondingStat') or []):
        k = s.get('key') or ''
        add(a, k, s.get('value', ''))
    # ★★ 2026-10-18 用户给出正确公式并实验证:
    #   (385+34) × (1 + 羈绊52% + 永久潛能20.8% + 觉醒12% + 收藏80%) = 1,109.5 = 面板 1,109 ✓
    #   (1638+243+154) × 1.8 = 3,663 = 面板 3,663 ✓
    #   ⇒ 【普通潛能(A~E 的属性节点)不计入面板】
    #   → 所以直接跳过整个 potential 属性部分
    # ★★★ 2026-10-21 用户明确答复（定案，不要再问、不要再改）:
    #   「潜能本来就不算啊…只算永久的，因为羁绊已经包括了不是永久的潜能了」
    #   ⇒ 潜能 A~E 属性节点【永远不计入】。原因：羁绊(bondingStat)里已经
    #     包含了「非永久潜能」那部分，再加一次就是重复计算。
    #   ⇒ 只有 【永久潛能 permanentStats】计入，且同角色所有服装叠加（见上方 148~150 行）
    #   实证: 苍蓝魔女 (385+34)×(1+52%羁绊+20.8%永久+12%觉醒+80%收藏) = 1,109.5 = 面板 1,109 ✅
    #   若误加潜能 A/B/D(+20.2%) → 1,194.2，比面板高 7.7% ❌
    #   开关只为排查用，正常必须保持 0。
    _SKIP_POT = os.environ.get('USE_POT_MAX', '0') != '1'
    for d in ([] if _SKIP_POT else (co.get('potential') or {}).get('details', {}).values()):
        k = TITLE.get((d.get('title') or '').strip())
        # ★ 实测: 潜能的「属性伤害/暴击率/暴击伤害/魔法抵抗」节点不计入面板
        #   (杀人娃娃 实战魔抗13.4%=绑定MDEF, 不含潜能MR 2.5%+4.2%; 2026-10-17 实证)
        if k in ('ADMG', 'CR', 'CDMG', 'MR'):
            continue
        if k:
            m = re.search(r'([\d.]+)%', d.get('value') or '')
            if m:
                add(a, k, m.group(1) + '%')       # 百分比节点
            else:
                m2 = re.search(r'增加\s*([\d.]+)', d.get('value') or '')
                if m2:
                    add(a, k, m2.group(1))        # 固定值节点(如 魔法力+11/+18)
    # ★ 修正: 致命率/致命伤害/属性伤害 的数值本身是"百分比数字", 不能存成 CR%/CDMG%/ADMG%
    for k in ('ADMG', 'CR', 'CDMG'):
        if k + '%' in a:
            a[k] = a.get(k, 0) + a.pop(k + '%')
    # ---- 收藏集(全账号通用, 非装备): 攻击力/魔法力/生命力 +80%, 暴击率 +50% ----
    a['ATK%'] = a.get('ATK%', 0) + 80
    a['HP%'] = a.get('HP%', 0) + 80
    a['CR'] = a.get('CR', 0) + 50
    # ★ 无通用隐藏加成(2026-10-17 双面板实证):
    #   无诅咒 暴伤=650(=50白值+溢出100×6), 有诅咒I 暴伤=440(=50+溢出65×6)
    #   ⇒ 面板上的 +390 绿字 = 被极限诅咒压制后的暴击溢出转化, 不是固定加成
    #   ⇒ 暴击率面板显示上限 100%(真实 165/200 都显示 100)
    ml = ch.get('maxlevel') or {}
    # ★ 三形态实测对比后取 A(最吻合): 白值×(1+全部%) + 固定值×(1+收藏集80%)
    #   (葛兰西特·恶作剧幽灵 生命 14123/游戏14128, 攻击 299/游戏298 → 全项吻合)
    # ★★ 2026-10-18 用户实证修正乘区结构:
    #   面板 = (白值 + 刻印固定 + 羈绊固定) × (1 + 百分比总和)
    #   实证: 魔女 (385+34)×(1+84.2%+80%) = 419×2.642 = 1,107  vs 面板 1,109
    COLL = 1 + 80 / 100.0
    atk = (float(ml.get('atk') or 0) + a.get('ATK', 0)) * (1 + a.get('ATK%', 0) / 100)
    # ★ 黄金竞技场【无装备】→ 不得乘装备系数(旧 ATK_MULT=1.45 导致魔法力虚高32%)
    #   (2026-10-17 面板校准: 出云天花魔法力 模型1130 vs 实战853, 去掉×1.45后 = 779+潜能补正≈853)
    atk *= float(os.environ.get('ATK_MULT', '1.0'))
    hp = (float(ml.get('hp') or 0) + a.get('HP', 0)) * (1 + a.get('HP%', 0) / 100)
    # ★★ 2026-10-18 用户确认: 游戏面板是【向下取整】(不是四舍五入)
    #   1,109.5 → 面板 1,109;  298.8 → 面板 298
    atk = float(int(atk))
    hp = float(int(hp))
    # ★ 2026-10-22: chars_db 里 艾瑞克/傑登/艾瑪/比阿特麗絲 的 maxlevel 是 cr=0 cdmg=0 def=0 mr=0
    #   (数据抽取缺失)。暴伤白值在 BD2 里是【全角色恒定 50】，缺了就补 50。
    #   暴击率白值通常是 10（少数 20），这里缺失时补 10 并在返回值里打标记 _cr_missing
    _cr_raw = ml.get('cr')
    _cr_missing = (not _cr_raw) or float(_cr_raw) == 0
    cr = float(_cr_raw or 0) + a.get('CR', 0)
    if _cr_missing:
        cr += 10.0
    cdmg = (float(ml.get('cdmg') or 0) or 50.0) + a.get('CDMG', 0)
    # ★★ 2026-10-22 用户纠正: 暴击率【不能取整】, 游戏面板是带小数的
    #   旧实现 float(int(cr)) 会把 74.6% 截成 74%, 导致全表小数位都是 0
    #   例: 露比雅·女僕比基尼 = 白值20 + 羁绊4.6% + 收藏50 = 74.6%
    cr = round(cr, 2)
    # ★★ 2026-10-18 新增: my_box.json 可直接覆盖面板值
    #   (游戏面板 = 白值 + 刻印 + 潜能 + 羁绊 + 收藏 + 其他服装的永久潜能 …… 推算容易差几个点)
    #   用法: "role·costume": {"atk": 1109, "hp": 3663, "cr": 60, "cdmg": 97.2}
    _ov = MY_BOX.get('%s·%s' % (ch.get('character'), co.get('costumeName')))
    if _ov is None:
        _ov = MY_BOX.get('%s·%s' % (ch.get('enName'), co.get('costumeName')))
    # ★★ 2026-10-22 修 bug: 原来 _pres_override 只在 isinstance(_ov, dict) 里赋值，
    #   服装不在 my_box.json 时（例如新出的服装、或对手用的其它服装）会
    #   UnboundLocalError: local variable '_pres_override' referenced before assignment
    _pres_override = None
    if isinstance(_ov, dict):
        if _ov.get('atk') is not None:
            atk = float(_ov['atk'])
        if _ov.get('hp') is not None:
            hp = float(_ov['hp'])
        if _ov.get('cr') is not None:
            cr = float(_ov['cr'])
        if _ov.get('cdmg') is not None:
            cdmg = float(_ov['cdmg'])
        # ★ 2026-10-22 用户说明: 属性抵抗【每个服饰不同】，且要保留小数
        #   chars_db 里没有这个字段 → 支持在 my_box.json 里用 "pres" 覆盖
        #   未提供时回退到「水/火/風 = 50, 其他 = 0」的旧规则
        if _ov.get('pres') is not None:
            _pres_override = float(_ov['pres'])
        else:
            _pres_override = None
    txt = ''.join(co.get('skill') or [])
    lv = co.get('level') or []
    last = dict(lv[min(_brk, len(lv) - 1)]) if lv else {}   # ★ 按真实破度取等级表行(原为 lv[-1] 满破)
    # ★ HIT\d 也要收进来: 爆发的「攻擊次數+1」目标是 HIT1, 不收的话加不上(堕落之星 2段→1段)
    vals = {k: float(v) for k, v in last.items()
            if re.match(r'(VALUE|HIT)\d', k) and str(v).replace('.', '').isdigit()}
    for sp in co.get('skillPotential') or []:
        for sw in sp.get('switches') or []:
            if sw.get('target') in vals and isinstance(sw.get('value'), (int, float)):
                vals[sw['target']] += sw['value']
    # ★ 爆发(Burst): 每级「伤害量+80%」也加到 VALUE 上(满级3级 = +240%)
    #   只累加【已解锁】的等级 —— 没爆发的角色不能白嫖这 240%
    #   ★ burst 文本里的「屬性傷害增加100%」是【点了爆发才生效的4回合临时buff】,
    #     不进面板(2026-10-17 面板实证: 光属性伤害80%=基础50+绑定30, 无burst加成) → 不解析
    # ★★ 2026-10-18 用户给出正确公式: 1109×5.8×(1-0.454) = 3512 = 实战 3511✓
    #   → 爆发的 Fire 類(傷害量+X%)【确实计入倍率】(魔女 280+240+60 = 580%)
    for b in (co.get('burst') or [])[:_bst]:
        for sw in (b.get('switches') or []):
            if sw.get('target') in vals and isinstance(sw.get('value'), (int, float)):
                vals[sw['target']] += sw['value']
    hits, per, basis = 1, 100.0, '自身攻擊力'
    # ★★★ 2026-10-27 修正(用户指出): 纯增益技能没有伤害句 → 不应造成伤害
    #   例 悠絲緹亞·泳池派對「自身在成功迴避7次前100%迴避。12回合期間攻擊力增加300%」
    #      技能本身没有「造成…傷害」→ 施放该技能的那一回合伤害应为 0
    #   旧实现默认 per=100% → 所有纯辅助(顶尖偶像/小红帽/泳池派對)被算成普通攻击
    _has_dmg = False
    for seg in txt.split('。'):
        # ★ 伤害句不一定要写「攻擊敵人」: 例 葛兰西特·战地医护兵
        #   「對敵人造成相當於自身最大生命力{VALUE1}%的物理傷害」就没有这四个字,
        #   旧条件会整段跳过 → 退回默认(自身攻击力×100%), 伤害差几十倍。
        # ★★ 2026-10-22 放宽: 伤害句可能用【字面百分比】而非 {VALUE}
        #   例 奧爾施塔因·青雲道士「造成相當於自身魔法力25%的魔法傷害」(没有 {VALUE})
        #   旧条件要求 {'{VALUE'} → 整段跳过 → per=100%、段数=1，完全错
        if '傷害' in seg and '造成' in seg:
            # ★★ 2026-10-17 修正: 只认「造成…傷害」的真正傷害句
            #   旧条件只要含「攻擊」就算 → 「自身攻擊力增加…連鎖傷害增加{VALUE3}%」
            #   这类增益句被当成傷害句 → 海洋先鋒被算成 1段×20%
            #   (實際是 8段×90%, 差 36 倍!)
            if ('連鎖傷害' in seg or '傷害增加' in seg or '傷害減少' in seg
                    or '攻擊力增加' in seg):
                continue
            # ★★ 2026-10-17 修正: 【反击句】不能当成本体的 per!
            #   例 布莱德·使者: 「每次反擊時，對全體敵人造成相當於自身攻擊力{VALUE1}%的物理傷害。」
            #                    「對敵人造成相當於自身攻擊力{VALUE3}%的物理傷害。」(本体)
            #   旧实现取第一句 → per=VALUE1(反击200%), 实际本体是 VALUE3(700%), 少算 3.5 倍!
            #   (实战: 使者单次 7000/40000 vs 模型 3041/8362)
            if '反擊' in seg or '反击' in seg:
                continue
            _has_dmg = True
            # ★ 段数可能是占位符 {HIT1}(如 安洁莉卡·堕落之星「攻擊敵人{HIT1}次」)。
            #   旧实现只认「攻擊敵人(\d+)次」→ 匹配失败会整个跳过,
            #   导致 basis/per 退回默认(自身攻击力×100%), 伤害差 8 倍以上。
            mh = re.search(r'攻擊敵人(\d+)次', seg)
            if mh:
                hits = int(mh.group(1))
            else:
                mh2 = re.search(r'\{HIT(\d)\}', seg)
                hits = int(vals['HIT' + mh2.group(1)]) if (mh2 and vals.get('HIT' + mh2.group(1)) is not None) else 1
            mv = re.search(r'\{VALUE(\d)\}%', seg)
            _got = False
            if mv and vals.get('VALUE' + mv.group(1)) is not None:
                per = vals['VALUE' + mv.group(1)]
                _got = True
            elif '{VALUE' not in seg:
                # ★ 字面百分比: 「造成相當於自身魔法力25%的魔法傷害」
                _ml = re.search(r'([\d.]+)%的[^，。]{0,6}傷害', seg)
                if _ml:
                    per = float(_ml.group(1))
                    _got = True
            if _got:
                basis = ('自身最大HP' if '自身最大生命力' in seg else '敵人最大HP' if '敵人最大生命-力' in seg else
                         '敵人最大HP' if '敵人最大生命力' in seg else '自身魔法力' if '自身魔法力' in seg
                         else '敵人魔法力' if '敵人魔法力' in seg else '自身攻擊力')
                break
    # ★★ 2026-10-22 新增【条件倍率】: 「若敵人為物理/魔法類型，則變為造成…{VALUEn}%」
    #   用户确认: 这里的「类型」= 敌人的【攻击类型】(atkType: 物/魔)，不是元素属性
    #   例 納羅達斯·無名道士 Lv6: 普通 VALUE1=450%，敌人是物理型 → VALUE2=850%(+潜力200=1050%)
    #   旧实现只看第一个伤害句就 break → 永远用 VALUE1，少算一半
    cond_per_value = None
    cond_per_type = None
    for seg in txt.split('。'):
        if ('若敵人為' in seg or '如果敵人是' in seg or '若敌人为' in seg) and '{VALUE' in seg and '傷害' in seg:
            _mk = '物' if '物理' in seg else ('魔' if '魔法' in seg else None)
            _mv = re.search(r'\{VALUE(\d)\}%', seg)
            if _mk and _mv and vals.get('VALUE' + _mv.group(1)) is not None:
                cond_per_value = vals['VALUE' + _mv.group(1)]
                cond_per_type = _mk
                break
    # ★★ 2026-10-22 新增【减攻击力/魔法力】: 按【百分比】降低对方输出
    #   用户确认(两次):
    #     ① 减物抗/减魔抗 = 减法(点数); 减攻击力/魔法力 = 百分比(乘法)
    #        例: 攻击力1000 被减70% → 减掉700 → 剩300
    #     ② 「技能范围内可能同时有物理型角色和魔法型角色，要分开计算」
    #        → 物理型目标吃【攻击力减少 VALUE1%】
    #        → 魔法型目标吃【魔法力减少 VALUE2%】
    #   例 青雲道士: 攻擊力減少{VALUE1}=70%  /  若敵人為魔法類型 → 魔法力減少{VALUE2}=70%
    #      西利亞·詛咒之星: 只有攻擊力減少{VALUE2}=65%(魔法型目标不吃)
    #      君特·盧戈獵人 / 雷南特·戰鬥醫師: 攻擊力減少50%(字面)
    atk_down_phys, atk_down_mag, atk_down_turns = 0.0, 0.0, 0
    for seg in txt.split('。'):
        if '敵人' not in seg and '敌人' not in seg:
            continue
        _is_mag = bool(re.search(r'魔法力\s*減少', seg))
        _is_phy = bool(re.search(r'攻擊力\s*減少', seg))
        if not (_is_mag or _is_phy):
            continue
        _pct_ad = None
        _mv_ad = re.search(r'\{VALUE(\d)\}%', seg)
        if _mv_ad and vals.get('VALUE' + _mv_ad.group(1)) is not None:
            _pct_ad = vals['VALUE' + _mv_ad.group(1)]
        else:
            _ml_ad = re.search(r'減少\s*([\d.]+)%', seg)
            if _ml_ad:
                _pct_ad = float(_ml_ad.group(1))
        if _pct_ad is None:
            continue
        # 魔法力那条语句里也可能出现「攻擊力」字样，用 _is_mag 优先区分
        if _is_mag:
            atk_down_mag = max(atk_down_mag, _pct_ad)
        else:
            atk_down_phys = max(atk_down_phys, _pct_ad)
        _mt_ad = re.search(r'(?:\{VALUE(\d)\}|(\d+))\s*回合期間', seg)
        if _mt_ad:
            if _mt_ad.group(1) and vals.get('VALUE' + _mt_ad.group(1)) is not None:
                atk_down_turns = max(atk_down_turns, int(vals['VALUE' + _mt_ad.group(1)]))
            elif _mt_ad.group(2):
                atk_down_turns = max(atk_down_turns, int(_mt_ad.group(2)))
    # ★★ 2026-10-22 新增【每命中一个目标增伤】: 范围内每多 1 个目标，全体 +X%
    #   用户确认: 无上限，且是【加在倍率上】(加法不是乘区)
    #   例 罗安·名人兔女郎「對敵人造成…50%的魔法傷害。每命中一個目標，傷害量增加{VALUE1}%」
    #      → 打到 N 个目标时 per = 50 + VALUE1 × (N-1)
    per_per_target, per_target_mode = 0.0, 'each'
    for seg in txt.split('。'):
        _is_pt = ('每多一個目標' in seg or '每多一个目标' in seg
                  or '每有一個目標' in seg or '每有一个目标' in seg
                  or '每命中一個目標' in seg or '每命中一个目标' in seg)
        if not _is_pt or '增加' not in seg:
            continue
        _mv_pp = re.search(r'\{VALUE(\d)\}%', seg)
        if _mv_pp and vals.get('VALUE' + _mv_pp.group(1)) is not None:
            per_per_target = vals['VALUE' + _mv_pp.group(1)]
        else:
            _ml_pp = re.search(r'增加\s*\+?\s*([\d.]+)%', seg)
            if _ml_pp:
                per_per_target = float(_ml_pp.group(1))
        # ★ 「每多一个」= 第一个不算(N-1)；「每有一个/每命中一个」= 第一个也算(N)
        per_target_mode = 'extra' if ('每多' in seg) else 'each'
        break
    # ★ 技能自带的 自身/我军 增益(无CD环境=常驻), 例: 死亡之夜「6回合自身暴伤+280%」
    team_buff = []; self_buff = []; sb_hit_buff = []   # ★ sb_hit_buff = 「受到攻擊時」条件触发
    # ★ 2026-10-23 已回滚: 「每次攻擊的技能傷害增加N%」其实是【加到 VALUE1】上，
    #   引擎的 switches 机制早就处理了（苍蓝280→580 / 恶灵6%→8% / 教授75→90 / 死亡之夜13→14）
    #   不能额外再做逐段递增，否则双重计算
    per_hit_grow = 0.0
    # ★★★ 2026-10-22 新增: 自身增益的【最大叠加层数】(白雷「最多可賦予疊加至2」)
    sb_stack_max = 1
    _ms = re.search(r'最多可[賦赋]予疊加至(\d+)', txt)
    if _ms:
        sb_stack_max = max(1, int(_ms.group(1)))
    for seg in txt.split('。'):
        if '增加' not in seg or '期間' not in seg:
            continue
        mv = re.search(r'增加(?:相當於[^，。]{0,14})?\{VALUE(\d)\}%', seg)
        if mv:
            val = vals.get('VALUE' + mv.group(1))
        else:
            mv = re.search(r'增加([\d.]+)%', seg)
            val = float(mv.group(1)) if mv else None
        if val is None:
            continue
        # ★★★ CHAIN_DMG_NOT_ATK (2026-10-27 用户给技能截图 + 实战核对):
        #   卢班希亚·海洋先锋「对自身应用造成的【连携伤害】增加20%的效果」
        #   → 这是「连携伤害」不是「攻击力」，旧实现整段含「增加20%」+「攻击力」（前半句有）
        #   → 被误判成 ATK% +20%，导致 8 段伤害虚高 20%
        #   实证: 游戏面板每段 3,822（=ATK×125%），真实8段合计 79,729
        #         模型算出 89,458（+17%），多出的正是这个 20%
        if (('連鎖' in seg or '连锁' in seg or '連攜' in seg or '连携' in seg)
                and ('傷害' in seg or '伤害' in seg)):
            continue
        #   另外「攻擊力增加疊加數達N或以上時」这类【条件触发】也不能在第1层就生效
        if re.search(r'[疊叠]加數達|叠加数达|達\s*\d+\s*或以|达\s*\d+\s*或以', seg):
            continue
        # ★★★ 2026-11-04 修正(用户指出): 必須区分【攻擊力】和【魔法力】
        #   「我軍攻擊力增加X%」只加强物理伤害单位，魔法角色吃不到（反之亦然）
        #   旧实现两者都记成 ATK%，而 KEY_ALIAS 又把 MATK 映射成 ATK
        #   → 增攻会同时加强魔法角色的魔攻（例 霍爾蒙克斯 +280% 让 DJ/致命之眼 全部虚高）
        tag = ('MATK%' if ('魔法力' in seg and '攻擊力' not in seg and '攻击力' not in seg) else
               'ATK%' if ('攻擊力' in seg or '攻击力' in seg) else
               'CDMG' if '致命傷害' in seg else
               'CR' if '致命率' in seg else
               'ADMG' if '屬性傷害' in seg else
               'HP%' if '最大生命力' in seg else None)
        # ★ 「致命伤害增加」: 只有【变身】类(死亡之夜)不常驻面板;
        #   普通「致命伤害增加」(医护兵 爆伤440+200=640) 是常驻的
        #   (2026-10-17 实战: 死亡之夜变身+280%不生效, 医护兵+200%生效)
        # ★ 2026-10-21 修正: 变身类的暴伤【不再跳过】
        #   用户确认死亡之夜暴伤是【前置】（文本第②句在伤害句③之前）→ 8段全吃 +300%
        #   （旧实现跳过 → 少算 2.38 倍，已作废）
        # if tag == 'CDMG' and ('變身' in txt or '变身' in txt):
        #     continue
        if not tag:
            continue
        if '我軍' in seg or '我军' in seg:
            team_buff.append((tag, val))
        elif ('受到攻擊時' in seg or '受到攻击时' in seg
              or '受到傷害時' in seg or '受到伤害时' in seg):
            # ★★★ 2026-10-27 用户指出 + 实战验证:
            #   阿奇拉·戰場猛獸「4回合內，【自身受到攻擊時】，為自己附加攻擊力+30%」
            #   → 必须【本回合先被打】才触发，不是出手时无条件加
            #   实证：夜神一 3017 分局，战场猛兽@pos15 未被攻击，面板攻击力 2452（无+30%）
            #        技能面板 (14712) = 2452×600% 印证
            sb_hit_buff.append((tag, val))
        else:
            self_buff.append((tag, val))

    # 技能护盾(能量防卫): 必须"套用/获得"才算给盾(排除"相当于持有护盾%的伤害"这类引用)
    # ★★ 2026-10-22: 「對我軍套用能量防衛」= 给全体友军 (例 魯·小紅帽)
    shield_allies = False
    shield_pct, shield_basis, shield_turns = 0.0, 'HP', 0
    # ★★★ SHIELD_BURST_SCAN (2026-10-27): 护盾可能写在【爆发的追加能力】里
    #   例 阿奇拉·戰場猛獸 burst Lv3: "[追加能力] 4回合期間，套用攻擊力200%的能量防衛效果"
    #   → 旧实现只扫本体 txt → 完全漏掉这个护盾
    _shield_txt = txt + '。' + '。'.join(
        (b.get('value') or '') for b in (co.get('burst') or [])[:_bst])
    for seg in _shield_txt.split('。'):
        if not ('能量防衛' in seg or '能量防卫' in seg or '護盾' in seg or '护盾' in seg):
            continue
        # ★★★ SHIELD_EXTRA (2026-10-27): 原文可能用「施加」而不是「套用/獲得」
        #   例 阿奇拉·戰場猛獸【額外能力】「為自己施加相當於攻擊力200%的能量護盾，持續4回合」
        #   旧条件只认 套用/獲得 → 这段完全被跳过 → 战场猛兽没有护盾（漏算）
        if not ('套用' in seg or '獲得' in seg or '获得' in seg or '施加' in seg
                or '应用' in seg or '應用' in seg):
            continue
        mv = re.search(r'\{VALUE(\d)\}%', seg)
        _lit = None
        if not (mv and vals.get('VALUE' + mv.group(1)) is not None):
            # ★ 支持字面百分比：「相當於攻擊力200%的能量護盾」
            _lm = re.search(r'(?:攻擊力|魔法力|最大生命力)\s*(\d+(?:\.\d+)?)%', seg)
            if _lm:
                _lit = float(_lm.group(1))
        if mv and vals.get('VALUE' + mv.group(1)) is not None:
            shield_pct = vals['VALUE' + mv.group(1)]
            shield_basis = ('ATK' if '攻擊力' in seg or '攻击力' in seg else
                            'MAG' if '魔法力' in seg else 'HP')
            mt1 = re.search(r'(\d+)回合內', seg)
            mt2 = re.search(r'(\d+)回合期間', seg)
            mt3 = re.search(r'持續(\d+)回合', seg)
            if mt1: shield_turns = int(mt1.group(1))
            elif mt2: shield_turns = int(mt2.group(1))
            elif mt3: shield_turns = int(mt3.group(1))
            if '我軍' in seg or '我军' in seg:
                shield_allies = True
            break
        elif _lit is not None:
            shield_pct = _lit
            shield_basis = ('ATK' if '攻擊力' in seg or '攻击力' in seg else
                            'MAG' if '魔法力' in seg else 'HP')
            mt1 = re.search(r'(\d+)回合內', seg)
            mt2 = re.search(r'(\d+)回合期間', seg)
            mt3 = re.search(r'持續(\d+)回合', seg)
            if mt1: shield_turns = int(mt1.group(1))
            elif mt2: shield_turns = int(mt2.group(1))
            elif mt3: shield_turns = int(mt3.group(1))
            if '我軍' in seg or '我军' in seg:
                shield_allies = True
            break
        if mv and vals.get('VALUE' + mv.group(1)) is not None:
            shield_pct = vals['VALUE' + mv.group(1)]
            shield_basis = ('ATK' if '攻擊力' in seg or '攻击力' in seg else
                            'MAG' if '魔法力' in seg else 'HP')
            # ★ 技能护盾也有回合数: 「2回合內…能量護盾」/「4回合期間…能量防衛」
            mt1 = re.search(r'(\d+)回合內', seg)
            mt2 = re.search(r'(\d+)回合期間', seg)
            if mt1:
                shield_turns = int(mt1.group(1))
            elif mt2:
                shield_turns = int(mt2.group(1))
            if '我軍' in seg or '我军' in seg:
                shield_allies = True
            break
    # ★★★ 2026-11-04 修正: 护盾回合数可能写成占位符 {VALUE2}回合期間
    #   例 拉德爾·暗黑騎士「{VALUE2}回合期間…能量防衛」→ 旧实现只认字面数字 → shield_turns=0
    if shield_pct and not shield_turns:
        _mtp = re.search(r'\{VALUE(\d)\}回合', _shield_txt)
        if _mtp and vals.get('VALUE' + _mtp.group(1)) is not None:
            shield_turns = int(vals['VALUE' + _mtp.group(1)])
    # ★ 护盾转伤害: 「此時額外造成相當於自身持有的能量防衛{VALUE2}%的物理傷害」
    #   (惡作劇幽靈等: 每段伤害额外 + 当前护盾值×X%)
    shield_dmg_pct = 0.0
    for seg in txt.split('。'):
        if '額外' in seg and '能量防衛' in seg:
            mv = re.search(r'\{VALUE(\d)\}%', seg)
            if mv and vals.get('VALUE' + mv.group(1)) is not None:
                shield_dmg_pct = vals['VALUE' + mv.group(1)]
            break
    # ★ 服装自带嘲讽(挑釁): 如 葛兰西特·回归偶像「2回合期間，對自身套用挑釁效果」
    #   生效期间敌方全体被强制打他(无视对位检索), 他死了效果消失
    taunt_n = 0
    # ★★★ TAUNT_POT (2026-10-27): 潜能里的「4回合挑釁」是字面数字、无「期間」
    #   例 賽爾·惡魔之女 skillPotential: {"type":"Plus","value":"4回合挑釁"}
    #   → 旧解析只认 {VALUEn}回合期間 → 完全漏掉 → 坦克没有嘲讽（模型高估我们的胜率）
    for sp in (co.get('skillPotential') or []):
        _sv = str(sp.get('value') or '')
        if '挑釁' in _sv or '挑衅' in _sv:
            _mt = re.search(r'(\d+)回合', _sv) or re.search(r'回合數?\s*(\d+)', _sv)
            if _mt:
                taunt_n = max(taunt_n, int(_mt.group(1)))
    for seg in txt.split('。'):
        if '挑釁' not in seg and '挑衅' not in seg:
            continue
        mv = re.search(r'\{VALUE(\d+)\}回合期間', seg)
        if mv and vals.get('VALUE' + mv.group(1)) is not None:
            taunt_n = int(vals['VALUE' + mv.group(1)])
        else:
            m2 = re.search(r'(\d+)回合期間', seg)
            taunt_n = int(m2.group(1)) if m2 else 2
        break
    # ★ 虚弱(被击中时给攻击者挂增伤debuff): 馬莫尼勒·奇蹟海洋 等
    #   「每當自身受到攻擊時，對敵人套用{VALUE1}%的脆弱效果…每次被擊中時，疊加1次，最多可賦予疊加至8」
    vuln_pct = vuln_max = vuln_turns = 0
    for seg in txt.split('。'):
        if '脆弱' in seg and '受到攻擊時' in seg:
            mv = re.search(r'\{VALUE(\d)\}%', seg)
            if mv and vals.get('VALUE' + mv.group(1)) is not None:
                vuln_pct = vals['VALUE' + mv.group(1)]
        if '疊加至' in seg:
            m8 = re.search(r'疊加至(\d+)', seg)
            if m8:
                vuln_max = int(m8.group(1))
        mv2 = re.search(r'在脆弱效果的\{VALUE(\d)\}回合期間', seg)
        if mv2 and vals.get('VALUE' + mv2.group(1)) is not None:
            vuln_turns = int(vals['VALUE' + mv2.group(1)])
    # ★ 防護罩/減傷(受伤减少%, 与防御力乘法叠加):
    #   「6回合期間，對自身套用{VALUE3}%的防護罩效果」 / 堕落之星「2回合期間，對自身套用50%的減傷效果」
    #   注意与「能量防衛」(HP护盾)是两回事 —— 防護罩是百分比减伤
    prot_pct = prot_turns = 0
    # ★★★ 2026-11-04 新增: 区分「物理防護罩」/「魔法防護罩」/通用减伤
    #   例 拉德爾·暗黑騎士「对自己应用60%的物理防护罩效果」→ 只减【物理】伤害
    _prot_kind = 'all'
    # ★★★ 2026-11-06 新增: 「對我軍套用X%的減傷」= 全体友军减伤
    #   实证 海倫娜·頂尖偶像「4回合期間，對我軍套用50%的減傷效果」(潜能+20% → 70%)
    #   旧实现只给自己上 → 敌方辅助的团队减伤完全丢失 → 我方伤害虚高一倍
    _prot_allies = False
    for seg in txt.split('。'):
        if '防護罩' in seg or '防护罩' in seg or '減傷' in seg or '减伤' in seg:
            if ('我軍' in seg or '我军' in seg or '友軍' in seg or '友军' in seg) and '自身' not in seg:
                _prot_allies = True
            if '物理' in seg and '魔法' not in seg:
                _prot_kind = 'phys'
            elif '魔法' in seg and '物理' not in seg:
                _prot_kind = 'magic'
            mv = re.search(r'\{VALUE(\d)\}%', seg)
            if mv and vals.get('VALUE' + mv.group(1)) is not None:
                prot_pct = vals['VALUE' + mv.group(1)]
            else:
                mfixed = re.search(r'套用\s*(\d+)%', seg)   # 固定数值减伤(如堕落之星50%)
                if mfixed:
                    prot_pct = float(mfixed.group(1))
            # ★ 回合数: 可能是字面数字(4回合) 也可能是占位符({VALUE2}回合)
            #   例 萊克莉斯·殺人娃娃: 「{VALUE2}回合期間，對自身套用{VALUE1}%的減傷效果」→ 必须取 VALUE2
            mt = re.search(r'(\d+)回合期間', seg)
            if mt:
                prot_turns = int(mt.group(1))
            else:
                mtp = re.search(r'\{VALUE(\d)\}回合期間', seg)
                if mtp and vals.get('VALUE' + mtp.group(1)) is not None:
                    prot_turns = int(vals['VALUE' + mtp.group(1)])
                else:
                    prot_turns = 6
            break
    # ★★ 主动施加脆弱: 「N回合期間，對主要目標的敵人套用{VALUE}%的物理脆弱效果」
    #   (例 布莱德·小公主: 4回合 150% 物理脆弱 → 之后物理伤害 +150%)
    #   旧实现只解析「受到攻击时挂脆弱」的自反型, 主动挂脆弱的技能整段丢失
    vul_apply_phys, vul_apply_magic, vul_apply_turns = 0.0, 0.0, 0
    for seg in txt.split('。'):
        if '脆弱' not in seg:
            continue
        if '受到攻擊時' in seg or '受到攻击时' in seg:
            continue
        isp = '物理脆弱' in seg or '物理脆弱' in seg
        ism = '魔法脆弱' in seg or '魔法脆弱' in seg
        if not (isp or ism):
            continue
        mv = re.search(r'\{VALUE(\d)\}%的(?:物理|魔法)脆弱', seg)
        pct = None
        if mv and vals.get('VALUE' + mv.group(1)) is not None:
            pct = vals['VALUE' + mv.group(1)]
        if pct is None:
            m2 = re.search(r'套用\s*(\d+)%的(?:物理|魔法)脆弱', seg)
            pct = float(m2.group(1)) if m2 else None
        if pct is None:
            continue
        mt = re.search(r'(\d+)回合期間', seg)
        vul_apply_turns = int(mt.group(1)) if mt else 4

        if isp:
            vul_apply_phys = float(pct)
        if ism:
            vul_apply_magic = float(pct)
        if vul_apply_phys or vul_apply_magic:
            break
    # ★★ 爆发(Burst) 的「Plus 追加能力」也挂脆弱 (2026-10-18)
    #   例 布莱德·小公主 爆发Lv1: 「[追加能力] 4回合期間，對敵人套用物理脆弱75%的效果。」
    # ★★ 2026-10-18 用户规则: 脆弱/弱化/降防的时机看【技能文本顺序】
    #   写在傷害【之前】(如 DJ) → 第1下就吃
    #   写在傷害【之后】(如 小公主) → 第1下不吃, 第2下起吃
    _segs = txt.split('。')
    _dmg_i = next((i for i, s in enumerate(_segs) if '造成' in s and '傷害' in s), 10 ** 6)
    _vul_i = next((i for i, s in enumerate(_segs) if '脆弱' in s and '受到攻擃' not in s), 10 ** 6)
    vul_before = _vul_i < _dmg_i
    # ★★ 2026-10-19 新增: 爆发的「攻擊次數 +N」与「屬性傷害增加N%」
    #   實證: 墮落之星 爆發Lv1 = 「4回合期間，對自身套用屬性傷害增加100%的效果，攻擊次數 +1」
    #   → hits 1→2, admg 80→180（之前兩項都沒計 → 對面傷害少算一半）
    _burst_hits_add = 0
    _burst_admg_add = 0.0
    for _b in (co.get('burst') or [])[:_bst]:
        _txt = _b.get('value') or ''
        # ★★★ 2026-10-27 修 bug: 「攻擊次數 +N」不能重复累加
        #   上面 303~306 行已按 switches(target=HIT1) 加过一次;
        #   这里再从文字里加一次 → 残破木乃伊 10段 被算成 14段(应为12段)
        #   用户 2026-10-27 指出「残破木乃伊没有14段」
        _has_hit_switch = any((_sw.get('target') or '').startswith('HIT')
                              for _sw in (_b.get('switches') or []))
        _mh = re.search(r'攻擊次數\s*\+\s*(\d+)', _txt)
        if _mh and not _has_hit_switch:
            _burst_hits_add += int(_mh.group(1))
        _ma = re.search(r'屬性傷害增加\s*(\d+)%', _txt)
        if _ma:
            _burst_admg_add += float(_ma.group(1))

    # ★★ 2026-10-19 新增: 「自身受到攻擊時攻擊力增加X%」可疊加
    #   實例 阿奇拉·戰場猛獸: 每受一次攻擊 攻擊力+21%，最多 99 層
    onhit_atk_pct = 0.0
    onhit_atk_max = 0
    for _seg2 in txt.split('。'):
        if '受到攻擊時' not in _seg2 and '受到攻击时' not in _seg2:
            continue
        if '攻擊力增加' not in _seg2 and '攻击力增加' not in _seg2:
            continue
        _pct = None
        _m1 = re.search(r'\{VALUE(\d)\}%', _seg2)
        if _m1 and vals.get('VALUE' + _m1.group(1)) is not None:
            _pct = float(vals['VALUE' + _m1.group(1)])
        if _pct is None:
            _m2 = re.search(r'增加\s*(\d+)%', _seg2)
            if _m2:
                _pct = float(_m2.group(1))
        if _pct:
            onhit_atk_pct = _pct
        break
    # ★★★ ONHIT_ADDITIVE (2026-10-27 用户指出 + 实战核对):
    #   阿奇拉·戰場猛獸「此效果叠加至1。最多可叠加至99。」
    #   = 每次被打【叠 1 层】，最多 99 层 → 【加法】叠加（+30%/+60%/+90%...）
    #   旧实现是乘法 t2['atk'] *= 1.3 每层 → 打12段就 ×1.3^12 = ×23 倍（严重虚高）
    #   另外旧实现 onhit_atk_max 解析出 0 → 运行时默认 99，且上限读的是「最多可叠加至99」
    _mo = re.search(r'最多可[疊叠]加至\s*(\d+)', txt) or re.search(r'[疊叠]加至\s*(\d+)', txt)
    if _mo:
        onhit_atk_max = max(1, int(_mo.group(1)))
    elif onhit_atk_pct > 0:
        onhit_atk_max = 1
    # ★ 2026-11-06: 这条调试打印以前是无条件输出的 → 搜索时刷屏上万行
    #   现在只在 PARSER_DEBUG=1 时打印
    if onhit_atk_pct > 0 and os.environ.get('PARSER_DEBUG', '0') == '1':
        print('   [onhit_atk] %s: 每次+%.0f%% 最多%d层(加法)' % (
            (co.get('costumeName') if isinstance(co, dict) else '?'), onhit_atk_pct, onhit_atk_max))

    vul_all_phys, vul_all_magic = 0.0, 0.0
    for _b in (co.get('burst') or [])[:_bst]:
        for _seg in (_b.get('value') or '').split('。'):
            if '脆弱' not in _seg:
                continue
            _m = re.search(r'(\d+)%', _seg)
            if not _m:
                continue
            _v = float(_m.group(1))
            # ★ 2026-10-18 用户确认: 爆发的脆弱对【全体敌人】生效
            #   (技能本体的 130% 只对主要目标)
            if '物理脆弱' in _seg:
                vul_all_phys += _v
            elif '魔法脆弱' in _seg:
                vul_all_magic += _v
            _mt = re.search(r'(\d+)回合', _seg)
            if _mt:
                vul_apply_turns = max(vul_apply_turns, int(_mt.group(1)))

    # ★ 复活: 「4回合內...以{VALUE}%的生命力復活」
    # ★★ 2026-10-19 修正: 复活持续回合要看「应用复活」那句的 N回合, 不是「复活后挑衅」的回合
    #   愛麗絲原文: "4回合内，对自己应用复活效果。死亡时...100%生命复活，并2回合内...挑衅"
    #   旧实现把 "2回合" 当成了复活时长(应为 4)
    revive_pct, revive_turns = 0.0, 0
    for seg in txt.split('。'):
        if '復活' not in seg and '复活' not in seg:
            continue
        # 复活持续回合: 「N回合…应用复活」
        mt = re.search(r'(\d+)回合[^。]*?(?:应用|應用)(?:复活|復活)', seg)
        if mt and not revive_turns:
            revive_turns = int(mt.group(1))
        # 复活百分比
        if not revive_pct:
            mv = re.search(r'\{VALUE(\d)\}%的生命力', seg) or re.search(r'以\{VALUE(\d)\}%', seg)
            if mv and vals.get('VALUE' + mv.group(1)) is not None:
                revive_pct = vals['VALUE' + mv.group(1)]
            else:
                mf = re.search(r'(\d+)%的生命力', seg)
                if mf:
                    revive_pct = float(mf.group(1))
    if revive_pct and not revive_turns:
        revive_turns = 4

    # ★ 回避: 「自身在成功迴避{VALUE}次前，以100%的機率迴避敵人的攻擊」
    dodge_max = 0.0
    for seg in txt.split('。'):
        if '迴避' not in seg and '回避' not in seg:
            continue
        mv = re.search(r'成功迴避\{VALUE(\d)\}次', seg)
        if mv and vals.get('VALUE' + mv.group(1)) is not None:
            dodge_max = float(vals['VALUE' + mv.group(1)])
            break
        mf = re.search(r'成功迴避(\d+)次', seg)
        if mf:
            dodge_max = float(mf.group(1))
            break

    # ★★★ 2026-10-27 新增: 「{N}%的機率迴避敵人的攻擊 + 每次成功迴避後機率-{M}%」
    #   例 自然的腳爪/白色貓咪: 「2回合期間，自身有75%的機率迴避敵人的攻擊。
    #       每次成功迴避攻擊後，成功迴避後續攻擊的機率將減少5%。」
    #   (旧的 dodge_max 只处理「以100%機率迴避 N次」这种写法)
    dodge_p = 0.0
    dodge_dec = 5.0
    dodge_rounds = 2
    for seg in txt.split('。'):
        if '迴避' not in seg and '回避' not in seg:
            continue
        mp = re.search(r'(\d+)%\s*的機率迴避', seg)
        if mp:
            dodge_p = float(mp.group(1))
            md = re.search(r'機率將?減少(\d+)%', seg)
            if md:
                dodge_dec = float(md.group(1))
            mr2 = re.search(r'(\d+)回合期間', txt)
            if mr2:
                dodge_rounds = int(mr2.group(1))
            break

    # ★★★ 2026-10-27 新增: 「對敵人套用標記效果」= 标记类技能
    #   用户规则: 带标记的技能【无视闪避】—— 标记后不再掷概率闪避
    applies_mark = ('套用標記' in txt) or ('套用标记' in txt)
    mark_turns = 0
    if applies_mark:
        _mm = re.search(r'\{VALUE(\d)\}回合期間[，,]?對敵人套用標記', txt)
        if _mm and vals.get('VALUE' + _mm.group(1)) is not None:
            mark_turns = int(float(vals['VALUE' + _mm.group(1)]))
        else:
            _mm2 = re.search(r'(\d+)回合期間[，,]?對敵人套用標記', txt)
            mark_turns = int(_mm2.group(1)) if _mm2 else 2

    # ★ 沉默: 「N回合期間，使敌人无法施放技能」
    #   ★★ 2026-10-20 修正: 回合数要用 vals(已叠加 skillPotential 的 VALUE2)
    #      实证 代號S: 基础 VALUE2=2 + 潜能「沉默效果增加2回合」→ 4回合
    #      旧实现硬编码回退 2 → 少了 2 回合
    silence = 0
    for seg in txt.split('。'):
        if '沉默' in seg or ('無法施放技能' in seg) or ('无法施放技能' in seg):
            _mv = re.search(r'\{VALUE(\d)\}', seg)
            if _mv and vals.get('VALUE' + _mv.group(1)) is not None:
                silence = int(vals['VALUE' + _mv.group(1)])
            else:
                mt = re.search(r'(\d+)回合', seg)
                silence = int(mt.group(1)) if mt else 2
            break

    # ★ 驱散: 「解除套用於敵人的有益效果」→ 只清【护盾】(不动减伤)
    #   (魔女「解除有益效果」实测 = 只解护盾, 守护屏障/圣域之恩的减伤不被驱散)
    # ★★★ 2026-10-22 修正: 必须同时有「解除」+「有益效果」才算驱散
    #   实证: 医护兵只写了「持有的有益效果數量為5個以上時…持續回合數將延長」
    #         → 旧逻辑(只要出现"有益效果")把她误判成有驱散, 导致她打反击坦不被反击
    #   真驱散文案: 「解除套用於敵人的有益效果」(苍蓝魔女/教授/代号S/泳池派对/魔弓)
    dispel = ('有益效果' in txt) and ('解除' in txt)
    # ★ 解除减伤+护盾(钢铁引擎): 「解除套用於敵人的減傷和能量防衛效果」→ 清【减伤+护盾】
    remove_guard = (('能量防衛' in txt) or ('能量防卫' in txt)) and (('減傷' in txt) or ('减伤' in txt))
    # ★★ 减魔抗/减防 —— 生效时机 = 【技能文字顺序】(铁律: 写在伤害句前=前置, 写在伤句后=第1段拍完才生效)
    #   例 DJ 「4回合期間敵人魔法抵抗減少50%。對敵人造成…」    → 前置
    #   例 教授 额外效果「2回合期間魔法抵抗減少15%」(列在伤害句之后) → 第2段起生效
    mr_debuff = def_debuff = 0.0
    debuff_turns = 0
    _segs_all = txt.split('。')
    _i_dmg = _i_deb = -1
    for _k, _sg in enumerate(_segs_all):
        if _i_dmg < 0 and (('傷害' in _sg) or ('伤害' in _sg) or ('造成' in _sg)):
            _i_dmg = _k
        if _i_deb < 0 and (('魔法抵抗' in _sg) or ('防禦力' in _sg) or ('防御力' in _sg)):
            _i_deb = _k
    for seg in _segs_all:
        has_mr = ('魔法抵抗' in seg)
        has_def = ('防禦力' in seg) or ('防御力' in seg)
        if not (has_mr or has_def):
            continue
        # 减少数值(模板 {VALUE}% 或 固定数值)
        _m = re.search(r'\{VALUE(\d)\}%', seg)
        if _m and vals.get('VALUE' + _m.group(1)) is not None:
            _pct = float(vals['VALUE' + _m.group(1)])
        else:
            _m2 = re.search(r'(?:減少|减少|降低)\s*(\d+)%', seg)
            _pct = float(_m2.group(1)) if _m2 else 0.0
        if not _pct:
            continue
        # 合写「防御力和魔法抵抗減少90%」→ 两者都减
        if has_mr:
            mr_debuff = _pct
        if has_def:
            def_debuff = _pct
        _mt = re.search(r'(\d+)回合', seg)
        debuff_turns = int(_mt.group(1)) if _mt else 4
        break
    # ★ 文字顺序判定: 减抗句在伤害句【之后】(或找不到伤害句) → 第1段拍完后才生效
    mr_debuff_after_first = (_i_deb >= 0 and (_i_dmg < 0 or _i_deb > _i_dmg))
    # ★★ 2026-10-20 新增: 潜能「Plus」的【额外效果】—— 同样按文字顺序(额外效果天然列在技能之后)
    #   例 教授(魔法学校教授): skillPotential=[{type:"Plus", value:"2回合期間魔法抵抗減少15%"}]
    #   之前完全漏解析 → 严重低估教授后续段的伤害(实测: 胜→负 反转)
    for _sp in (co.get('skillPotential') or []):
        _v = str(_sp.get('value') or '')
        if not _v:
            continue
        _is_mr = ('魔法抵抗' in _v)
        _is_df = ('防禦力' in _v) or ('防御力' in _v)
        if not (_is_mr or _is_df):
            continue
        _m3 = re.search(r'(?:減少|减少|降低)\s*(\d+)%', _v)
        if not _m3:
            continue
        _p3 = float(_m3.group(1))
        if _is_mr:
            mr_debuff = _p3
        if _is_df:
            def_debuff = _p3
        _mt3 = re.search(r'(\d+)回合', _v)
        debuff_turns = int(_mt3.group(1)) if _mt3 else 2
        mr_debuff_after_first = True      # 额外效果 → 列在技能之后 → 第2段起
    # ★★ 2026-10-19 新增: 解除/驱散时机 = 技能文本顺序
    #   解除句在伤害句【前】(钢铁引擎「解除…再造成伤害」) → 前置
    #   解除句在伤害句【后】(魔女「造成伤害…解除」) → 后置(先打一下再解除)
    _segs2 = txt.split('。')
    _dmg_i2 = next((i for i, s in enumerate(_segs2) if '造成' in s and '傷害' in s), 10 ** 6)
    _disp_i = next((i for i, s in enumerate(_segs2) if ('解除' in s) or ('驱散' in s) or ('驅散' in s)), 10 ** 6)
    _is_before = _disp_i < _dmg_i2
    dispel_before = dispel and _is_before
    remove_guard_before = remove_guard and _is_before

    # ★ 反击: 「N回合期間，自身受到攻擊時將反擊」+「造成相當於{基准}{VALUE}%的...傷害」
    counter_skill = None
    if '反擊' in txt or '反击' in txt:
        cn = 10; cb = '自身最大HP'; cp = 0.0; allE = ('全體敵人' in txt or '全体敌人' in txt)
        for seg in txt.split('。'):
            if ('受到攻擊時' in seg or '受到攻击时' in seg) and ('反擊' in seg or '反击' in seg):
                mt = re.search(r'(\d+)回合', seg)
                if mt:
                    cn = int(mt.group(1))
            if ('反擊時' in seg or '反击时' in seg) and '傷害' in seg:
                # ★★ 2026-10-22 修正: 「造成受到的傷害X%的傷害」= 按【所受傷害】为基准
                #   (葛蘭西特·虛無之星「每次反擊時，對敵人造成受到的傷害{VALUE2}%的物理傷害」)
                #   旧实现没有这个分支 → 全部落到「自身最大HP」→ 伤害虚高 4 倍以上
                cb = ('受到傷害' if ('受到的傷害' in seg or '所受傷害' in seg or '受到的伤害' in seg) else
                      '自身最大HP' if '最大生命力' in seg else
                      '自身攻擊力' if ('攻擊力' in seg or '攻击力' in seg) else '自身最大HP')
                mv = re.search(r'\{VALUE(\d)\}%', seg)
                if mv and vals.get('VALUE' + mv.group(1)) is not None:
                    cp = float(vals['VALUE' + mv.group(1)])
        # ★ 反击次数上限: 「此效果將在受到{VALUE1}次攻擊後消失」
        chits = None
        for seg in txt.split('。'):
            mh = re.search(r'受到\{VALUE(\d)\}次攻擊', seg)
            if mh and vals.get('VALUE' + mh.group(1)) is not None:
                chits = int(vals['VALUE' + mh.group(1)])
                break
        if cp:
            counter_skill = {'pct': cp, 'basis': cb, 'all': allE, 'turns': cn, 'hits': chits}

    # ★★★ 2026-10-22 新增: 「每次受到攻擊時，恢復相當於自身最大生命力{X}%」(赛尔·恶魔之女)
    heal_pct = 0.0
    _mh = re.search(r'受到攻擊時[，,]?恢復相當於自身最大生命力\{VALUE(\d)\}%', txt)
    if _mh and vals.get('VALUE' + _mh.group(1)) is not None:
        heal_pct = float(vals['VALUE' + _mh.group(1)])
    # ★ 潜能的「4回合挑釁」→ 嘲讽 N 回合（type=Plus, 无 switches）
    for _sp in (co.get('skillPotential') or []):
        _v = str(_sp.get('value') or '')
        if '挑釁' in _v or '挑衅' in _v:
            _mt = re.search(r'(\d+)回合', _v)
            if _mt:
                taunt_n = max(taunt_n, int(_mt.group(1)))

    # ★★★ 2026-11-05 新增: 「血氣」叠层 + 「出血」持续伤害（斐傑·背叛之夜 Valze_1）
    #   原文: 6回合期間自身套用「持續傷害造成的傷害增加5%」的血氣疊加(可疊VALUE2, 最多20)
    #         攻擊敵人2次，每段依【自身持有的每一個血氣】造成 VALUE1% 魔法傷害
    #         VALUE3回合期間，對敵人套用 VALUE4% 魔法傷害的出血
    #   ⇒ 伤害按血气层数放大 + 出血是每回合结算的持续伤害
    blood_gain, blood_max, blood_dot_pct = 0, 20, 5.0
    bleed_pct, bleed_turns = 0.0, 0
    per_per_stack = False
    if '血氣' in txt or '血气' in txt:
        if vals.get('VALUE2') is not None:
            blood_gain = int(vals['VALUE2'])
        _mb = re.search(r'疊加至\s*(\d+)|叠加至\s*(\d+)', txt)
        if _mb:
            blood_max = int(_mb.group(1) or _mb.group(2))
        _mp2 = re.search(r'持續傷害造成的傷害增加\s*(\d+(?:\.\d+)?)%', txt)
        if _mp2:
            blood_dot_pct = float(_mp2.group(1))
        if '每一個血氣' in txt or '每一个血气' in txt:
            per_per_stack = True
    if '出血' in txt:
        if vals.get('VALUE4') is not None:
            bleed_pct = float(vals['VALUE4'])
        if vals.get('VALUE3') is not None:
            bleed_turns = int(vals['VALUE3'])
    # ★★★ 2026-11-05: 「攻擊對自身造成持續傷害狀態的敵人時，造成的傷害增加X%」(增強)
    #   例 斐傑·背叛之夜 burst Lv2 → 对出血状态敌人 +50%
    dot_amp_pct = 0.0
    _all_txt = txt + '。' + '。'.join((b.get('value') or '') for b in (co.get('burst') or [])[:_bst])
    for _seg in _all_txt.split('。'):
        if ('血氣' in _seg) or ('血气' in _seg):
            continue                      # ★ 血氣自身那条「持續傷害造成的傷害增加5%」不是增強
        if ('持續傷害' in _seg or '持续伤害' in _seg) and ('傷害增加' in _seg or '伤害增加' in _seg):
            _ma = re.search(r'傷害增加\s*(\d+(?:\.\d+)?)%|伤害增加\s*(\d+(?:\.\d+)?)%', _seg)
            if _ma:
                dot_amp_pct = float(_ma.group(1) or _ma.group(2))
                break

    attr = ch.get('attribute')
    return {'name': '%s·%s' % (ch.get('enName'), co.get('costumeName')),
            'per': (float(per) if _has_dmg else 0.0), 'hits': (int(hits) + int(_burst_hits_add)) if _has_dmg else 0, 'basis': basis,   # ★爆發「攻擊次數+N」
            'blood_gain': blood_gain, 'blood_max': blood_max, 'blood_dot_pct': blood_dot_pct,
            'per_per_stack': per_per_stack, 'bleed_pct': bleed_pct, 'bleed_turns': bleed_turns,
            'dot_amp_pct': dot_amp_pct,
            'cond_per_value': cond_per_value, 'cond_per_type': cond_per_type,   # ★ 条件倍率(敌人攻击类型)
            'per_per_target': per_per_target,   # ★ 每个目标增伤的 X
            'per_target_mode': per_target_mode,   # ★ 'each'=×N(每有一个) / 'extra'=×(N-1)(每多一个)
            'atk_down_phys': atk_down_phys, 'atk_down_mag': atk_down_mag,
            'atk_down_turns': atk_down_turns,   # ★ 减攻击/魔法力(按目标类型分开)
            'type': ch.get('atkType'), 'attr': attr,
            'atk': atk * float(os.environ.get('ATK_MULT', '1')),
            'hp': hp * HPM, 'hpmax': hp * HPM,
            'cr': cr, 'cdmg': cdmg,
            # ★★ 2026-10-18 修正: 防御/魔抗 也要算百分比加成!
            #   旧实现只用了 maxlevel 的白值(爱丽丝 mr=20), 而实际面板是 45.4
            #   来源: 刻印 8% + 觉醒 4% + 羈绊 13.4% + 潛能 6.7% + 收藏 80%
            # ★★ 2026-10-18 用户实测: 防御/魔抗 = 白值 + 百分比【直接当点数加】
            #   爱丽丝: 20 + 刻印 8 + 觉醒 4 + 羈绊 13.4 = 45.4 = 面板 ✓
            #   (不是乘法! 也不吃收藏80%)
            'def': float(ml.get('def') or 0) + a.get('DEF', 0) + a.get('DEF%', 0),
            'mr':  float(ml.get('mr') or 0) + a.get('MR', 0) + a.get('MR%', 0),
            'admg': a.get('ADMG', 0) + 50 + _burst_admg_add,   # ★爆發「屬性傷害+N%」
            # ★ 2026-10-22 用户确认: 属性抵抗【光=0 暗=0，水/火/風=50】
            #   游戏只有 5 个属性: 風/光/水/火/暗（没有「地」）
            #   也就是说除了光暗，其余一律 50
            'pres': (_pres_override if _pres_override is not None
                     else (0.0 if attr in ('光', '暗') else 50.0)),
            'order': order, 'pos': pos, 'alive': True,
            'shape': [list(x) for x in (shape or [[0, 0]])],
            'target': co.get('target') or '最前方',
            'dispel': dispel, 'taunt_n': taunt_n, 'taunt_seq': 0,
            'mr_debuff': mr_debuff, 'def_debuff': def_debuff, 'debuff_turns': debuff_turns, 'dispel_before': dispel_before, 'mr_debuff_after_first': mr_debuff_after_first,
            'remove_guard': remove_guard, 'remove_guard_before': remove_guard_before,
            'counter_skill': counter_skill,
            'shield_pct': shield_pct, 'shield_basis': shield_basis, 'shield_allies': shield_allies,
            'shield_dmg_pct': shield_dmg_pct, 'shield_turns': shield_turns,
            'heal_pct': heal_pct,
            'vul_apply_phys': vul_apply_phys, 'vul_apply_magic': vul_apply_magic,
            'vul_apply_turns': vul_apply_turns, 'onhit_atk_pct': onhit_atk_pct, 'onhit_atk_max': onhit_atk_max, 'vul_before': vul_before, 'vul_all_phys': vul_all_phys, 'vul_all_magic': vul_all_magic,
            'prot_pct': prot_pct, 'prot_turns': prot_turns, 'prot_kind': _prot_kind,
            'prot_allies': _prot_allies,
            'revive_pct': revive_pct, 'revive_turns': revive_turns,
            'applies_mark': applies_mark, 'mark_turns': mark_turns, 'dodge_max': dodge_max, 'dodge_p': (0.0 if dodge_max > 0 else dodge_p), 'dodge_dec': dodge_dec, 'dodge_rounds': dodge_rounds, 'silence': silence,
            'self_buff': self_buff, 'sb_hit_buff': sb_hit_buff, 'team_buff': team_buff, 'sb_stack_max': sb_stack_max, 'per_hit_grow': per_hit_grow,
            'vuln_pct': vuln_pct, 'vuln_max': vuln_max, 'vuln_turns': vuln_turns, 'vuln_hits': 8,
            # ★ 运行时初始值(战斗开始会被覆盖, 不初始化会 KeyError)
            'chains': 0, 'vul_phys': 0, 'vul_magic': 0, 'vuln_stacks': 0, 'vuln_left': 0,
            'taunt': False, 'taunt_left': 0, 'counter': None, 'counter_left': 0, 'counter_used': 0,
            'shield': 0.0, 'skillred': 0.0, 'prot': 0.0, 'prot_left': 0,
            'dodge': 0, 'dodge_granted': False, 'revive_left': 0,
            'silenced': 0, 'silenced1': False, 'suppressed': 0, 'focus': False,
            'ext_vuln': 0, 'untarg': 0, 'order_is_second': False,
            'atk0': atk, 'hp0': hp * HPM, 'def0': float(ml.get('def') or 0),
            'mr0': float(ml.get('mr') or 0), 'admg0': a.get('ADMG', 0) + 50 + _burst_admg_add,
            'pres0': 50.0 if attr in ('水', '火', '風') else 0.0,
            'cr0': cr, 'cdmg0': cdmg, 'bless_shield1': 0.0,
            '_bm_atk': 0.0, '_bm_hp': 1.0, '_bm_def': 0.0, '_bm_mr': 0.0,
            '_bm_admg': 0.0, '_bm_pres': 0.0}

# ★ 属性相克关系: (A, B) 表示 A 克 B
ADV = {('水', '火'), ('火', '風'), ('風', '水'), ('光', '暗'), ('暗', '光')}