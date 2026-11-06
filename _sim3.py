# -*- coding: utf-8 -*-
"""黄金竞技场 战斗模拟器 v3 —— 庇佑开局并入属性 + 读取防守方真实庇佑"""
import json, io, os, re, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
DISPEL_N = [0]          # 诊断用: 驱散实际清掉护盾/减伤的次数
VERBOSE = [0]
# ★待施加的脆弱(本次行動結束後才生效)
_PENDING_VUL = []           # 设成 1 可打印逐回合/逐段细节(对决用)
# 脆弱来自【额外能力】的服饰: 整段技能打完后才挂上
VUL_AT_END = {'忌妒之夜', '致命之眼'}
# 攻击后给目标挂「连携伤害增加 X%」的服饰
CHAIN_ADD = {('Nekyndalia', '致命之眼'): 3.0, ('涅肯達莉亞', '致命之眼'): 3.0, '致命之眼': 3.0}
DMG_LOG = [0.0, '']     # 诊断用: [总伤害, 归属方] —— 与实战"总伤害"对账用
DMG_DEBUG = [0]         # 设成 1 打印伤害公式各乘区分解
DMG_BY_UNIT = {}        # 诊断用: 我方每人累计伤害
DMG_ENEMY = {}          # 诊断用: 敌方每人累计伤害
HERE = os.path.dirname(os.path.abspath(__file__))
# AOE 口径: full = 范围内每个目标都吃满「段数×倍率」; split = 段数在范围内目标间分摊
AOE_MODE = os.environ.get('AOE_MODE', 'full')
# ★ 2026-10-16 用户口述实证: 多段技能(如魅魔·海滨度假2段、堕落之星2段)每段都打【同一范围】,
#   即范围内每个目标吃满所有段数(full), 不是摊给不同人、也不是只打最前方。魅魔尤其爆发3伤害极高。
import types
import random
_src = io.open(os.path.join(HERE, '_sim.py'), encoding='utf-8').read().split('lines = io.open')[0]
s1 = types.SimpleNamespace()
s1.__dict__['__file__'] = os.path.join(HERE, '_sim.py')
exec(compile(_src, '_sim_head', 'exec'), s1.__dict__)
_us_orig = s1.unit_stats

# ★★★ 2026-10-24: 技能带「若敵人為主要目標，則變為…」的服饰 → (普通倍率, 主目标倍率)
#   数值来自用户游戏内截图（含 潜力+爆發3）
PER_MAIN = {
    ('Levia', '忌妒之夜'): (240.0, 520.0),
    ('萊維亞', '忌妒之夜'): (240.0, 520.0),
    '忌妒之夜': (240.0, 520.0),
    ('Nekyndalia', '致命之眼'): (120.0, 120.0),
    ('涅肯達莉亞', '致命之眼'): (120.0, 120.0),
    '致命之眼': (120.0, 120.0),
}
# 段数修正(用户截图)
HITS_OVERRIDE = {('Nekyndalia', '致命之眼'): 12, ('涅肯達莉亞', '致命之眼'): 12, '致命之眼': 12}


def _ov(tbl, u):
    """覆盖表查询: 先查 (角色,服饰) 双键, 再退回只查服饰名

    ★★★ 2026-10-24 用户提醒: 不同角色可能有【同名服饰】
       例 泳池派對 有 拉德爾/悠絲緹亞/莎赫拉查德/格雷/安潔莉卡 五个
          海邊度假 有 伊柯利普斯/墨菲亞 两个
       只按服饰名匹配会认错人（属性/数值全错）
    """
    if not u:
        return None
    _n = u.get('name') or ''
    _parts = _n.split('·')
    _co = _parts[-1] if _parts else ''
    _ch = _parts[0] if len(_parts) > 1 else ''
    for _k2 in ((_ch, _co), _co):
        if _k2 in tbl:
            return tbl[_k2]
    return None


def unit_stats(*a, **k):
    u = _us_orig(*a, **k)
    if u:
        _pm = _ov(PER_MAIN, u)
        if _pm:
            # ★★★ 2026-10-29 用户截图修正: 忌妒之夜 倍率随【爆发等级】变化
            #   破5+潜能: VALUE1=180 / VALUE2=420  (爆0-爆1, 用户截图)
            #   爆2/爆3:  "一般+30% / 主要目标+50%" → 240 / 520
            _co = (u.get('name') or '').split('·')[-1]
            if _co == '忌妒之夜':
                _b = k.get('burst')
                if _b is None and len(a) >= 6:
                    _b = a[5]
                try:
                    _b = int(_b or 0)
                except Exception:
                    _b = 0
                if _b >= 2:
                    u['per'], u['per_main'] = 240.0, 520.0
                else:
                    u['per'], u['per_main'] = 180.0, 420.0
            else:
                # ★★★ 2026-11-06 修正(用户指出): PER_MAIN 是"满破满爆"口径的定值，
                #   直接覆盖会让【破度/爆发完全失效】(致命之眼 破0爆0 与 破5爆3 结果一模一样)
                #   → 用自然解析值做比例修正: ratio = 自然(当前破爆) / 自然(破5爆3)
                _bv = a[4] if len(a) > 4 else k.get('brk')
                _sv = a[5] if len(a) > 5 else k.get('burst')
                try:
                    _un = _us_orig(a[0], a[1], a[2], a[3], _bv, _sv)
                    _uf = _us_orig(a[0], a[1], a[2], a[3], 5, 3)
                    _n0 = float((_un or {}).get('per') or 0)
                    _n1 = float((_uf or {}).get('per') or 0)
                except Exception:
                    _n0 = _n1 = 0
                _ratio = (_n0 / _n1) if (_n1 > 0 and _n0 > 0) else 1.0
                u['per'] = _pm[0] * _ratio
                u['per_main'] = _pm[1] * _ratio
            u['cond_per_value'] = None
            u['cond_per_type'] = None
            # ★ 忌妒之夜同样要跟随破度变化（爆发已单独处理）
            if (u.get('name') or '').split('·')[-1] == '忌妒之夜':
                _bv2 = a[4] if len(a) > 4 else k.get('brk')
                try:
                    _un2 = _us_orig(a[0], a[1], a[2], a[3], _bv2, 3)
                    _uf2 = _us_orig(a[0], a[1], a[2], a[3], 5, 3)
                    _x0 = float((_un2 or {}).get('per') or 0)
                    _x1 = float((_uf2 or {}).get('per') or 0)
                except Exception:
                    _x0 = _x1 = 0
                _r2 = (_x0 / _x1) if (_x1 > 0 and _x0 > 0) else 1.0
                u['per'] = u['per'] * _r2
                u['per_main'] = u['per_main'] * _r2
        _h = _ov(HITS_OVERRIDE, u)
        if _h:
            # ★★★ 2026-11-06 修正(同类问题): HITS_OVERRIDE 也是"满破满爆"口径定值
            #   致命之眼 定值12 实际=基础10 + 爆发2级(+2)
            #   → 用差值修正: hits = 定值 + (自然(当前) - 自然(破5爆3))
            try:
                _ch, _cco = (a[0], a[1])
                _uh = _us_orig(_ch, _cco, a[2], a[3], a[4] if len(a) > 4 else k.get('brk'),
                               a[5] if len(a) > 5 else k.get('burst'))
                _uh2 = _us_orig(_ch, _cco, a[2], a[3], 5, 3)
                _d = int((_uh or {}).get('hits') or 0) - int((_uh2 or {}).get('hits') or 0)
            except Exception:
                _d = 0
            u['hits'] = max(1, int(_h + _d))
    return u
ADV = s1.ADV

# ---------- 庇佑数值表（取自游戏 _blessings_i18n.js） ----------
# ('ATK', 值, 过滤)  过滤: all / ('attr','光') / ('type','物')
B = {
    # ★ 力量庇佑只提升【攻击力】= 物理系; 魔力庇佑只提升【魔法力】= 魔法系。
    #   角色只有一个 atk 属性(物角色显示攻击力、魔角色显示魔法力), 故按 atkType 过滤。
    #   → 魔法队带力量庇佑完全无效; 混编队只有对应系吃到。
    # ★★ 2026-10-22 赛季47 改版: 力量/魔力庇佑只剩【单级 +350%】（原 I/II/III = 50/125/200）
    '力量庇佑': [('ATK', {'I': 350}, ('type', '物'))],
    '魔力庇佑': [('ATK', {'I': 350}, ('type', '魔'))],
    # ★★ 赛季47 删除: 火/水/风/光/暗 之庇佑（改为 绑定的庇佑/和谐的庇佑，见下）
    # 慧眼如炬 / 杀戮斗魂 : 统一在 crit_of() 里按【叠加】处理, 此处不再重复
    # ★★ 赛季47 删除: 烈焰/深海/疾风/光辉/暗黑 之恩（改为 绑定之恩/和谐之恩，见下）
    # ★★ 赛季47: 斗魂/精灵之恩只剩【单级 +450%】
    '斗魂之恩': [('HP', {'I': 450}, ('type', '物'))],
    '精灵之恩': [('HP', {'I': 450}, ('type', '魔'))],
    # ★★ 赛季47 新增: 绑定/和谐 系列（条件: 同属性≥3人 / ≥3种不同属性）
    # ★ 注意: split_lv() 会把「绑定的庇佑I」拆成 (绑定的庇佑, I) → 表里必须写不带等级的基础名
    '绑定的庇佑': [('ATK', {'I': 150, 'II': 300}, ('same_attr', 3))],
    '和谐的庇佑': [('ATK', {'I': 150, 'II': 300}, ('distinct_attr', 3))],
    '绑定之恩': [('HP', {'I': 150, 'II': 350}, ('same_attr', 3))],
    '和谐之恩': [('HP', {'I': 150, 'II': 350}, ('distinct_attr', 3))],
    '守护权能': [('DEF', {'I': 60}, 'all')],
    '守护圣域': [('MR', {'I': 60}, 'all')],
    '均衡结界': [('ADMG', {'I': 200}, 'all'), ('属性抵抗', {'I': 40}, 'all')],
    # ★★ 赛季47: 威力增强改为【每回合开始 +100%/+200%，最多4层】→ 在 dmg() 里按 rnd 处理，不上表
    '突袭准备': [('ATK', {'I': 300}, ('order', 3))],   # ★ 只对#3顺位, 攻+300%(与魔法增强加法叠加)
}
# ★ ID→名称 映射补齐 (2026-10-18 用户确认)
#   ID45 = 深海之恩 (水属性 HP+250%, 与光辉之恩同结构)
#   实证: 19749254 的 死亡之夜(水) 实际 41,699血, 模型原本只算 15,209
B['ID45'] = [('HP', {'I': 250, 'II': 250}, ('attr', '水'))]   # ★實測: ID45 = 深海之恩II (+250%)

# ★★ 协议裸 ID → 盲名 (2026-10-18 实测确认)
#   方法: 让用户在游戏里装上已知名字的庇佑 →
#         拉自己(394419)的 ColosseumRankDetail → 读 f7/f8 原始 ID
#   实测: 装「逆转权能I + 桼梓之链I」→ ID [27, 33]
#         且顺序与装备顺序一致 (三更火火的打印顺序也对得上)
B['ID27'] = None    # 逆转权能I  (反击伤害+200%, 已在代码里特殊处理)
B['ID33'] = None    # 桎梏之链I  (连锁加成+1层, 同上)
B['ID34'] = None    # 桎梏之链II (连锁加成, 已实现)
B['ID35'] = None    # 禁锢之力   (每层连锁 +2%)
ID_ALIAS = {'ID27': '逆转权能I', 'ID33': '桎梏之链I',
            'ID34': '桎梏之链II', 'ID35': '禁锢之力'}
def split_lv(nm):
    nm = nm.strip()
    m = re.match(r'^(.*?)(III|II|I)$', nm)
    if m:
        return m.group(1), m.group(2)
    return nm, 'I'

# ★★★ 2026-10-22 官方规则（用户提供截图）:
#   「若以最大生命力为基准使用技能时，基础生命力超过 50000，则数值以 50000 为基准计算」
#   ★★★ 2026-10-22 实测确认: 伤害也封顶！实证 93,375 = 50,000×90%×2.5×0.83
HP_BASE_CAP = 50000.0


def hpbase(u):
    """生命基准的封顶值（官方 50000 上限）"""
    return min(float(u.get('hpmax') or 0.0), HP_BASE_CAP)


def _blk_bless_debuff(u):
    """庇佑类弱化是否被挡: 言灵祝福有效, 但只有【先攻方】的言灵才能免疫后攻方的庇佑"""
    return bool(u.get('_first_side')) and has(u.get('_tbless') or [], '言灵祝福')

def apply_bless(team, names):
    """★ 严格按【摆放顺序】逐条即时执行 —— 后出现的庇佑用"已经被前面庇佑更新过的属性"算。

    ★ 2026-10-17 用户确认的游戏真实行为:
      「执行到那里的时候就按照那个血量算。比如光辉之恩先看对面有没有诅咒压制，
        然后加上血了，然后再执行生命结界就看那个加过血的来算」

    所以:
      - 生命结界 I/II 在它的**实际摆放位置**结算, 用它当时的 HP
        (光辉之恩 放在它前面 → 护盾吃满加成; 放在后面 → 护盾按原始 HP)
      - 生命结界 I/II 的护盾量【叠加】: 150%+300% = 450%, 但每级按各自时刻的 HP 累加
      - 同名多级(守护屏障等)取最高级
    """
    if not names:
        names = []
    order = {'I': 1, 'II': 2, 'III': 3}
    # ★★ 赛季47: 绑定/和谐 系列的条件判定（同属性≥3人 / ≥3种不同属性）
    from collections import Counter as _Ctr
    _ac = _Ctr(u['attr'] for u in team)
    _max_same = max(_ac.values()) if _ac else 0
    _n_distinct = len(_ac)
    done = set()
    for raw in names:
        nm, lv = split_lv(raw)
        # ★★★ 2026-10-22 用户实测纠正: 绑定之恩/和谐之恩 I+II 也是【叠加】的
        #   实证: 冰镇苦瓜队伍 白雷裸血 4,305 → 实际 25,830 (=×6.0=+500%)
        #         小红帽裸血 7,187 → 实际 43,122 (=×6.0=+500%)
        #   绑定之恩I(+150%) + II(+350%) = +500% → 这才是正确算法
        #   (旧实现把 I 当"同名低级别"丢掉 → 只算 +350% = ×4.5，血量少算 25%)
        _STACK_NM = ('生命结界', '绑定之恩', '和谐之恩', '绑定的庇佑')   # 这几类必须逐条累加
        if nm not in _STACK_NM:
            for r2 in names:
                n2, l2 = split_lv(r2)
                if n2 == nm and order.get(l2, 0) > order.get(lv, 0):
                    lv = l2
        if nm in done:
            continue
        if nm not in _STACK_NM:
            done.add(nm)
        # ★ 生命结界: 立即按【当前】HP 结算（严格顺序）
        if nm == '生命结界':
            pct = 3.0 if lv == 'II' else 1.5
            for u in team:
                # ★★★ 2026-10-24 用户实证纠正: 盾量用【未被极限诅咒压迫打折的 HP】
                #   实证 Anoko(uid 333163): 泳池派对 裸血8,807 + 绑定之恩II(+350%)
                #     压迫后战斗血 = 31,925 ✅ (用户确认血是对的)
                #     护盾 = 59,446 ✅ = 150% × 39,632(未打折)  ← 不是 150% × 31,925 = 47,888
                #   → 血按打折后算, 盾按打折前算
                _raw_hp = u['hp0'] * (1 + (u.get('_bm_hp_pct', 0.0) + u.get('_sb_hp', 0.0)) / 100.0)
                u['bless_shield1'] = u.get('bless_shield1', 0.0) + min(_raw_hp, 50000.0) * pct * float(os.environ.get('SHIELD_SCALE','1'))
                u['_shield_pct'] = u.get('_shield_pct', 0) + pct
            continue
        for key, tab, filt in B.get(nm, []):
            v = tab.get(lv, tab.get('I', 0))
            for u in team:
                if not (filt == 'all'
                        or (filt[0] == 'attr' and u['attr'] == filt[1])
                        or (filt[0] == 'type' and u['type'] == filt[1])
                        or (filt[0] == 'order' and u['order'] == filt[1])
                        or (filt[0] == 'same_attr' and _max_same >= filt[1])
                        or (filt[0] == 'distinct_attr' and _n_distinct >= filt[1])):
                    continue
                if key == 'ATK':
                    # ★ ATK 百分比加成【加法叠加】(威力增强/魔法增强/突袭 等相加), 不是乘法
                    #   (2026-10-17 实战: 突袭300%+魔法增强100% = +400%, 不是 ×4×2=×8)
                    u['_bm_atk'] = u.get('_bm_atk', 0.0) + v
                    u['atk'] = u['atk0'] * (1 + u['_bm_atk'] / 100)
                    # ★ 突袭准备: 只持续【4回合】(用户确认), 记下来供到时撤销
                    if nm == '突袭准备':
                        u['_surprise_atk'] = u.get('_surprise_atk', 0.0) + v
                elif key == 'HP':
                    # ★★ 2026-10-22 用户规则: 百分比加成【加白值】, 不是阶乘
                    #   绑定之恩II(+350%) + 斗魂之恩(+450%) = +800% (×9)，不是 ×4.5×5.5=×24.75
                    u['_bm_hp_pct'] = u.get('_bm_hp_pct', 0.0) + v
                    u['hp'] = u['hp0'] * (1 + (u['_bm_hp_pct'] + u.get('_sb_hp', 0.0)) / 100)
                    u['hpmax'] = u['hp']
                elif key == 'DEF':
                    u['def'] += v; u['_bm_def'] = u.get('_bm_def', 0.0) + v
                elif key == 'MR':
                    u['mr'] += v; u['_bm_mr'] = u.get('_bm_mr', 0.0) + v
                elif key == 'ADMG':
                    u['admg'] += v; u['_bm_admg'] = u.get('_bm_admg', 0.0) + v
                elif key == '属性抵抗':
                    u['pres'] = u.get('pres', 0) + v; u['_bm_pres'] = u.get('_bm_pres', 0.0) + v
    # ★ 敏捷权能(3点): 全队获得 1 次闪避(免疫1次伤害)
    #   庇佑在开局即生效(不同于服装技能"需放技能才生效"), 故在此直接加
    if has(names, '敏捷权能'):
        for u in team:
            u['dodge'] = u.get('dodge', 0) + 1

def _apply_stat(u, tag, v):
    # ★★★ 2026-11-04 修正(用户指出): 【攻擊力】和【魔法力】是两个属性，不能互相加强
    #   「我軍攻擊力+X%」只加强物理伤害角色；「我軍魔法力+X%」只加强魔法角色
    #   模型的 u['atk'] 对魔法角色存的就是 MATK（_sim.py 的 KEY_ALIAS 把 MATK→ATK）
    #   旧实现把两者都当 ATK% → 增攻会同时加强魔法角色（霍爾蒙克斯 +280% 让 DJ/致命之眼 虚高）
    # ★ 記錄技能自帶的 ATK%%/MATK%%/HP%%
    try:
        if tag in ('ATK%', 'MATK%'):
            _is_mag = (u.get('type') == '魔')
            if not ((tag == 'ATK%' and _is_mag) or (tag == 'MATK%' and not _is_mag)):
                _vk = '_sb_atk' if tag == 'ATK%' else '_sb_mtk'
                u[_vk] = u.get(_vk, 0.0) + float(v)
        if tag == 'HP%':
            u['_sb_hp'] = u.get('_sb_hp', 0.0) + float(v)
    except Exception:
        pass
    if tag in ('ATK%', 'MATK%'):
        # ★★ 2026-10-22 用户纠正: 同源加成【加白值】, 不是阶乘
        #   正确: atk = 白值 × (1 + 庇佑% + 技能%)
        u['atk'] = u['atk0'] * (1 + (u.get('_bm_atk', 0.0) + u.get('_sb_atk', 0.0)
                                     + u.get('_sb_mtk', 0.0)) / 100)
    elif tag == 'HP%':
        # ★★ 2026-10-22: 同样加白值（不是阶乘）
        u['hp'] = u['hp0'] * (1 + (u.get('_bm_hp_pct', 0.0) + u.get('_sb_hp', 0.0)) / 100)
        u['hpmax'] = u['hp']
    elif tag == 'CDMG':
        u['cdmg'] += v
        u['_sb_cdmg'] = u.get('_sb_cdmg', 0.0) + v    # ★ 记录 self_buff 部分(供压迫结算)
    elif tag == 'CR':
        u['cr'] += v
        u['_sb_cr'] = u.get('_sb_cr', 0.0) + v
    elif tag == 'ADMG':
        u['admg'] += v

def _apply_vul(u, t2, is_main):
    """★ 把一个单位本次施加的脆弱挂到目标身上
    ★★ 2026-10-20 用户确认: 【主目标】= 技能脆弱 + 爆发脆弱【相加】
       小公主 例: 技能150% + 爆发75% → 主目标 225%, 其他目标只吃爆发75%
    """
    if not t2.get('alive'):
        return
    _p = (u.get('vul_all_phys') or 0) + ((u.get('vul_apply_phys') or 0) if is_main else 0.0)
    _m = (u.get('vul_all_magic') or 0) + ((u.get('vul_apply_magic') or 0) if is_main else 0.0)
    if _p > 0:
        t2['vul_phys_amt'] = max(t2.get('vul_phys_amt') or 0, _p)
        t2['vul_phys_left'] = max(t2.get('vul_phys_left') or 0, u.get('vul_apply_turns') or 4)
    if _m > 0:
        t2['vul_magic_amt'] = max(t2.get('vul_magic_amt') or 0, _m)
        t2['vul_magic_left'] = max(t2.get('vul_magic_left') or 0, u.get('vul_apply_turns') or 4)


def flush_pending_vul():
    # 將延後的脆弱一次性施加
    global _PENDING_VUL
    for u, t2, is_main in _PENDING_VUL:
        _apply_vul(u, t2, is_main)
    _PENDING_VUL = []


def apply_skill_buffs(t, include_self=False):
    """★ 技能自带的 自身/我军 增益
    ★★ 2026-10-20 用户规则: 服饰效果都是【先放技能才有】
       self_buff(自身) 改为【出手时】才应用 → 见 act() 开头
       team_buff(我军) 仍在开局应用
    """
    team = []
    for u in t:
        if include_self:
            for tag, v in u.get('self_buff') or []:
                _apply_stat(u, tag, v)
        # ★★ 2026-10-22 用户规则: 「对我军」的增益要【放技能之后】才生效，不是开局常驻
    #   (例 鲁·小红帽 6回合我军致命率+50/致命伤害+300 → 她出手后才给)
    #   已移到 act() 里应用
    for u in t:
        for tag, v in team:
            _apply_stat(u, tag, v)

def val_of(names, nm, key='I'):
    return 0

_SPLIT_CACHE = {}


def _split_c(nm):
    v = _SPLIT_CACHE.get(nm)
    if v is None:
        v = split_lv(nm)
        _SPLIT_CACHE[nm] = v
    return v


_BL_KEY = None
_BL_SET = frozenset()


def _bl_set(names):
    """把一条庇佑列表转成「基础名集合」，每条列表只算一次（原来每次 has() 都重扫）"""
    global _BL_KEY, _BL_SET
    k = tuple(names)
    if k != _BL_KEY:
        _BL_KEY = k
        _BL_SET = frozenset(_split_c(x)[0] for x in k)
    return _BL_SET


_LIST_FIELDS = ('self_buff', 'team_buff', 'sb_hit_buff', 'burst_list')


def clone(u):
    """单位快速克隆：只复制顶层 dict + 会被就地修改的 list
       （shape 等大对象只读共享）—— 比 copy.deepcopy 快 5~10 倍"""
    d = dict(u)
    for k in _LIST_FIELDS:
        v = d.get(k)
        if isinstance(v, list):
            d[k] = list(v)
    for k, v in d.items():
        if isinstance(v, dict):
            d[k] = dict(v)
    return d


def clone_team(team):
    return [clone(x) for x in team]


def has(names, nm):
    if not names:
        return False
    return nm in _bl_set(names)

def lv_of(names, nm):
    """同名庇佑多级时取最高级"""
    if not names:
        return None
    order = {'I': 1, 'II': 2, 'III': 3}
    best = None
    for x in names:
        a, b = split_lv(x)
        if a == nm and (best is None or order.get(b, 0) > order.get(best, 0)):
            best = b
    return best

def _sum_lv(names, nm, tab):
    """同名多级【叠加】(玩家会花点数同时带 I+II, 取最高级就浪费了)"""
    if not names:
        return 0
    s = 0
    for x in names:
        a, b = split_lv(x)
        if a == nm:
            s += tab.get(b, tab.get('I', 0))
    return s

def crit_of(u, is_first, bless):
    # ★ 2026-10-17 双面板实证修正(出云天花 无诅咒650% / 有诅咒I 440%):
    #   极限诅咒压制的是【暴击率增益(慧眼如炬)】: +140 → +140×(1-P)
    #   → 溢出 = (白值CR+50收藏集+慧眼×(1-P)) - 100
    #   → 转化爆伤 = 溢出 × 6 (R=CRIT_CONVERT), 加到白值爆伤上, 【不再二次压制】
    #   实证: 无诅咒 (60+140-100)×6=600 → 50+600=650 ✓
    #         有诅咒I (60+105-100)×6=390 → 50+390=440 ✓
    P = (u.get('suppressed', 0) or 0) / 100.0
    # ★★★ 2026-10-22: 开启烟幕的 -50暴击率/-300爆伤 必须在【庇佑加成之后】扣
    #   旧实现只扣了白值(50→0)，杀戮斗魂的 +700 逃掉了 → 伤害虚高
    _crp = float(u.get('_cr_pen', 0) or 0)
    _cdp = float(u.get('_cd_pen', 0) or 0)
    cr = u['cr'] + _sum_lv(bless, '慧眼如炬', {'I': 50, 'II': 90, 'III': 150}) * (1 - P) - _crp
    cd_base = u['cdmg']                                  # 白值 + 服装(固有) + 技能增益(小红帽等)
    cd_buff = _sum_lv(bless, '杀戮斗魂', {'I': 300, 'II': 700}) * (1 - P)
    # ★ 超出100%的暴击率按 1% → R% 转化为暴击伤害 (R 由 CRIT_CONVERT 控制, 默认6)
    excess = max(0.0, cr - 100.0)
    _cc = float(os.environ.get('CRIT_CONVERT', '6'))
    overflow = excess * _cc
    # ★★★ 2026-10-22: 爆伤减益(-300) 从【总额】扣，但有【下限 = 该单位白值爆伤】
    #   实证: ① 白雷 50白值+小红帽300 = 350 → 扣300 → 50 ✓
    #         ② 虚无之星反击那次(小红帽还没出手, 白值50) → 扣300 仍是 50
    #            → 反击暴击 ×1.5, 415%×93,375×0.75×1.5 = 431,583 ≈ 实战 433,619 ✓
    _cdfloor = float(u.get('cdmg0', 50.0) or 50.0)
    cd = max(_cdfloor, cd_base + cd_buff + overflow - _cdp)
    cd = min(10000.0, cd)                                # ★ 官方: 爆伤上限 10000%
    CRIT_PARTS[0] = (cr, cd)                             # 供 crit_roll 复用
    # ★★★ 2026-10-22 用户规则: 不要期望值！
    #   暴击率 < 100% → 按【不暴击】算（乘区 1.00）
    #   暴击率 >= 100% → 必暴击（乘区 1 + 爆伤/100）
    if u.get('_always_crit') or cr >= 100.0:
        return 1 + cd / 100.0
    return 1.0

CRIT_PARTS = [None]

def crit_roll(u, is_first, bless):
    # ★★ 2026-10-18 用户要求: 按真实暴击率随机
    #   例 cr=60 → random(1..100)：1~60 暴击, 61~100 不暴击
    #   暴击 → 1 + cd/100；不暴击 → 1.0
    #   cr >= 100 → 必定暴击 (溢出部分已在 crit_of 里转成爆伤)
    crit_of(u, is_first, bless)          # 先算一遍, 顺便填 CRIT_PARTS
    cr, cd = CRIT_PARTS[0]
    # ★★★ 2026-11-05 修复: ENEMY_ALWAYS_CRIT 标记在这里也必须生效
    #   旧实现只判断 cr>=100 → 敌方被「开启烟幕」扣到负数后【永远不暴击】
    #   实证: 微光s 蒼藍魔女 实战 3 段 23,554 / 25,909 / 28,268（全暴击）
    #         模型当时只给 1,711 / 2,830 / 3,087（全不暴击）→ 少算 8 倍
    if u.get('_always_crit'):
        return 1 + cd / 100.0
    if cr >= 100.0:
        return 1 + cd / 100.0
    if random.random() * 100.0 < cr:
        return 1 + cd / 100.0
    return 1.0

def panel_crit(u, bless):
    """开战后面板值（含慧眼如炬/杀戮斗魂，供回放显示用）
       ★ 与 crit_of 同口径，区别只是这里返回 (暴击率, 爆伤) 而不是暴击乘区
    """
    P = (u.get('suppressed', 0) or 0) / 100.0
    cr = u['cr'] + _sum_lv(bless, '慧眼如炬', {'I': 50, 'II': 90, 'III': 150}) * (1 - P)
    cd = u['cdmg'] + _sum_lv(bless, '杀戮斗魂', {'I': 300, 'II': 700}) * (1 - P)
    excess = max(0.0, cr - 100.0)
    cd = max(0.0, cd + excess * float(os.environ.get('CRIT_CONVERT', '6')) - float(u.get('_cd_pen', 0) or 0))
    return cr, min(10000.0, cd)


def dmg(u, tgt, rnd, is_second, bless, is_main=False,
        b0_ov=None, per_ov=None, hits_ov=None, no_chain=False, extra_base=0.0):
    # ★ 禁锢之力: 每层连锁的连锁伤害额外 +2%(I)/+5%(II) —— 基础是每层 +10%
    cbon = 0.10
    if has(bless, '禁锢之力'):
        cbon += (5 if lv_of(bless, '禁锢之力') == 'II' else 2) / 100.0
    # ★ 「敵人最大HP」基准对范围内每个目标都生效(堕落之星/泳池派对 的百分比伤害打满范围)
    # ★★ 2026-10-20 修正: 「自身最大HP」为基准的技能必须用 hpmax，不是当前 hp
    #   实证: 敌方恶作剧幽灵 40,618 血 → 8% = 3,249/段；
    #         旧实现取当时残血 1,012 → 只算出 191/段（用户实测首下 5,846，含盾转伤）
    b0 = b0_ov if b0_ov is not None else (
        hpbase(u) if u['basis'] == '自身最大HP' else (hpbase(tgt) if u['basis'] == '敵人最大HP' else u['atk']))
    # ★★ 2026-10-22 减攻击力/魔法力: 按【百分比】压低攻击者输出(乘法, 不是减法)
    #   只影响「以攻击力/魔法力为基准」的技能; HP 基准的技能不受影响
    # ★★★ 2026-10-24 用户实证公式: 恶灵「能量防卫」= 护盾×12%，这一部分
    #   ★必须★ 并入 b0，一起乘【暴击 × 防护罩 × 防御 × 减伤】
    #   用户给的公式: (50000×8% + 150000×12%) × 暴击(1+0.54) × 防护罩0.25 × 防御0.92
    #   → 旧实现把它加在减伤之后 → 少乘 0.25×0.92，伤害虚高约 4 倍
    # ★★★ CURSE_IN_DMG (2026-10-27 用户指出「是不是没算对面的诅咒」):
    #   极限诅咒I: 「所有敌人 所有能力值增益效果受到25%的压迫」
    #   → 庇佑给的 ATK% 也要 ×0.75（旧实现只压技能自身增益）
    #   实证: 我方海洋先锋 白值898 + 绑定的庇佑II(+300%)
    #         游戏面板 2,925 (=898×3.25, 即 300%→225%)
    #         模型 3,592 (=898×4.00, 没压) → 每段虚高 22.6%
    #   ★ 速战速决/乘胜追击 等【非能力值增益】不受压制（用户确认）
    if (u.get('basis') in ('自身攻擊力', '自身魔法力')):
        _ebl = u.get('_ebless') or []
        # ★★★ 2026-11-03 用户面板实证: 【删除】此处的攻击压制, 否则重复打折两次
        #   实证: 使者 手动算 面板攻击2554 ×700% ×6.722(爆伤572.2%) ×0.47(敌防53%) ×0.60(守护屏障II)
        #         = 33,890  ← 用户实战 33,889 ✅ (误差 0.003%)
        #         第二个目标(防45%): 17,878×6.722×0.55×0.60 = 39,660 ← 实战 39,658 ✅
        #   面板 2554 本身已是「极限诅咒压制后」的数值(开局 setup 已算过),
        #   此处再 ×0.75 → 2214 → 伤害少 25%, 与实战不符。
        if False and any(('诅咒' in str(x)) or ('詛咒' in str(x)) or ('压迫' in str(x)) or ('壓迫' in str(x))
                         for x in _ebl):
            _wa = u.get('_white_atk')
            if _wa:
                b0 = _wa + (b0 - _wa) * 0.75
                if DMG_DEBUG[0]:
                    print('         b0 ×0.75 (极限诅咒压制庇佑攻击力 %0.f→%.0f)' % (_wa + (b0 - _wa), b0))

    _adn = u.get('_atk_down_pct') or 0
    if _adn > 0 and u['basis'] in ('自身攻擊力', '自身魔法力'):
        b0 *= max(0.0, 1.0 - min(_adn, 100.0) / 100.0)
    # ★ 官方【固定伤害】(宿命之恩): 不能暴击、不吃易伤; 只跳过防御/魔抗+减伤技能; 其他都吃
    #   2026-10-17 用户确认: 宿命之恩 属于【固定伤害】类别
    # ★★ 赛季47: 士气削弱（对方庇佑）→ 我方 攻击力&魔法力 -50%，持续 2 回合
    # ★★★ 2026-10-23 用户重大修正: 言灵祝福【只免疫技能造成的弱化】，
    #     不免疫【庇佑】造成的弱化 → 士气削弱/开启烟幕/破甲/蔑视权能 照常生效
    if (rnd <= 2 and not _blk_bless_debuff(u)
            and u['basis'] in ('自身攻擊力', '自身魔法力') and has(u.get('_ebless') or [], '士气削弱')):
        b0 *= 0.5
        if DMG_DEBUG[0]:
            print('         b0 ×0.5 (士气削弱)')
    # ★★★ 2026-10-24 用户纠正: 【HP%基准技能不是固定伤害！会正常吃减伤】
    #   固定伤害只来自庇佑【宿命之恩】(所有友军造成的伤害变为固定伤害)
    fixed = has(bless, '宿命之恩')
    # ★★ 赛季47 死亡时间: 第5回合起 攻击力/魔法力 +100%/层（每2回合叠一层），固定伤害不吃
    _dt = (1 + (rnd - 5) // 2) if rnd >= 5 else 0
    if _dt and not fixed:
        b0 *= (1 + 1.0 * _dt)
        if DMG_DEBUG[0]:
            print('         b0 ×%.2f (死亡时间 攻魔+%d%%)' % (1 + 1.0 * _dt, 100 * _dt))
    # ★★ 赛季47: 开启烟幕（对方庇佑）→ 我方 暴击率-50、暴击伤害-300，持续 2 回合
    _yel = (rnd <= 2 and not _blk_bless_debuff(u)
            and has(u.get('_ebless') or [], '开启烟幕'))   # 先攻方言灵可免疫
    u['_cr_pen'] = 50.0 if _yel else 0.0
    u['_cd_pen'] = 300.0 if _yel else 0.0
    if fixed:
        _cm = 1.0
    elif os.environ.get('CRIT_RANDOM', '1') == '1':
        _cm = crit_roll(u, not is_second, bless)
    else:
        _cm = crit_of(u, not is_second, bless)
    # (极限诅咒的「压迫」已在开局按"只打折增益部分"修正过面板, 此处不再重复扣)
    if DMG_DEBUG[0]:
        print('      [乘区分解] %s -> %s' % (u['name'], tgt['name']))
        print('         b0(攻击/HP基准)=%.0f  hits=%s  per(倍率)=%.0f%%' % (b0, u['hits'], u['per']))
        if fixed:
            print('         [暴击] 固定伤害 → 不暴击，乘区=1.00')
        else:
            _crc, _cdc = CRIT_PARTS[0] if CRIT_PARTS[0] else (0.0, 0.0)
            _crit_full = 1 + _cdc / 100.0                      # 真暴击时的乘区
            print('         [暴击] 暴击率=%.1f%%  爆伤=%.1f%%  → 暴击时×%.2f / 不暴击×1.00  实际×%.2f' % (
                _crc, _cdc, _crit_full, _cm))
    _per = ((u.get('per_main') or u['per']) if is_main else u['per']) if per_ov is None else per_ov
    # ★★★ 2026-11-05: 「依自身持有的每一個血氣總量造成傷害」→ 倍率 × 当前层数
    if u.get('per_per_stack'):
        _bst = u.get('blood_stacks') or 0
        _per = _per * (max(1, _bst) if _bst > 0 else 1)
    _hits = u['hits'] if hits_ov is None else hits_ov
    base = b0 * _hits * _per / 100 * _cm
    # ★★★ 2026-10-24 用户实证公式（恶灵/任何「护盾转伤害」单位）:
    #   (最大生命×8% + 护盾×12%) × 暴击倍率 × 防护罩 × 防御 × 减伤
    #   → 护盾那部分【不乘 per】，但【必须】乘暴击/防御/防护罩/减伤
    if extra_base:
        base += extra_base * _hits * _cm
        if DMG_DEBUG[0]:
            print('         [能量防卫] +%.0f/段 (乘暴击×%.2f, 之后照常吃防御/防护罩/减伤)' % (extra_base, _cm))
    # ★ 极限诅咒「压迫」压制【所有增益效果】(慧眼/突袭/速战/先发/力量庇佑...)
    #   (2026-10-17 双面板+实战校准实证; GAIN_SUPPRESS=0 可关闭)
    _Pg = (u.get('suppressed', 0) or 0) / 100.0 if os.environ.get('GAIN_SUPPRESS', '1') == '1' else 0.0
    # (突袭准备已改为在 apply_bless 阶段加到 atk, 与魔法增强加法叠加; 2026-10-17)
    # ★★ 赛季47 改版: 威力增强 = 每回合开始时 +100%(I) / +200%(II)，最多叠 4 层（第1回合就叠1层）
    # ★★ 2026-10-22 用户纠正: 威力增强是【加到白值的百分比】, 不是伤害乘算
    #   → 已在 apply_bless + 每回合开始时累加进 _bm_atk（HP 基准技能不受影响）
    #   这里不再乘伤害
    # ★★★ 2026-11-06 删除: 物理增强 已统一到下面的循环里按【加法叠加 +200%】处理
    #   旧实现在这里额外 ×2.0，加上循环里再一次 → 物理系伤害虚高 3.5 倍
    # (魔法增强已改为 apply_bless 阶段加到 atk, 不再这里 ×2; 2026-10-17)
    # ★★ 2026-10-22: 旧的「第6回合起 ×2」已删除 —— 那是赛季46 对后期伤害暴涨的近似,
    #   赛季47 有正式【死亡时间】(第5回合起) 已在 dmg 里建模, 避免重复计算
    # ★ 官方公式(2026-10-17 用户核实): 属性克制【没有 ×1.5 倍率】!
    #   [属性伤害] 只有在属性克制时生效 → ×(1+属性伤害); 非克制时该项完全不存在
    if (u['attr'], tgt['attr']) in ADV:
        base *= (1 + u['admg'] / 100)
        if DMG_DEBUG[0]:
            print('         [属性] %s 克制 %s → ×(1+属性伤害%.0f%%)=%.2f' % (u['attr'], tgt['attr'], u['admg'], 1 + u['admg'] / 100))
    elif DMG_DEBUG[0]:
        print('         [属性] %s vs %s 非克制 → 属性伤害不生效(×1.00)' % (u['attr'], tgt['attr']))
    # ★ 连携上限 = 100 层 (每层 +10% → 满层 +1000%) —— 2026-10-17 用户确认
    #   (旧值 999 = 无上限; 逐个击破 单独封顶 2 层)
    cap = 2 if has(bless, '逐个击破') else 100
    if not no_chain:                              # ★ 反击不吃连锁加伤
        # ★★ 2026-10-18 用户规则: 连锁与脆弱【相加】进同一个乘区
        #   第2下 = ×(1 + 0.1连锁 + 0.75脆弱)
        _vulb = 0.0
        if u['type'] == '物' and (tgt.get('vul_phys_left') or 0) > 0:
            _vulb = (tgt.get('vul_phys_amt') or 0) / 100.0
        elif u['type'] == '魔' and (tgt.get('vul_magic_left') or 0) > 0:
            _vulb = (tgt.get('vul_magic_amt') or 0) / 100.0
        _cbon2 = cbon + (tgt.get('chain_add_pct') or 0) / 100.0 + (u.get('chain_extra_pct') or 0) / 100.0
        # ★ 2026-11-03: chain_extra_pct = 攻击者自身的「連鎖强化」层数加成
        #   (莎赫拉查德·泳池派對 爆发3: 6回合 1层连锁强化)
        _comb = 1 + _cbon2 * min(tgt['chains'], cap) + _vulb
        base *= _comb
        if DMG_DEBUG[0]:
            print('         ×连锁+脆弱 (1+%.3f×%d+%.2f)=%.3f  [chains=%s cap=%s vul_phys=%s vul_magic=%s]' % (cbon, min(tgt['chains'], cap), _vulb, _comb, tgt.get('chains'), cap, tgt.get('vul_phys_amt'), tgt.get('vul_magic_amt')))
    # ★★★ 2026-10-19 用戶確認(游戲描述寫明「持續1個回合」):
    #   魔法增强(魔法力+100/200%) 與 物理增强 【僅第1回合】生效，之前被錒成永久了
    if rnd == 1:
        for _nm, _ty in (('魔法增强', '魔'), ('物理增强', '物')):
            if has(bless, _nm):
                _lv = lv_of(bless, _nm)
                # ★★★ 2026-11-06 用户面板实证: 魔法增强 = 魔法力 【+200%】(不是+100%)
                #   实证: 致命之眼 白值1138, 带 和谐庇佑II(300)+魔力庇佑(350)+魔法增强(200)
                #         面板 8439 = 1138 × (1+850%×0.75) = 8393 ✓ (若按+100%只有7539 ✗)
                # ★ 数据: 魔法增强 = 魔法力+200%, 物理增强 = 攻击力+200%（都是1点, 单级）
                _v = 200 if _nm in ('魔法增强', '物理增强') else 0
                # ★★★ 2026-10-19 實測: 按【敵人最大生命】算傷害的技能
                #   不吃任何攻擃力/魔法力增益 (因為傷害跟自身攻擃力無關)
                #   實證: 墮落之星打死亡之夜 實戰 32,632 / 35,895
                #         14,504 × 90% × 2.5 = 32,634 ✅ (不乘魔法增強的 1.75)
                _is_hp_basis = ('最大HP' in (u.get('basis') or '')) or ('生命' in (u.get('basis') or ''))
                if _v and (not _is_hp_basis) and (u.get('type') or '').startswith(_ty):
                    # ★★ 2026-10-19 用戶實測: 魔法/物理增強屬於【能力值增益】→ 吃極限诅咒壓制
                    #   實證: 魔女打幽靈 實戰 20,390; 模型滿額算 23,289
                    #         1109 × 4.20 × 1.75(被壓) × 2.5 = 20,378 ✅
                    _P = (u.get('suppressed', 0) or 0) / 100.0
                    _ve = _v * (1 - _P)
                    # ★★★ 2026-11-06 用户面板实证: 魔法增强必须与 和谐的庇佑/魔力庇佑
                    #   【加法叠加】(同为"攻击力/魔法力%"), 不能当成独立乘区
                    #   实证: 白值1138, 和谐庇佑II300 + 魔力庇佑350 + 魔法增强200
                    #         压制25% → 1138×(1+850%×0.75)=8393 = 面板8439 ✓
                    #   若按独立乘区: 6686×2.5=16715 → 伤害变成 2 倍 ✗
                    _bm = float(u.get('_bm_atk') or 0.0)
                    _ratio = (1.0 + (_bm + _ve) / 100.0) / (1.0 + _bm / 100.0) if _bm > -100 else 1.0
                    base *= _ratio
                    if DMG_DEBUG[0]:
                        print('         ×%s +%d%%(压制后+%.0f%%) 加法并入攻魔 → ×%.3f' % (
                            _nm, _v, _ve, _ratio))
    # ★ 速战速决: 第1回合 攻击连携<5 敌人 伤害+150%
    #   ★ 2026-10-17: 「增伤」不属于能力值 → 不吃极限诅咒压迫 (SPEED_SUPPRESS=1 可切回旧行为)
    #   实证: 医护兵/魔女四击同时对上, 需要 ×2.5(不压) 而非 ×2.125
    # ★★★ 2026-10-24 用户实证(最终): 速战速决是【每段重新判定】连锁<5
    #   实战第6段(连锁=5)伤害腰斩 ✓ 所以按当前连锁判定, 不能用行动开始时的值
    if has(bless, '速战速决') and tgt.get('chains', 0) < 5:
        _sm = float(os.environ.get('SPEED_MULT', '2.5'))
        if os.environ.get('SPEED_SUPPRESS', '0') == '1':
            _sm = 1 + (_sm - 1) * (1 - _Pg)
        base *= _sm
        if DMG_DEBUG[0]:
            print('         ×速战速决 %.2f' % _sm)
    # 敌方脆弱(由对方庇佑挂的, ★有回合数) —— ★固定伤害不吃易伤
    if not fixed:
        # ★★ 赛季47: 苟延残喘(物理虚弱) / 抗性弱化(魔法虚弱) = 每回合开始 +50%，最多叠3层
        #   (旧实现是固定 ×1.5 持续6回合 → 已改)
        if tgt.get('vul_phys', 0) >= rnd and u['type'] == '物':
            base *= (1 + 0.5 * min(rnd, 3))
        if tgt.get('vul_magic', 0) >= rnd and u['type'] == '魔':
            base *= (1 + 0.5 * min(rnd, 3))
    if has(bless, '先发制人') and tgt['hp'] >= tgt['hpmax'] * 0.9:
        # ★ 2026-10-26 用户纠正: 先发制人是【条件增伤/乘区】, 不是能力值增益
        #   → 和速战速决一样【不吃】极限诅咒压迫 (旧实现错乘了 (1-_Pg))
        base *= 1.5
    if has(bless, '乘胜追击') and tgt['hp'] <= tgt['hpmax'] * 0.9:
        base *= 1.5
    # (极限诅咒已改为在 dmg 开头压制"攻击者自身"的b0, 此处不再处理)
    if not fixed:
        # ★★ 2026-10-18 用户给出正确公式: 减伤 = 线性 (1 - 魔抗/100)
        #   1109 × 5.8 × (1-0.454) = 3,512 = 实战 3,511 ✓
        # ★★ 赛季47: 破甲（对方庇佑）→ 目标 防御-30、魔抗-30，持续 2 回合
        _brk = 30 if (rnd <= 2 and not _blk_bless_debuff(tgt)
                      and has(tgt.get('_ebless') or [], '破甲')) else 0
        # ★★ 赛季47 死亡时间: 防御力/魔法抵抗 -100%/层
        _dtd = 100 * _dt
        # ★ 防御/魔抗最低为 0（不会变负数，否则 (1-dr) 会被放大得离谱）
        dr = max(0.0, (tgt['def'] if u['type'] == '物' else tgt['mr']) - _brk - _dtd) / 100
        # ★★ 2026-10-22: 旧的「第6回合起防御归零」已删除（改由死亡时间的防御-100%/层 处理）
        # ★★★ 2026-11-03 用户实战: 「按最大HP百分比」的伤害【不吃减伤】
        #   实证: 自然爪(#3) 一刀 125%最大生命 → 秒杀我方惡魔之女(46,063血)
        #     带自然爪#3的两队(冷紫凝2700/久岛鸥归来2705) 我们都输
        #     带自然爪#5的대디(2576, 它最后出手) 我们赢
        #   环境变量 HP_IGNORE_RED=1 开启(默认开)
        _hpb = ('最大HP' in (u.get('basis') or '')) and os.environ.get('HP_IGNORE_RED','0')=='1'
        if not _hpb:
            base *= max(0.0, 1 - min(dr, 0.9))
            base *= (1 - tgt['skillred'])
        # (_hpb=True 时既不吃防御也不吃减伤: 125%最大生命 = 必杀)
    else:
        dr = 0.0
        # ★ 固定伤害(宿命之恩): 只跳过 防御/魔抗 + 减伤技能; 属性抵抗属于"其他", 照吃
    # ★ 属性抵抗: 【只有属性被克制时】才生效(官方公式) —— 固定伤害同样吃
    if (tgt['attr'], u['attr']) in ADV:
        # ★★ 2026-10-22 用户规则: 防御力 / 魔法抵抗 / 属性抵抗 【最低为 0，不会负数】
        #   → 上限 90%、下限 0
        _pres = min(max(tgt.get('pres', 0) or 0, 0.0), 90.0)
        base *= max(0.0, 1 - _pres / 100.0)
        if DMG_DEBUG[0]:
            print('         [属性抵抗] 目标 %s 抵抗 %s = %.0f%% → ×%.2f' % (tgt['attr'], u['attr'], _pres, max(0.0, 1 - _pres / 100.0)))

    if DMG_DEBUG[0]:
        _dname = '防御' if u['type'] == '物' else '魔抗'
        _dval = tgt['def'] if u['type'] == '物' else tgt['mr']
        print('         [%s] 目标%s=%.0f → 减伤%.0f%% → ×%.2f%s' % (
            _dname, _dname, _dval, min(dr, 0.9) * 100, 1 - min(dr, 0.9),
            '  [固定伤害跳过]' if fixed else ''))
        print('         [技能减伤] %.0f%% → ×%.2f' % (tgt['skillred'] * 100, 1 - tgt['skillred']))
        print('         [防护罩] prot=%.0f%% 剩余=%s 回合' % ((tgt.get('prot') or 0)*100, tgt.get('prot_left')))
        print('         => 全部段合计=%.0f, 每段=%.0f' % (base, base / max(1, u['hits'])))
    # ★★ 2026-10-22: 旧的「第6回合起 ×1.5」已删除（改由死亡时间的 受伤+50%/层 处理）
    # ★ 蔑视权能: 第2回合起给「对面全队」+100% 虚弱(受伤 ×2)  —— 2026-10-18 用户修正
    #   (原实现按 +30%(I)/+60%(II) 算, 是错的; 该庇佑只有1级)
    #   (官方文案为通用"虚弱", 与 苟延残喘/抗性弱化 的"物理脆弱/魔法脆弱"区分开) —— 易伤类, 固定伤害不吃
    # ★★ 赛季47 改版: 蔑视权能 = 每回合开始时给全体敌人 +50% 虚弱，最多 6 层（第1回合就 +50%）
    # ★★★ 2026-10-22 用户确认: 「虚弱」属于【弱化】→ 言灵祝福免疫
    # ★ 庇佑类虚弱: 只有先攻方的言灵祝福能免疫
    # ★★★ TAUNT_MASTER (2026-10-27): 挑衅大师 = 对【挑衅状态】的敌人伤害 +100%/层, 最多3层
    #   官方: 「所有友軍 對挑釁狀態下的敵人造成的傷害提高100%（最多疊加3層）」
    #   层数按「对挑衅目标的累计命中次数」递增（每命中一次 +1 层，封顶 3）
    if has(bless, '挑衅大师') and tgt.get('taunt'):
        _tl = min(3, int(tgt.get('_tauntmaster_layers') or 0))
        tgt['_tauntmaster_layers'] = min(3, _tl + 1)
        base *= (1.0 + 1.0 * _tl)
        if VERBOSE[0]:
            print('         ×挑衅大师 %d层 =%.2f' % (_tl, 1.0 + 1.0 * _tl))

    if has(bless, '蔑视权能') and not fixed and not _blk_bless_debuff(tgt):
        _ly = min(rnd, 6)
        base *= (1 + 0.5 * _ly)
        if DMG_DEBUG[0]:
            print('         ×蔑视权能 50%%×%d层 =%.2f' % (_ly, 1 + 0.5 * _ly))
    # ★ 虚弱(目标身上的脆弱层数): 每层 +脆弱% 受伤, 叠加(例 奇蹟海洋 8层×50% = +400%)
    _vs = tgt.get('vuln_stacks') or 0
    if _vs > 0 and (tgt.get('vuln_pct') or 0) > 0 and not fixed:
        base *= 1 + _vs * (tgt['vuln_pct'] / 100.0)
        if DMG_DEBUG[0]:
            print('         ×虚弱 %d层 ×%.2f' % (_vs, 1 + _vs * tgt['vuln_pct'] / 100.0))
    # ★ 集中射击庇佑的虚弱(外部挂的, 目标受伤 +100%) —— 易伤类
    if tgt.get('ext_vuln') and not fixed:
        base *= 1 + tgt['ext_vuln'] / 100.0
    # ★★★ 2026-11-05: 「攻擊處於持續傷害狀態的敵人時，造成的傷害增加X%」(增強)
    #   例 斐傑·背叛之夜 burst Lv2 → 打有出血的目标 +50%
    if (u.get('dot_amp_pct') or 0) > 0 and (tgt.get('bleed_left') or 0) > 0:
        base *= (1 + float(u['dot_amp_pct']) / 100.0)
        if DMG_DEBUG[0]:
            print('         ×增強(目标有持续伤害) (1+%.0f%%)' % float(u['dot_amp_pct']))
    # ★★ 技能施加的物理/魔法脆弱 → 已在上面【与连锁相加】进同一个乘区(第285~292行)
    #   2026-10-18: 此处不再单独相乘，否则会乘两次

    # ★ 防護罩(目标身上的百分比减伤, 与防御乘法): 奇蹟海洋等
    # ★ 2026-10-17 实测校准: 技能自带防护罩【不吃】极限诅咒压迫 (PROT_SUPPRESS=1 可切换)
    #   实证 vs 예카테리나(16244556) 后攻: 防护罩50% → 47,153 vs 实战 48,428 = -2.6% ✓
    #   若改成吃压迫(37.5%) → 58,942 = +21.7% ✗
    _pp = (tgt.get('prot') or 0) * (1 - (tgt.get('suppressed', 0) or 0) / 100.0) \
        if os.environ.get('PROT_SUPPRESS', '0') == '1' else (tgt.get('prot') or 0)
    # ★★★ 2026-10-24 用户纠正: 【固定伤害】无视防护罩
    #   「对面有固定伤害的庇佑，打我们，所以防护罩没用」
    # ★★★ 2026-11-04 修正: 「物理防护罩」只减【物理】伤害，「魔法防护罩」只减魔法
    #   实证依据(用户截图): 拉德爾·暗黑騎士「对自己应用60%的物理防护罩效果」
    #   旧实现对所有伤害一律 ×(1-60%) → 对魔法队被严重高估
    _pk = tgt.get('prot_kind') or 'all'
    _pk_ok = (_pk == 'all' or (_pk == 'phys' and u['type'] != '魔')
              or (_pk == 'magic' and u['type'] == '魔'))
    if (tgt.get('prot_left') or 0) > 0 and _pp > 0 and not fixed and _pk_ok:
        base *= (1 - _pp)
        if DMG_DEBUG[0]:
            print('         ×防護罩[%s] (1-%.0f%%)=%.2f' % (_pk, _pp * 100, 1 - _pp))
    # ★ 挑衅大师: 对处于「挑衅/集中射击印记」状态的目标, 伤害 +100%  (2026-10-18 用户确认: 只有1级, 无+200%)
    #   (与 集中射击庇佑 是配套 combo: 先挂印记集火, 再吃这个增伤)
    if (tgt.get('focus') or tgt.get('taunt')) and has(bless, '挑衅大师'):
        # ★★ 赛季47 用户确认(2026-10-22): 每回合开始自动叠一层
        #   → 第1回合 +100%、第2回合 +200%、第3回合 +300%（最多3层）
        base *= (1 + 1.0 * min(rnd, 3))
    #   对面伤害 ×1.01、我方伤害 ×0.99  —— 抵消模型残留误差
    # ★★ 赛季47 死亡时间: 受到伤害 +50%/层（固定伤害不吃）
    if _dt and not fixed:
        base *= (1 + 0.5 * _dt)
    if not fixed:
        if u.get('side') == 'D':
            base *= float(os.environ.get('ENEMY_DMG_MULT', '1.01'))
        elif u.get('side') == 'A':
            base *= float(os.environ.get('MY_DMG_MULT', '0.99'))
    return base

# ★ 2026-10-16 重写: 对位/几何检索(原实现只按出手顺序选人, 无对位概念)
# 规则: 正对面=同(行,列) → 下面一格(朝前排) → 上面一格(朝后排) → 换列;
#       回避/突袭准备不可被选中(全场仅剩时可被选); 跳過=同列从敌方后排向前扫
from _targeting import pick

def basic_attack(u, enemies, allies, rnd, is_second, bless):
    """★★ 2026-10-20 用户纠正: 被沉默 ≠ 不能行动
       沉默只是【不能施放技能】，仍然可以【普攻】
       普攻 = 1段 × 自身攻击力100%（不吃技能倍率/不走技能效果）
    """
    alive = [e for e in enemies if e.get('alive')]
    if not alive:
        return
    # ★★★ TAUNT_IN_BASIC (2026-10-27 用户指出):
    #   「被沉默→普攻」原来直接取最前方，【完全忽略嘲讽】
    #   → 先锋斗魂的嘲讽对沉默普攻失效（实测打到苍蓝魔女而不是#1海边度假）
    #   嘲讽优先级：嘲讽单位中最先挂上的优先（TAUNT_SEQ 小者）
    _taunted = [e for e in alive if e.get('taunt')]
    if _taunted:
        _taunted.sort(key=lambda e: (e.get('taunt_seq') or 0))
        tgt = _taunted[0]
    else:
        # 最前方 = 行号最小，再按列
        tgt = min(alive, key=lambda e: pos2rc(e.get('pos') or 0))
    # ★★★ 2026-10-23 修 BUG: 普攻必须用【攻击力/魔法力】当基准,
    #   不能用技能自带的基准（医护兵是「自身最大HP」基准 → 普攻打出 25万，严重虚高）
    d = dmg(u, tgt, rnd, is_second, bless, True, per_ov=100.0, hits_ov=1,
            no_chain=True, b0_ov=u['atk'])
    s = min(tgt['shield'], d) if tgt['shield'] > 0 else 0.0
    tgt['shield'] -= s
    tgt['hp'] -= (d - s)
    if VERBOSE[0]:
        print('  ▶ %s 被沉默→普攻 %s 吃 %.0f 伤害, HP→%.0f' % (
            u['name'], tgt['name'], d, max(0.0, tgt['hp'])))
    if tgt['hp'] <= 0:
        if tgt.get('revive_left', 0) > 0:
            tgt['revive_left'] = 0
            tgt['hp'] = tgt['hpmax'] * (tgt.get('revive_pct', 100) / 100.0)
            if VERBOSE[0]:
                print('      [复活] %s 以 %.0f 血复活' % (tgt['name'], tgt['hp']))
        else:
            tgt['hp'] = 0
            tgt['alive'] = False

def _run_counter(t2, u, d, allies, rnd, to_dispel, died=False):
    """反击结算（每段命中触发一次）

    ★ 2026-10-22 用户确认的三条规则:
      ① 攻击被【闪避】时，反击【照样触发】
         （受到傷害基准 → 反 0；自身攻擊力/最大HP 基准 → 照常满伤害）
      ② 反击者被【沉默】不影响已挂上的反击（沉默只封新技能施放）
      ③ 带【永恒祝福】不会被驱散 → 反击照常触发
    """
    c = t2.get('counter')
    if not c or died:
        return
    if to_dispel and not has(t2.get('_tbless') or [], '永恒祝福'):
        return                                  # 驱散把反击解掉了
    if (t2.get('counter_left') or 0) <= 0:
        return
    if c.get('hits') is not None and t2.get('counter_used', 0) >= c['hits']:
        return
    t2['counter_used'] = t2.get('counter_used', 0) + 1
    tb = t2.get('_tbless') or []
    # ★ 官方【反击】: 不吃连锁加伤, 其他都吃(能暴击/吃易伤/属性伤害/减伤/属性抵抗)
    if c['basis'] == '受到傷害':
        _b0, _per = d * c['pct'] / 100.0, 100.0
    elif c['basis'] == '自身最大HP':
        _b0, _per = hpbase(t2), float(c['pct'])
    else:
        _b0, _per = None, float(c['pct'])
    for v in (allies if c['all'] else [u]):
        if not v['alive']:
            continue
        cd2 = dmg(t2, v, rnd, t2.get('order_is_second', False), tb,
                  b0_ov=_b0, per_ov=_per, hits_ov=1, no_chain=True)
        if VERBOSE[0]:
            print('      [反击] %s → %s 吃 %.0f (b0=%s per=%s)' % (
                t2['name'], v['name'], cd2, _b0 if _b0 else 'ATK', _per))
        # ★★★ 2026-10-31 修正: 按游戏内庇佑文案
        #   逆转权能I = 反击伤害 +250% / 逆转权能II = +600%
        #   (旧代码写的 I+100 / II+250 / III+400 是过期数值，少算 2.4 倍)
        if has(tb, '逆转权能'):
            lvv = lv_of(tb, '逆转权能')
            cd2 *= 1 + (600 if lvv == 'II' else 250 if lvv == 'I' else 400) / 100.0
        vs = min(v['shield'], cd2) if v['shield'] > 0 else 0
        v['shield'] -= vs
        v['hp'] -= (cd2 - vs)
        if v['hp'] <= 0:
            v['hp'] = 0
            v['alive'] = False


def act(u, enemies, allies, rnd, is_second, bless):
    # ★★ 2026-10-20 用户规则: 技能自带增益【出手时才应用】(先放技能才有),
    #    并且应用在伤害之前 → 第一下就按加成后的面板算
    # ★★★ 2026-10-22 用户实测: 自身增益可【叠加】(白雷「最多可賦予疊加至2」)
    #   第1回合 +150%，第2回合再 +150% → 共 +300%（旧实现只应用一次）
    if u.get('self_buff'):
        _maxst = int(u.get('sb_stack_max') or 1)
        _cur = int(u.get('_sb_stacks') or 0)
        if _cur < _maxst:
            u['_sb_stacks'] = _cur + 1
            _P = (u.get('suppressed', 0) or 0) / 100.0
            for _tag, _v in u['self_buff']:
                _apply_stat(u, _tag, _v * (1 - _P))
            if VERBOSE[0]:
                print('      [自身增益] %s 应用 %s (第%d/%d层, 压迫抵挡%.0f%%)' % (
                    u['name'], u['self_buff'], u['_sb_stacks'], _maxst, _P * 100))
    # ★★★ 2026-10-30 用户确认: 回歸偶像「4回合回避目标」是【施放技能时】才套上
    #   （突袭准备是庇佑, 开局就有; 回歸偶像要等她出手）→ 记下施放回合
    if (u.get('name') or '').startswith('Yuri'):
        u['untarg_from'] = rnd
        u['untarg'] = 1          # ★ 施放当刻【立刻】不可被选中（之前只记回合数，漏了即时生效）
        if VERBOSE[0]:
            print('      [回避目标] %s 施放 → %d~%d 回合不可被选中' % (u['name'], rnd, rnd + 3))
    # ★ 闪避要「放了技能」才生效: 该单位首次行动(施放技能)时才获得 N 次免疫。
    #   不放技能 → 第一次攻击就能打到; 获得后每次命中消耗 1 次, 需多段才能打穿。
    # ★★ 2026-10-19 用户实测: 闪避「不会到下一回合就没了」，而是每次施放技能都重置回满
    #   实证: 悠丝缇亚·泳池派对的 7 次闪避一直延续, 下回合放技能又刷新回 7 次
    if u.get('dodge_max'):
        u['dodge'] = u['dodge_max']
        u['dodge_granted'] = True
    # ★ 服装自带嘲讽: 施放技能时对自身挂挑衅 N 回合, 当回合立即生效
    #   (例: 葛兰西特·回归偶像 / 萊克莉斯·殺人娃娃 → 敌方全体被迫打他)
    if u.get('taunt_n'):
        u['taunt_left'] = u['taunt_n']
        u['taunt'] = True
        # ★ 记录施放序号: 多个嘲讽同时在身时, 打【最近施放】的那个(用户确认)
        TAUNT_SEQ[0] += 1
        u['taunt_seq'] = TAUNT_SEQ[0]
        if VERBOSE[0]:
            print('      [嘲讽] %s 施放挑衅(%d回合)' % (u['name'], u['taunt_n']))
    # ★ 复活: 施放技能时对自己挂复活 buff N 回合（必须先放技能才有, 不是开局自带）
    #   规则（用户确认 2026-10-17）:
    #     1. 复活后身上所有效果全清（挑衅/护盾/增益都清）
    #     2. 只挡「一次攻击」—— 多段伤害第N段打死→复活→第N+1段继续打(能彻底打死)
    #     3. 被驱散 → 复活 buff 消失, 无法复活
    if u.get('revive_pct'):
        u['revive_left'] = u.get('revive_turns', 4)
        if VERBOSE[0]:
            print('      [复活] %s 获得复活效果(%d回合, 复活后%.0f%%血)' % (
                u['name'], u['revive_left'], u['revive_pct']))
    # ★ 反击: 施放技能后才激活(用户确认: 「反击也是释放技能以后才会反击」)
    #   N 回合内每次受到攻击进行反击; 回合数按激活后递减
    if u.get('counter_skill'):
        u['counter'] = dict(u['counter_skill'])
        u['counter_left'] = u['counter_skill'].get('turns') or 4
        u['counter_used'] = 0
        if VERBOSE[0]:
            print('      [反击] %s 获得反击效果(%d回合)' % (u['name'], u['counter_left']))
    # ★ 防護罩(百分比减伤): 施放技能时对自身套用 N 回合(例 奇蹟海洋 50%×6回合)
    #   ★ 技能自带减伤【不被诅咒压】(堕落之星50%实战反推不压; 2026-10-17)
    #   ★ 2026-10-17 用户确认: 对面每回合都会重新施放技能 → 每次施放都【刷新】持续回合
    # ★★★ 2026-11-06: 「對我軍套用X%的減傷」→ 给全体友军（海倫娜·頂尖偶像 50%+潜能20%=70%）
    #   旧实现只给自己 → 敌方团队减伤完全丢失 → 我方伤害虚高一倍
    if (u.get('prot_pct') or 0) > 0:
        _ptgts = [a for a in allies if a.get('alive')] if u.get('prot_allies') else [u]
        for _a in _ptgts:
            _a['prot'] = u['prot_pct'] / 100.0
            _a['prot_left'] = u['prot_turns'] or 4
        if VERBOSE[0] and u.get('prot_allies'):
            print('      [护盾/减伤] %s → 我军全体 减伤%.0f%% (%d回合)' % (
                u['name'], u['prot_pct'], u['prot_turns'] or 4))
    # ★★ 技能护盾(能量防卫): 每回合施放给自身, 数值同样吃暴击/爆伤
    #   ★ 2026-10-17: 加回合数限制(爱丽丝「2回合內」/安卓女王「4回合期間」)
    #   ★★ 2026-10-18 重大修正: 必须放在 `if not tgt: return` 【之前】!
    #      自目标技能(爱丽丝/安卓女王/悠丝缇亚)的 pick() 返回 None → 提前 return
    #      → 之前的护盾代码根本执行不到 → 这些单位的护盾完全没生效
    # ★★★ 2026-11-05 新增: 血氣叠层（斐傑·背叛之夜 Valze_1）
    #   每次施放 +blood_gain 层（上限 blood_max）；攻击伤害在 dmg() 里按层数放大
    #   ★ 必须在【伤害之前】加层，否则第一回合吃不到自己的层数
    if (u.get('blood_gain') or 0) > 0:
        _bmax = u.get('blood_max') or 20
        u['blood_stacks'] = min(_bmax, (u.get('blood_stacks') or 0) + int(u['blood_gain']))
        if VERBOSE[0]:
            print('      [血氣] %s 叠层 → %d (上限%d)' % (u['name'], u['blood_stacks'], _bmax))
    # ★★ 2026-10-22: 「对我军」增益 —— 施放技能时给全体友军（含自己），只给一次
    if (u.get('team_buff') or []) and not u.get('_tb_applied'):
        u['_tb_applied'] = True
        for _a in allies:
            _Pa = (_a.get('suppressed', 0) or 0) / 100.0
            for _tag, _val in u['team_buff']:
                # ★★★ 2026-11-03 用户双截图实证(小紅帽放技能 前/后 的使者面板):
                #   前: 暴击率 60.00%  爆伤 347.20%
                #   后: 暴击率 97.50%  爆伤 572.20%
                #   差值 = +37.5 / +225 = 标称(+50/+300) × 0.75
                #   → 对方带「极限诅咒I」时,「我军增益」的 CR/CDMG 同样被压 25%
                #   → 且压制后 CR=97.5 < 100, 不应再走「溢出转爆伤」那一段
                #   (旧实现: 未压制 → CR 110/爆伤 707.2%, 使者伤害虚高 2.6 倍)
                if _tag in ('CR', 'CDMG') and _Pa > 0:
                    _v2 = float(_val) * (1 - _Pa)
                    if _tag == 'CR':
                        _a['cr'] = _a.get('cr', 0.0) + _v2
                    else:
                        _a['cdmg'] = _a.get('cdmg', 0.0) + _v2
                    continue
                try:
                    _apply_stat(_a, _tag, _val)
                except Exception:
                    pass
        if VERBOSE[0]:
            print('      [我军增益] %s → 全体 %s' % (u['name'], u['team_buff']))
    if u.get('shield_pct'):
        b = hpbase(u) if u.get('shield_basis') == 'HP' else u['atk']   # ★ 50000 封顶
        # ★★ 2026-10-18 修正: 护盾不吃暴击! (旧实现乘了 crit → 虚高 5.4 倍)
        #   实证: GIJoe 的爱丽丝 实际 12,695血+1,036盾, 模型算成 13,279+9,098盾
        _amt = b * u['shield_pct'] / 100.0
        # ★★ 2026-10-22: 技能写「对我军套用」→ 护盾给全体友军（鲁·小红帽）
        if u.get('_shield_granted') and not u.get('shield_allies'):
            _tg = []          # ★ 受击时已给过，不重复
        else:
            u['_shield_granted'] = True
            _tg = allies if u.get('shield_allies') else [u]
        for _x in _tg:
            # ★★★ 2026-10-22 用户纠正: 护盾是【叠加】的，不是取最大值
            #   实证: 赛尔 生命结界I(75,000) + 小红帽(64,683) = 139,683 ≈ 15万
            #   (旧实现 max() → 只算 75,000 → 少一大截)
            _x['shield'] = _x.get('shield', 0.0) + _amt
            _x['skill_shield_amt'] = _amt
            _x['shield_left'] = u.get('shield_turns') or 4
        if VERBOSE[0]:
            if u.get('shield_allies'):
                print('      [护盾] %s → 我军全体获得能量护盾 %.0f (%d回合)' % (
                    u['name'], _amt, u.get('shield_turns') or 4))
            else:
                print('      [护盾] %s 获得能量护盾 %.0f (%d回合)' % (u['name'], _amt, u['shield_left']))
    tgt = pick(u, enemies)
    if not tgt:
        return
    # ★ 沉默: 使主目标 N 回合无法施放技能; 言灵祝福 可免疫沉默
    if u.get('silence') and not has(tgt.get('_tbless') or [], '言灵祝福'):
        tgt['silenced'] = max(tgt.get('silenced', 0), u['silence'])
    to_dispel = u.get('dispel', False)
    # ★★★ 2026-10-30 用户确认: 回歸偶像(尤里)的「4回合回避目标」是【施放后】才生效
    #   与突袭准备不同(突袭准备是庇佑, 开局就生效)
    _uf0 = u.get('untarg_from')
    u['untarg'] = 1 if (
        (u['order'] == 3 and has(bless, '突袭准备') and rnd <= 4)
        or (_uf0 is not None and _uf0 <= rnd <= _uf0 + 3)
    ) else 0
    chain_add = 5 if lv_of(bless, '桎梏之链') == 'II' else 2 if has(bless, '桎梏之链') else 1

    # ★ 技能范围(AOE): 以主目标为原点, 按掩码取所有命中的敌人
    #   (含「回避/突袭准备」保护的单位 —— 打别人时扫到照样吃伤害)
    def pnum(p):
        v = re.sub(r'\D', '', str(p))
        return int(v) if v else 0
    # ★★ 2026-10-19 用户實測: 【跳過型】的掩碼錧點 = 【攻擃者自身】, 不是主目標!
    #   實證: 敵·海邊度假(跳過) 位於第3行第3列, 打中
    #         泳池派對(0,+2) / 死亡之夜(+1,-1) / 白雷(-1,0) —— 全都是對「自身」的偏移
    #   舊實作錧在主目標上 → 只打中 1 人
    # ★★ 2026-10-19 用戶確認: 「跳過 / 越過」= 範圍内跳過最前排那個, 打它後面的
    # ★★ 2026-10-19 實測約束: 掩碼錧點 = 【主目標】(不分是否跳過型)
    #   實證 vs 效度幽靈: 我方海邊度假(主目標=醫護兵 第4行第1列)
    #         實戰只打中 醫護兵 + 泳池派對, 沒打到天御鳥命
    #   之前為了對上另一場改成「攻擃者自身」是錯的
    tg, tc = pos2rc(pnum(tgt['pos']))
    targets = []
    # ★ 掩码约定是 [行偏移, 列偏移](例 代号O 的 [[-3,0]…[3,0]] = 同一列上下 7 格, 竖线)。
    #   旧实现按 [列,行] 解 → 竖线变横线, AOE 只扫到 1 人(实战应串杀同列 3 人)。
    for dr, dc in (u.get('shape') or [[0, 0]]):
        rr, cc = tg + dr, tc + dc
        # ★★★ 2026-10-24 用户指出: 原先限制 rr<=3 → 【范围打不到第5行(后排)】
        #   实证: 敌 医护兵(1段90%) 从 我恶灵(第4行第1列) 展开掩码, 应该连 我堕落之星(第5行第1列) 一起打
        #        旧实现只打到 1 人 → 少了个人
        if not (0 <= rr < S47_ROWS and 0 <= cc < S47_COLS):
            continue
        for e in enemies:
            ep = pnum(e['pos'])
            if e['alive'] and pos2rc(ep) == (rr, cc) and e not in targets:
                targets.append(e)
    if not targets:
        targets = [tgt]
    # ★★ 2026-10-20: 【额外效果】减抗的「第几下生效」计数器(每次行动重置)
    for _e in enemies:
        _e['_hitn'] = 0
    # ★★ 2026-10-19 用户实测: 【跳過 / 越过】= 范围内跳过最前排(row0)那个单位，打它后面的
    #   实证: 敌·海邊度假(跳過) 时我方墮落之星, 她跳过第1行的魔女,
    #         打中 泳池派對(第3行) / 死亡之夜(第4行) / 白雷 / 海邊度假(第2行)
    #   旧实现把最前排也打进去 → 多死单位、判错胜负


    # ★ 2026-11-07 用户要看范围命中名单（对照实战）→ 多目标时在日志里列出来
    if VERBOSE[0] and len(targets) > 1:
        print('      [范围] %s 命中 %d 人: %s' % (
            u['name'], len(targets), '、'.join(x['name'] for x in targets)))
    if os.environ.get('AOE_DEBUG') == '1':
        print('      [AOE] %s 主目标=%s(pos%s) 命中=%s' % (
            u['name'], tgt['name'], tgt.get('pos'), [x['name'] for x in targets]))

    def strike(t2, is_main=False):
        if not t2['alive']:
            return
        # ★★ 2026-10-20: 【额外效果】减抗的「第几下生效」计数器
        _hn = t2.get('_hitn', 0)
        t2['_hitn'] = _hn + 1
        # ★★★ 2026-10-27 新增: 概率闪避「{N}%機率迴避 + 每次成功-{M}%」
        #   例 自然的腳爪/白色貓咪: 75%起、每成功一次-5%, 持续 dodge_rounds 回合
        _dp = t2.get('dodge_p', 0) or 0
        # ★ 用户规则(2026-10-27): 带【标记】的技能无视闪避
        # ★ 用户规则(2026-10-27): 【只有带标记的技能】无视闪避（=致命之眼）
        #   残破木乃伊不是标记技能，不享受此规则
        if _dp > 0 and (t2.get('dodge_left', 0) or 0) > 0 and not u.get('applies_mark'):
            import random as _rnd
            if _rnd.random() * 100.0 < _dp:
                t2['dodge_p'] = max(0.0, _dp - (t2.get('dodge_dec', 5) or 5))
                if VERBOSE[0]:
                    print('      [概率闪避] %s 回避成功(下次%.0f%%)' % (t2['name'], t2['dodge_p']))
                if (_hn == 0 and u.get('mr_debuff_after_first') and u.get('mr_debuff')
                        and not has(t2.get('_tbless') or [], '言灵祝福')):
                    _pctd = u['mr_debuff']
                    if t2.get('_mr_debuff_pct'):
                        t2['mr'] += t2['_mr_debuff_pct']
                    _actd = min(_pctd, t2['mr'])
                    t2['mr'] -= _actd
                    if t2.get('_mr_debuff_pct'):
                        t2['mr'] += t2['_mr_debuff_pct']
                return

        # ★ 闪避(免疫N次伤害): 每次命中消耗1次, 期间该次伤害为0
        #   —— 不掉血 / 不消耗护盾 / 不累加连锁; 第 N+1 次命中才生效
        if t2.get('dodge', 0) >= 1:
            t2['dodge'] -= 1
            if VERBOSE[0]:
                print('      [闪避] %s 免疫一次(剩%d)' % (t2['name'], t2['dodge']))
            # ★★ 用户实测: 减抗【即使被闪避也照挂】→ 第1下被闪避也要挂,
            #    这样后面真正打到的段(第4下)就是按减抗算的
            # ★ 言灵祝福 免疫【技能】弱化 → 带言灵的目标不被减抗
            if (_hn == 0 and u.get('mr_debuff_after_first') and u.get('mr_debuff')
                    and not has(t2.get('_tbless') or [], '言灵祝福')):
                _pctd = u['mr_debuff']
                if t2.get('_mr_debuff_pct'):
                    t2['mr'] += t2['_mr_debuff_pct']
                _actd = min(_pctd, t2['mr'])
                t2['mr'] -= _actd
                t2['_mr_debuff_pct'] = _actd
                t2['_mr_debuff_left'] = u.get('debuff_turns') or 2
                if VERBOSE[0]:
                    print('      [减魔抗] %s 魔抗-%.0f (剩%d回合) [闪避也挂]' % (
                        t2['name'], _actd, t2['_mr_debuff_left']))
            # ★★★ 2026-10-31 用户更正（推翻 2026-10-22 的旧结论）:
            #   【被闪避 = 没打到 = 不触发反击】
            #   旧实现此处调用了 _run_counter → 闪避后照样反击，
            #   导致「敏捷权能 + 使者」被严重高估（闪掉致命一发还能反杀）。
            if os.environ.get('COUNTER_ON_DODGE') == '1':
                _run_counter(t2, u, 0.0, allies, rnd, to_dispel, False)
            return
        # ★ 驱散 vs 反击 = 「先驱散后伤害」 → 本次命中不会吃到反击
        #   (真正的驱散动作在【扣血之后】执行, 见下方 DISPEL 块)
        if to_dispel and not has(t2.get('_tbless') or [], '永恒祝福'):
            t2['counter'] = None
        # ★ 文本写在傷害【之前】的脆弱 → 第1下就吃
        # ★★ 2026-10-20 用户确认: 主目标 = 技能脆弱 + 爆发脆弱【相加】
        if u.get('vul_before') and not t2.get('_vul_applied'):
            t2['_vul_applied'] = True
            _vp = (u.get('vul_all_phys') or 0) + ((u.get('vul_apply_phys') or 0) if is_main else 0.0)
            _vm = (u.get('vul_all_magic') or 0) + ((u.get('vul_apply_magic') or 0) if is_main else 0.0)
            if _vp > 0:
                t2['vul_phys_amt'] = max(t2.get('vul_phys_amt') or 0, _vp)
                t2['vul_phys_left'] = max(t2.get('vul_phys_left') or 0, u.get('vul_apply_turns') or 4)
            if _vm > 0:
                t2['vul_magic_amt'] = max(t2.get('vul_magic_amt') or 0, _vm)
                t2['vul_magic_left'] = max(t2.get('vul_magic_left') or 0, u.get('vul_apply_turns') or 4)
            if VERBOSE[0]:
                print('      [VUL_TRACE-A] 施加者=%s → 目标=%s  phys=%.1f magic=%.1f (vul_before=%s)' % (
                    u.get('name'), t2.get('name'), _vp, _vm, u.get('vul_before')))
        # ★★ 2026-10-22 条件倍率: 「若敵人為物理/魔法類型，則變為造成…{VALUEn}%」
        #   用户确认「类型」= 敌人的攻击类型(type: 物/魔)，不是元素属性
        #   例 納羅達斯·無名道士: 普通450%，打物理型 → 850%(+潜力200=1050%)
        _cpv = u.get('cond_per_value')
        _cpt = u.get('cond_per_type')
        # ★★★ 2026-10-24 用户实证: 忌妒之夜「攻击敌人4次180%，若为主要目标则420%」
        #   实战 小红帽52,100/医护22,327 = 2.334 = 420/180 ✓
        if is_main and u.get('per_main'):
            _base_per = u['per_main']
        else:
            _base_per = _cpv if (_cpv is not None and _cpt and t2.get('type') == _cpt) else (u['per'] or 0)
        # ★★★ 2026-11-03 新增: 「連鎖數疊加到 N 以上時，改為造成 {VALUE2}% 傷害」
        #   实例 莎赫拉查德·泳池派對「盛夏熱浪」:
        #     技能原文: 攻擊5次，每次造成 自身魔法力{VALUE1}% 傷害
        #               若此攻擊造成的連鎖數疊加為15以上 → 改為 {VALUE2}%
        #     Lv6: VALUE1=60 / VALUE2=220 (3.67倍)
        #   旧实现只取固定 per，完全没有这个条件切换 → 严重低估该卡
        _cg = u.get('chain_per_gate')
        if _cg and (t2.get('chains') or 0) >= _cg and u.get('chain_per_value'):
            _base_per = u['chain_per_value']
        # ★ 每命中一个目标增伤: 直接加到倍率上
        # ★★★ 必须把 _base_per 显式传给 dmg，否则主目标的 420% 会被 u['per'](180) 覆盖
        _perov = (_base_per + _ppt_bonus) if _ppt_bonus else _base_per
        _extra = ((u.get('shield', 0.0) or 0.0) * u['shield_dmg_pct'] / 100.0) \
            if (u.get('shield_dmg_pct') or 0) > 0 else 0.0
        d = dmg(u, t2, rnd, is_second, bless, is_main, per_ov=_perov, extra_base=_extra) / max(1, u['hits'])
        if DMG_LOG[1] == 'A':
            DMG_LOG[0] += d       # 我方造成的伤害(含被盾吸收的部分)
            DMG_BY_UNIT[u['name']] = DMG_BY_UNIT.get(u['name'], 0.0) + d
        elif DMG_LOG[1] == 'D':
            DMG_ENEMY[u['name']] = DMG_ENEMY.get(u['name'], 0.0) + d
        # ★★ 2026-10-19 用户規則: 【驱散類技能無視護盾】—— 直接打血
        #   實證: 白雷(帶驱散) 打我幽靈 18,456/20,001/22,147，
        #         模型先吃 40,618 護盾 → 只算 8,409 且沒死（錯）
        #   實際: 護盾被穿透 → 直接扣 14,128 血 → 一下就死
        # ★★ 2026-10-19 實測推翻: 驱散並不無視護盾!
        #   實證 vs 效度幽靈: 第1下 20,390 被護盾吃掉 → 驱散解除護盾 → 第2/3下才打血
        #   (之前為了對上白雷那場加的「穿透護盾」是誤判: 真正原因是技能自帶攻擃+160% 被丟)
        s = min(t2['shield'], d) if t2['shield'] > 0 else 0
        t2['shield'] -= s
        t2['hp'] -= (d - s)
        # ★★★ SB_HIT_ON_DAMAGE (2026-10-27): 「受到攻擊時」类增益 —— 被打才触发
        #   例 阿奇拉·戰場猛獸「4回合內自身受到攻擊時 攻擊力+30%，疊加至1」
        #   实证：未被攻击时面板攻击力 2452（无+30%），被攻击后才 +30%
        if (t2.get('sb_hit_buff') and not t2.get('_sb_hit_done')
                and not (t2.get('onhit_atk_pct') or 0) > 0):
            t2['_sb_hit_done'] = True
            _P2 = (t2.get('suppressed', 0) or 0) / 100.0
            for _ht, _hv in t2['sb_hit_buff']:
                _apply_stat(t2, _ht, _hv * (1 - _P2))
            if VERBOSE[0]:
                print('      [受击增益] %s 应用 %s' % (t2.get('name'), t2['sb_hit_buff']))
        # ★★★ 2026-10-22 新增: 「每次受到攻擊時，恢復相當於自身最大生命力X%」(赛尔·恶魔之女)
        if (t2.get('heal_pct') or 0) > 0 and t2['hp'] > 0:
            # ★ 2026-10-22 用户确认: 按【50000 封顶】计算，且【回血也能暴击】
            _h = hpbase(t2) * t2['heal_pct'] / 100.0
            _saved = CRIT_PARTS[0]
            _hcrit = crit_of(t2, False, t2.get('_tbless') or [])
            CRIT_PARTS[0] = _saved
            _h *= _hcrit
            t2['hp'] = min(t2['hpmax'], t2['hp'] + _h)
            if VERBOSE[0]:
                print('      [受击回复] %s +%.0f (%.0f%%最大生命 × 暴击%.2f)' % (
                    t2['name'], _h, t2['heal_pct'], _hcrit))
        t2['chains'] += chain_add
        # ★★ 2026-10-20 用户实测: 【额外效果】减抗「第一下之后」才生效
        #   教授(魔法学校教授) 「2回合期間魔法抵抗減少15%」→ 第2~7段吃满减抗
        if _hn == 0 and u.get('mr_debuff_after_first') and u.get('mr_debuff'):
            _pctm = u['mr_debuff']
            if t2.get('_mr_debuff_pct'):
                t2['mr'] += t2['_mr_debuff_pct']
            _act = min(_pctm, t2['mr'])
            t2['mr'] -= _act
            t2['_mr_debuff_pct'] = _act
            t2['_mr_debuff_left'] = u.get('debuff_turns') or 2
            if VERBOSE[0]:
                print('      [减魔抗] %s 魔抗-%.0f (剩%d回合)' % (
                    t2['name'], _act, t2['_mr_debuff_left']))
        died = False
        # ★ 虚弱(如 奇蹟海洋): 被击中时给攻击者叠 1 层脆弱(最多8层),
        #   攻击者之后受到的伤害 +层数×脆弱%; 自身该效果在受8次攻击后消失
        vp = t2.get('vuln_pct') or 0
        if vp and u.get('alive', True) and t2.get('vuln_hits', 0) < (t2.get('vuln_max') or 0):
            t2['vuln_hits'] = t2.get('vuln_hits', 0) + 1
            u['vuln_stacks'] = min(t2.get('vuln_max') or 8, u.get('vuln_stacks', 0) + 1)
            u['vuln_left'] = t2.get('vuln_turns') or 2
        if VERBOSE[0]:
            print('      → %s 吃 %.0f 伤害%s, HP→%.0f%s' % (
                t2['name'], d, (' (护盾挡 %.0f)' % s) if s > 0 else '',
                max(0.0, t2['hp']), '  ☠死亡' if t2['hp'] <= 0 else ''))
        # ★★ 2026-10-19 新增: 「受到攻擃時自身攻擃力增加X%」可疊加(如 阿奇拉·戰場猛獸)
        # ★★★ SHIELD_ON_HIT (2026-10-27 用户指出): 技能护盾也是「受到攻擊時」触发
        #   例 阿奇拉·戰場猛獸「4回合內自身受到攻擊時 攻+30% / CD-2 / 【額外能力】200%能量護盾」
        #   → 我们打它【第一下之后】它才有盾，第2、3下打在这 4905 盾上
        # ★★★ 2026-10-31 用户确认（重大修正）: 「能量防衛」护盾是
        #   【施放技能时给予一次】，不是每回合挨打就刷新。
        #   旧实现：此处每回合首次被攻击就重新发一次满盾 →
        #   安卓女王(76,848血+80,000盾)变成每回合刷盾，有效血量翻倍，永远打不死。
        #   现改为只在 act() 施放技能时发放（该处已置 _shield_granted=True）。
        #   仅 黛安娜·反烏托邦「光环内每回合恢复」例外，走 shield_allies 分支照常。
        if (False and (t2.get('shield_pct') or 0) > 0 and t2.get('alive')
                and not t2.get('_shield_granted')):
            t2['_shield_granted'] = True
            _sb = hpbase(t2) if t2.get('shield_basis') == 'HP' else t2['atk']
            _sa = _sb * t2['shield_pct'] / 100.0
            t2['shield'] = t2.get('shield', 0.0) + _sa
            t2['shield_left'] = t2.get('shield_turns') or 4
            if VERBOSE[0]:
                print('      [受击护盾] %s 获得能量护盾 %.0f (%d回合)' % (
                    t2['name'], _sa, t2.get('shield_turns') or 4))

        # ★★★ ONHIT_ADDITIVE (2026-10-27): 「受到攻擊時攻擊力+30%，疊加至1，最多99層」
        #   正确 = 每次被打 +30%（加法叠加到 atk0 上），上限 99 层
        #   旧实现 t2['atk'] *= 1.3 每层 → 12段就 ×1.3^12 = ×23（严重虚高）
        if (t2.get('onhit_atk_pct') or 0) > 0 and t2.get('alive'):
            _mx = t2.get('onhit_atk_max') or 1
            _st = t2.get('onhit_atk_stacks') or 0
            if _st < _mx:
                _st += 1
                t2['onhit_atk_stacks'] = _st
                if t2.get('_atk0') is None:
                    t2['_atk0'] = t2['atk'] / max(1e-9, (1 + (t2.get('onhit_atk_pct') or 0) / 100.0) ** max(0, _st - 1))
                t2['atk'] = t2['_atk0'] * (1 + t2['onhit_atk_pct'] / 100.0 * _st)
                if VERBOSE[0]:
                    print('      [受击增幅] %s 攻擃+%.0f%% (第%d/%d层, 加法) atk=%.0f' % (
                        t2['name'], t2['onhit_atk_pct'], _st, _mx, t2['atk']))
        # ★★ 驱散 = 【先伤害后驱散】+ 对每个被命中的目标都生效 (2026-10-18 修)
        #   实证1: 敌方魔女打我方坦克 1000多/7000多/8000多 → 第1段吃满85%减伤, 之后被清掉
        #   实证2: 我方魔女打爱丽丝, 第1段后驱散 → 第2段打死时【不能复活】
        #   旧实现放在所有段数打完后、且只作用于最后一个目标 → AOE 时前面的目标驱散不到
        if to_dispel and not t2.get('_dispelled') and not has(t2.get('_tbless') or [], '永恒祝福'):
            t2['_dispelled'] = True
            if t2.get('shield', 0) > 0 or t2.get('skillred', 0) > 0:
                DISPEL_N[0] += 1
            t2['shield'] = 0.0          # ✅ 护盾
            t2['taunt'] = False         # ✅ 嘲讽
            t2['taunt_left'] = 0
            t2['counter'] = None        # ✅ 反击
            t2['prot'] = 0.0            # ✅ 服装减伤
            t2['prot_left'] = 0
            # ★★★ 2026-10-31 用户确认: 「受击回复」也是【施放技能后】才有的 buff
            #   (賽爾·惡魔之女: 6回合 每次受击恢复30%最大生命) → 驱散应该拆得掉
            t2['heal_pct'] = 0.0        # ✅ 受击回复
            t2['heal_turns'] = 0
            t2['revive_left'] = 0       # ✅ 复活
            if VERBOSE[0]:
                print('      [驱散] 解除 %s 的有益效果' % t2['name'])
        if t2['hp'] <= 0:
            # ★ 复活判定: 有复活 buff 且还有次数 → 不真死, 清空所有效果后回血
            if t2.get('revive_left', 0) > 0:
                t2['revive_left'] = 0                      # 只挡一次
                t2['hp'] = t2['hpmax'] * (t2.get('revive_pct', 100) / 100.0)
                t2['alive'] = True
                # 复活后身上所有效果全清（挑衅/护盾/减伤/嘲讽/闪避/反击/易伤层）
                t2['shield'] = 0.0
                t2['skillred'] = 0.0
                t2['focus'] = False
                t2['taunt'] = False
                t2['taunt_left'] = 0
                t2['dodge'] = 0
                t2['counter_used'] = 0
                t2.pop('_shield_pct', None)
                if VERBOSE[0]:
                    print('      [复活] %s 以 %.0f 血复活（效果已全清）' % (t2['name'], t2['hp']))
                # 注意: 循环继续, 剩余段数照打（多段能彻底打死）
            else:
                t2['hp'] = 0; t2['alive'] = False; died = True

        # ★★ 2026-10-18 用户规则: 脆弱/弱化的时机看【技能文本顺序】
        #   写在傷害【之后】(如 小公主) → 每个目标的第1下不吃, 第2~4下吃
        #   写在傷害【之前】(如 DJ) → 第1下就吃 (在 strike 开头已处理)
        #   实证: 海边度假第1下 24,300 (不含脆弱) ✓
        if (not u.get('vul_before')) and (not t2.get('_vul_applied')):
            t2['_vul_applied'] = True
            # ★★★ 2026-10-20 用户纠正: 脆弱写在【傷害之后】→ 从第2段开始生效！
            #   小公主 打主目标: 第1段不含脆弱, 第2段起 ×(1+1.5+0.75)=×3.25
            #                 打其他目标: 第2段起 ×(1+0.75)=×1.75
            #   （旧实现拖到整轮行动结束才挂 → 后续段全部少算, 是错的）
            # ★★★ 2026-10-24 用户实证(忌妒之夜): 脆弱写在【额外能力】→ 本技能自己不吃
            # ★ 连携伤害增加: 第一段之后挂到目标身上(后续段数生效)
            _ca = CHAIN_ADD.get((u.get('name') or '').split('·')[-1])
            if _ca:
                t2['chain_add_pct'] = max(t2.get('chain_add_pct') or 0, _ca)
                t2['chain_add_left'] = 4
                if VERBOSE[0]:
                    print('      [连携增伤] %s 受到的连携伤害 +%.0f%% (4回合)' % (t2['name'], _ca))
            if (u.get('name') or '').split('·')[-1] in VUL_AT_END:
                _PENDING_VUL.append((u, t2, is_main))
            else:
                _apply_vul(u, t2, is_main)
            # ★★ 2026-10-18 用户规则: 【技能的 130% 只给主要目标】
            #   (主要目标 = 技能选中的那个人, 如海边度假)
        # ★ 反击: 每段(每次命中)触发一次; 本段把反击者打死 → 不反击
        _run_counter(t2, u, d, allies, rnd, to_dispel, died)
    # ★★ 2026-10-19 新增: 前置效果(减抗/前置驱散/解除减伤+护盾)在伤害前执行
    #   减抗: DJ「魔法抵抗減少50%」先减抗再打 → 本次伤害吃满减抗
    #   前置驱散: 魔女「造成伤害…解除」→ 后置; 钢铁引擎「解除减伤和能量防卫…再伤害」→ 前置
    #   解除减伤+护盾: 钢铁引擎 解除【减伤(skillred)+护盾(shield)】, 与「驱散(只解护盾)」不同
    if u.get('mr_debuff') or u.get('def_debuff') or u.get('dispel_before') or u.get('remove_guard_before'):
        for t2 in list(targets):
            if not t2.get('alive'):
                continue
            if (u.get('mr_debuff') and not u.get('mr_debuff_after_first')
                    and not has(t2.get('_tbless') or [], '言灵祝福')):
                pct = u['mr_debuff']
                if t2.get('_mr_debuff_pct'):          # 先恢复旧的
                    t2['mr'] += t2['_mr_debuff_pct']
                actual = min(pct, t2['mr'])           # ★ 减法, 最小减到 0(不为负)
                t2['mr'] -= actual
                t2['_mr_debuff_pct'] = actual         # 存实际减的量(供恢复)
                t2['_mr_debuff_left'] = u.get('debuff_turns') or 4
                if VERBOSE[0]:
                    print('      [减魔抗] %s 魔抗 -%.0f (%d回合)' % (t2['name'], actual, t2['_mr_debuff_left']))
            if u.get('def_debuff') and not has(t2.get('_tbless') or [], '言灵祝福'):
                pct = u['def_debuff']
                if t2.get('_def_debuff_pct'):
                    t2['def'] += t2['_def_debuff_pct']
                actual = min(pct, t2['def'])           # ★ 减法, 最小减到 0
                t2['def'] -= actual
                t2['_def_debuff_pct'] = actual
                t2['_def_debuff_left'] = u.get('debuff_turns') or 4
                if VERBOSE[0]:
                    print('      [减防] %s 防御 -%.0f (%d回合)' % (t2['name'], actual, t2['_def_debuff_left']))
            if u.get('remove_guard_before') and not t2.get('_dispelled'):
                t2['_dispelled'] = True
                t2['shield'] = 0.0          # 解除 护盾(生命结界)
                t2['prot'] = 0.0            # 解除 技能防护罩/减伤(堕落之星等)
                t2['prot_left'] = 0
                # ★ 不清 skillred(庇佑防护罩) —— 用户确认: 钢铁引擎也无法清除庇佑的防护罩
                if VERBOSE[0]:
                    print('      [解除减伤+护盾] %s' % t2['name'])
            if u.get('dispel_before') and not t2.get('_dispelled'):
                t2['_dispelled'] = True
                t2['shield'] = 0.0
                t2['taunt'] = False
                t2['taunt_left'] = 0
                t2['counter'] = None
                t2['prot'] = 0.0
                t2['prot_left'] = 0
                t2['revive_left'] = 0
                if VERBOSE[0]:
                    print('      [前置驱散] 解除 %s 的有益效果' % t2['name'])
    # ★★ 2026-10-22 每命中一个目标增伤: 范围内每多 1 个目标，全体 +X%(加法, 无上限)
    _ppt_bonus = 0.0
    _ppt_x = u.get('per_per_target') or 0
    if _ppt_x > 0:
        _n_alive = len([x for x in targets if x.get('alive')])
        # ★ 「每有一个目标」(each) → ×N ; 「每多一个目标」(extra) → ×(N-1)
        _cnt = _n_alive if (u.get('per_target_mode') or 'each') == 'each' else max(0, _n_alive - 1)
        _ppt_bonus = _ppt_x * _cnt
        if VERBOSE[0] and _ppt_bonus:
            print('      [每目标增伤] 范围 %d 个目标 ×%d → 倍率 +%.0f%%  (%s)' % (
                _n_alive, _cnt, _ppt_bonus,
                '每有一个' if (u.get('per_target_mode') or 'each') == 'each' else '每多一个'))
    # ===== 执行攻击：范围内每个目标吃满「段数×倍率」 =====
    if AOE_MODE == 'split':                      # 段数在范围内目标间分摊
        for i in range(u['hits']):
            alive_t = [x for x in targets if x['alive']]
            if not alive_t:
                break
            strike(alive_t[i % len(alive_t)], alive_t[i % len(alive_t)] is tgt)
            # ★★★ 2026-10-30 用户指出: 打手被【反击】打死 → 剩余段数不能再打
            #   例 自然爪打虚无之星, 第1段被反 40万秒杀 → 第2段不该继续
            if not u.get('alive', True):
                if VERBOSE[0]:
                    print('      [被打断] %s 已被反击打死, 剩余段数取消' % u['name'])
                break
    else:                                        # full（含 auto 缺省）
        _dead_mid = False
        for t2 in list(targets):
            t2['_chain0'] = t2.get('chains', 0)   # ★ 行动开始时的连锁
            for _ in range(u['hits']):
                strike(t2, t2 is tgt)
                if not u.get('alive', True):
                    _dead_mid = True
                    break
            if _dead_mid:
                if VERBOSE[0]:
                    print('      [被打断] %s 已被反击打死, 剩余段数/目标取消' % u['name'])
                break
    # ★★★ 2026-10-19 用户实测: 脆弱在本技能所有段数打完后才施加
    #   (实证 小公主打幽灵 15,312/16,834/18,374/19,905 — 后续段只吃连锁+10%，不吃 +150% 脆弱)
    flush_pending_vul()
    # ★★★ 2026-11-05 新增: 出血（持续伤害）施加 —— 技能打完后挂到目标身上
    #   每回合伤害 = 施放者魔法力 × bleed_pct% × (1 + 血气层数 × blood_dot_pct%)
    if (u.get('bleed_pct') or 0) > 0 and (u.get('bleed_turns') or 0) > 0:
        _bst = u.get('blood_stacks') or 0
        _dot = (u.get('atk') or 0) * float(u['bleed_pct']) / 100.0
        _dot *= (1 + _bst * float(u.get('blood_dot_pct') or 5) / 100.0)
        for _t in (targets or []):
            if not _t.get('alive'):
                continue
            _t['bleed_left'] = int(u['bleed_turns'])
            # ★ 官方「赋予叠加」说明: 效果以【最后一次施加】为准 → 直接覆盖
            _t['bleed_dmg'] = _dot
            if VERBOSE[0]:
                print('      [出血] → %s 每回合 %.0f 伤害 × %d 回合' % (_t['name'], _dot, _t['bleed_left']))
    # ★★ 2026-10-22 减攻击力/魔法力: 对【范围内的每一个目标】施加，且按目标类型分开算
    #   用户确认: 技能范围内可能同时有物理型和魔法型角色
    #     物理型目标 → 减【攻击力】(atk_down_phys)
    #     魔法型目标 → 减【魔法力】(atk_down_mag)
    #   魔法型目标不吃「减攻击力」，物理型目标不吃「减魔法力」
    _adp = u.get('atk_down_phys') or 0
    _adm = u.get('atk_down_mag') or 0
    if _adp > 0 or _adm > 0:
        for _t in list(targets):
            if not _t.get('alive'):
                continue
            _pct_t = _adp if _t.get('type') == '物' else _adm
            if _pct_t <= 0:
                continue
            _old_ad = _t.get('_atk_down_pct') or 0
            _t['_atk_down_pct'] = max(_old_ad, _pct_t)
            _t['_atk_down_left'] = max(_t.get('_atk_down_left') or 0, u.get('atk_down_turns') or 4)
            if VERBOSE[0]:
                print('      [减%s] %s 输出 -%.0f%% (%d回合)' % (
                    '攻击力' if _t.get('type') == '物' else '魔法力',
                    _t['name'], _t['_atk_down_pct'], _t['_atk_down_left']))

def setup(t, rnd, bless):
    # ★ 护盾/减伤 改为「开局挂一次, 持续到被打光或被驱散」
    #   旧实现每回合把护盾清零、减伤只算第1回合 → 庇佑几乎没价值, 驱散也无从可驱
    for u in t:
        u.setdefault('shield', 0.0)
        u.setdefault('skillred', 0.0)

def battle(A, D, my_first, bA, bD, maxr=25):
    bA = [ID_ALIAS.get(x, x) for x in (bA or [])]
    bD = [ID_ALIAS.get(x, x) for x in (bD or [])]
    # ★★ 2026-10-18 实测结论: range_table 掩码【本来就是对的】, 不要居中!
    #   证据: GIJoe 小公主(主目标海边度假 第1行第4列)实战打死 海边度假/魔女/幽灵
    #        = 掩码 行0..2 × 列-1..1 从锚点【向下展开】正好覆盖这 3 个
    #   → 之前加的居中会改成别的方向, 是错的, 已撤销
    # ★ 记录"增益前"基础值(压迫只打折增益部分, 需要基础值)
    # ★ 朝向镜像: range_table 定义的是【我方朝左】方向 → 敌方(D队)列偏移(dc)取反
    #   (light_003 我方打 [−2,2][−1,1][0,0][1,−1](↗↙), 敌方打 [−2,−2][−1,−1][0,0][1,1](↘↖))
    for u in D:
        if u.get('shape'):
            u['shape'] = [(dr, -dc) for dr, dc in u['shape']]
    for u in (A + D):
        u['atk0'] = u['atk']; u['hp0'] = u['hp']
        u['def0'] = u['def']; u['mr0'] = u['mr']
        u['admg0'] = u['admg']; u['pres0'] = u.get('pres', 0.0)
        u['cdmg0'] = u['cdmg']; u['cr0'] = u['cr']    # ★ 白值快照(不含技能self_buff), 供压迫结算
        u['_bm_atk'] = 0.0; u['_bm_hp'] = 1.0; u['_bm_hp_pct'] = 0.0
        u['_bm_def'] = 0.0; u['_bm_mr'] = 0.0; u['_bm_admg'] = 0.0; u['_bm_pres'] = 0.0
    # ★ 2026-10-19 容错机制: 标记阵营, 用于伤害保守估算
    for u in A:
        u['side'] = 'A'
        u['_first_side'] = bool(my_first)          # ★ 我方是否先攻方
    for u in D:
        u['side'] = 'D'
        u['_first_side'] = not bool(my_first)      # ★ 敌方是否先攻方
    # ★★★ 2026-10-22 用户规则（测试口径）:
    #   我方: 暴击率没到 100% → 默认【不暴击】
    #   敌方: 默认【暴击】(cr 视为 100%)
    #   ENEMY_ALWAYS_CRIT=0 可关闭
    if os.environ.get('ENEMY_ALWAYS_CRIT', '1') == '1':
        for _u in D:
            _u['_always_crit'] = True
    # ★ 记录庇佑前的白值（供极限诅咒压制用）
    for _u in list(A) + list(D):
        _u['_white_atk'] = _u.get('atk') or 0.0
        _u['_white_cr'] = _u.get('cr') or 0.0
        _u['_white_cdmg'] = _u.get('cdmg') or 0.0
    for t, names, sec in ((A, bA, not my_first), (D, bD, my_first)):
        apply_bless(t, names)
    # ★★★ CURSE_ON_BLESS (2026-10-27 用户指出「是不是没算对面的诅咒」+ 面板实证):
    #   极限诅咒I: 「所有敌人 所有能力值增益效果受到25%的压迫」
    #   → 庇佑给的 ATK%/CR/CDMG/ADMG 也要被压 25%（旧实现只压了技能自身增益）
    #   实证: 我方海洋先锋 白值898, 后攻只带「绑定的庇佑II(+300%)」
    #         游戏面板 = 2925 = 898×3.25 (+225% = 300%×0.75)
    #         模型 = 3592 = 898×4.00 (+300%, 没压)  → 高 22.8%
    for _t, _eb in ((A, bD), (D, bA)):
        if any(('诅咒' in str(x)) or ('詛咒' in str(x)) for x in (_eb or [])):
            _sc = 0.75
            for _u in _t:
                _wa = _u.get('_white_atk') or 0.0
                _wc = _u.get('_white_cr') or 0.0
                _wd = _u.get('_white_cdmg') or 0.0
                _u['atk'] = _wa + ((_u.get('atk') or 0.0) - _wa) * _sc
                _u['cr'] = _wc + ((_u.get('cr') or 0.0) - _wc) * _sc
                _u['cdmg'] = _wd + ((_u.get('cdmg') or 0.0) - _wd) * _sc
            if VERBOSE[0]:
                print('   [极限诅咒] 对方庇佑加成被压 25%%（ATK/暴击率/爆伤）')
    # ★★★ SMOKE_SCREEN (2026-10-27): 开启烟幕 = 所有敌人 暴击率-50%、爆伤-300%, 持续2回合
    #   官方文案: 「所有敵人在第1回合開始時，暴擊率降低50%，暴擊傷害降低300%，持續2回合」
    #   用途: 精确抵消「小紅帽」(我军全体 暴击率+50% / 爆伤+300%) —— 一换一
    for _t, _eb in ((A, bD), (D, bA)):
        if '开启烟幕' in (_eb or []) or '開啟煙幕' in (_eb or []):
            # ★★★ 2026-11-05 修复: 这里【不能】直接扣 cr/cdmg!
            #   扣减已经由 dmg() 里的 _cr_pen/_cd_pen 负责（含「持续2回合」判定）
            #   两处都扣 → 敌方爆伤变负数(-202.8)、被下限抬到 97.2 → 伤害少算 5~6 倍
            #   实证: 微光s 蒼藍魔女 实战 3 段 23,554/25,909/28,268, 模型只给 3,408/3,749/4,089
            if VERBOSE[0]:
                print('   [开启烟幕] 对方全体 暴击率-50%% 爆伤-300%% (2回合)')
        # ★★ 赛季47: 威力增强 每回合开始时叠一层（加白值），最多 4 层
        #   注意: 每回合开始的处理块（主循环里）已经会做, 这里只登记参数
        _wlv0 = lv_of(names, '威力增强')
        _wpow0 = 200 if _wlv0 == 'II' else (100 if _wlv0 == 'I' else 0)
        for u in t:
            u['_wpow'] = _wpow0
            u['_wpow_lay'] = 0
        for u in t:
            u['order_is_second'] = sec
            u['_tbless'] = names          # 记住本队庇佑(用于 言灵祝福/永恒祝福 的免疫判定)
            # ★ 开局挂一次: 生命结界护盾(持续到被打光) + 守护屏障/圣域之恩 减伤
            #   多个减伤 buff【相乘】计算(NGA: 人偶75% + 海伦娜50% → (1-75%)×(1-50%)=12.5%)
            #   ★ 守护屏障官方文案「持续1回合」→ 只有第1回合有效, 第2回合起失效
            u['shield'] = u.get('bless_shield1', 0.0)
            keep1 = 1.0; keep2 = 1.0
            # ★ 守护屏障 多级【相乘】(wiki: 多个减伤buff相乘, 按释放顺序连乘)
            #   I+II = (1-0.60)×(1-0.30) = 0.28 → 减伤 72%（不是相加的 90%）
            #   2026-10-17 用户确认: 先释放II则 (1-0.6)×(1-0.3)
            _barrier_lv = []
            for raw in names:
                nm, lv = split_lv(raw)
                if nm == '守护屏障':
                    # ★★★ 2026-11-03 用户双数据实证: II 级是【受到伤害减少40%】(×0.60)
                    #   实证: 使者 2554×700%×6.722×0.47(敌防53%)×0.60 = 33,890 ← 实战 33,889 ✅
                    #         第二目标 防45% → ×0.55×0.60 = 39,660 ← 实战 39,658 ✅
                    #   旧值 II=60% 会让伤害少 33%, 与实战不符
                    _barrier_lv.append({'I': 30, 'II': 40, 'III': 90}.get(lv, 0))
            u['_barrier_lv'] = _barrier_lv             # 各级减伤%(按释放顺序, 供压迫结算)
            # ★ 圣域之恩 多级【相乘】(与守护屏障一致; 用户确认「减伤相乘」)
            #   I+II = (1-0.20)×(1-0.40) = 0.48 → 减伤 52%（旧实现只取最高级 = 40%）
            _sanctum_lv = []
            for raw in names:
                nm, lv = split_lv(raw)
                if nm == '圣域之恩':
                    _sanctum_lv.append({'I': 20, 'II': 40, 'III': 60}.get(lv, 0))
            keep2 = 1.0
            for _v in _sanctum_lv:
                keep2 *= (1 - _v / 100.0)
            _sanctum_red = round((1 - keep2) * 100, 2)
            u['_sanctum_red'] = _sanctum_red            # 圣域之恩原始减伤%(供压迫结算 ×(1-P))
            u['_sanctum_keep'] = keep2
            u['skillred'] = 0.0                        # 下面压迫结算统一重算
            u['skillred_after1'] = 1 - keep2           # 第2回合起(屏障已到期)
    for t in (A, D):
        apply_skill_buffs(t, include_self=False)   # ★ self_buff 改为出手时应用(见 act)
    D2 = ['苟延残喘' in [split_lv(x)[0] for x in bD], ]
    _CUR = {'I': 25, 'II': 50}
    # ★★ 赛季47 新增: 士气削弱 / 开启烟幕 / 破甲 —— 都是「对敌人」的第1回合减益，持续2回合
    #   记录每个单位的【对方庇佑】，dmg() 里按 rnd<=2 判定
    for _t, _eb in ((A, bD), (D, bA)):
        for _u in _t:
            _u['_ebless'] = _eb
    for u in A:                      # ★脆弱有回合数(苟延残喘/抗性弱化=6回合)
        u['vul_phys'] = 6 if has(bD, '苟延残喘') else 0
        u['vul_magic'] = 6 if has(bD, '抗性弱化') else 0
        u['suppressed'] = _CUR.get(lv_of(bD, '极限诅咒') or '', 0)
        # ★★★ 2026-10-23 修正: 按兵不动是【庇佑】沉默 → 只有先攻方言灵可免疫
        u['silenced1'] = has(bD, '按兵不动') and not _blk_bless_debuff(u)
        # ★★★ 2026-11-03 用户实测: 先攻方的「言灵祝福」也会免疫敌方庇佑的【极限诅咒压迫】
        #   实证: 我们后攻 带 极限诅咒I，对面先攻带 言灵祝福 → 我们的压迫无效
        #   → 对面安潔莉卡/自然爪按【未压制】的满值打我们
        if _blk_bless_debuff(u):
            u['suppressed'] = 0
    for u in D:
        u['vul_phys'] = 6 if has(bA, '苟延残喘') else 0
        u['vul_magic'] = 6 if has(bA, '抗性弱化') else 0
        u['suppressed'] = _CUR.get(lv_of(bA, '极限诅咒') or '', 0)
        u['silenced1'] = has(bA, '按兵不动') and not _blk_bless_debuff(u)
        if _blk_bless_debuff(u):
            u['suppressed'] = 0    # ★ 同上: 先攻方言灵祝福免疫敌方的极限诅咒压迫
    # ★ 极限诅咒「压迫」: 只把【能力值增益部分】打(1-P)折, 基础值不动。
    #   官方例子: 20%压迫下 +200%攻击力 → 实际 +160%。
    #   旧实现在 dmg 里直接 b0×(1-P), 连基础值一起砍 → debuff 强度算重约一倍。
    for u in (A + D):
        P = (u.get('suppressed', 0) or 0) / 100.0
        if P > 0:
            u['hp'] = u['hp0'] * (1 + (u.get('_bm_hp_pct', 0.0) + u.get('_sb_hp', 0.0)) / 100 * (1 - P))
            u['hpmax'] = u['hp']
            # ★★ 2026-10-19 修正: 技能自帶的攻擃力+X% (self_buff) 也要算進去!
            #   實證: 白雷 自身攻擃+160%% 被壓迫後整個丟失 → 傷害差 2.6 倍
            _sa = u.get('_sb_atk', 0.0)
            u['atk'] = u['atk0'] * (1 + (u['_bm_atk'] + _sa) / 100 * (1 - P))
            # ★ 压迫削弱【所有】庇佑能力值增益(DEF/MR/属性伤害/属性抵抗)
            #   实证: 圣域MR+60 遇诅咒I(25%) → 60×0.75=45, 面板 5+45=50 ✓
            u['def'] = u['def0'] + u['_bm_def'] * (1 - P)
            u['mr'] = u['mr0'] + u['_bm_mr'] * (1 - P)
            u['admg'] = u['admg0'] + u['_bm_admg'] * (1 - P)
            # ★★ 2026-10-18 用户实测修正: 属性抵抗加成【只对本来就有抗性的单位生效】
            #   实证(吃到均衡结界后): 殺人娃娃(風) 50→80、魔女(水) 50→80 ✅
            #                        天御鸟命(暗) 0→0、幽灵 0→0  ✅（光/暗 加不上去）
            #   所以: pres0 > 0 才加, 否则保持 0
            u['pres'] = (u['pres0'] + u['_bm_pres'] * (1 - P)) if (u.get('pres0') or 0) > 0 else 0.0
            # ★ 技能自带的爆伤/暴击率(self_buff)【同样吃压迫】: +200 → +150
            #   (2026-10-17 修正: 旧实现只重算 hp/atk/def/mr/admg/pres, 漏了 cdmg/cr,
            #    导致 医护兵「致命傷害+200%」整份生效 → crit 7.40 而非 6.90)
            if os.environ.get('SELF_BUFF_SUPPRESS', '1') == '1':
                if u.get('_sb_cdmg'):
                    u['cdmg'] = u['cdmg0'] + u['_sb_cdmg'] * (1 - P)
                if u.get('_sb_cr'):
                    u['cr'] = u['cr0'] + u['_sb_cr'] * (1 - P)
            if u.get('_shield_pct'):
                # ★★★ 2026-11-03 用户实证【推翻旧规则】: 护盾【按压迫后的血算】
                #   实证 皆非丶的自然之爪: 血 21,300(=5,876×3.625, 已含 和谐之恩II 350%×0.75)
                #                         盾 63,900 = 300% × 21,300 (生命结界II)  ✅
                #   旧实现按未压制血 26,442×300%=79,326 → 高估 24%, 会误判我方打不穿
                #   (旧的 Anoko 案例是 150%×39,632, 那条待重新复核)
                if os.environ.get('SHIELD_USE_SUPPRESSED', '1') == '1':
                    _sb = u['hp']          # 已含压迫的当前最大血
                else:
                    _sb = u['hp0'] * (1 + (u.get('_bm_hp_pct', 0.0) + u.get('_sb_hp', 0.0)) / 100.0)
                u['bless_shield1'] = min(_sb, 50000.0) * u['_shield_pct'] * float(os.environ.get('SHIELD_SCALE', '1'))
                u['shield'] = u['bless_shield1']
    # ★ 守护屏障多级【相乘】; ★「减伤」不属于能力值 → 不吃压迫 (BARRIER_SUPPRESS=1 可切回)
    #   实证: 四击(医护兵×2、敌堕落、我方魔女)同时对上, 需要 60% 全额而非 45%
    for u in (A + D):
        P = (u.get('suppressed', 0) or 0) / 100.0
        _bs = P if os.environ.get('BARRIER_SUPPRESS', '0') == '1' else 0.0
        keep1 = 1.0
        for _v in (u.get('_barrier_lv') or []):
            keep1 *= (1 - _v * (1 - _bs) / 100.0)
        keep2 = u.get('_sanctum_keep', 1.0)
        u['skillred'] = 1 - keep1 * keep2
    # ★★ 2026-10-18 用户实测: 属性抵抗加成【只对本来就有抗性的单位生效】
    #   (殺人娃娃/魔女 50→80 ✓;  光/暗 0→0 ✓)
    #   ⚠️ 旧实现写在 `if P > 0` 里 → 我方单位(P=0)从不执行,
    #   导致均衡结界给 光/暗 单位也加了 40% 属性抗抗
    #   (实证: 敌天御鸟命打我墮落之星 实战24,112 → 模型只算14,469 = ×0.6)
    for u in (A + D):
        P = (u.get('suppressed', 0) or 0) / 100.0
        if (u.get('pres0') or 0) <= 0:
            u['pres'] = 0.0
        else:
            u['pres'] = u['pres0'] + u.get('_bm_pres', 0.0) * (1 - P)

    # ★ 强制目标: 只在开局挂一次
    #   被挂的人死了 → 效果消失, 且【不会顺延】给下一个顺位(故不能每回合重挂)
    #   集中射击庇佑 → 给「对方第1顺位」挂 focus, 我方全体集火他
    #   先锋斗魂     → 我方第1顺位获得 taunt, 敌方被迫打他(仅第1回合)
    for t, names, other in ((A, bA, D), (D, bD, A)):
        if has(names, '集中射击庇佑') and other:
            min(other, key=lambda x: x['order'])['focus'] = True
            min(other, key=lambda x: x['order'])['ext_vuln'] = 100   # ★ 官方: 虚弱+100%
        if has(names, '先锋斗魂') and t:
            min(t, key=lambda x: x['order'])['taunt_left'] = 1
    if os.environ.get('DUMP_SETUP','0')=='1':
        print()
        print('========== 战斗开局属性（%s先攻） ==========' % ('我方' if my_first else '敌方'))
        for tag, team in (('我方', A), ('敌方', D)):
            print('--- %s ---' % tag)
            print('  %-14s %-4s %-4s %8s %8s %9s %7s %6s %5s  %-10s %s' % (
                '单位','顺位','站位','裸血','战斗血','护盾','攻/魔','防','暴率','技能','段/倍率'))
            for u in sorted(team, key=lambda x: x['order']):
                print('  %-14s #%-3d %-4d %8.0f %8.0f %9.0f %7.0f %6.0f %4.0f%%  %-10s %sx%.0f%%' % (
                    u['name'], u['order'], u['pos'], (u.get('hp0') or u['hpmax']), u['hpmax'],
                    (u.get('shield') or 0.0), (u.get('atk',0) if u['basis']=='自身攻擊力' else u.get('mag', u.get('atk',0))),
                    u['def'], u['cr'], u['basis'].replace('自身',''), u['hits'], u['per']))
            tb = (team[0].get('_tbless') or [])
            print('  庇佑: %s' % '+'.join(tb))
            print('  减伤keep=%.3f  屏障=%s  圣域=%s%%  压迫=%s%%' % (
                (team[0].get('skillred') or 0), team[0].get('_barrier_lv'), team[0].get('_sanctum_red'), team[0].get('suppressed')))
        print()

    for rnd in range(1, maxr + 1):
        setup(A, rnd, bA); setup(D, rnd, bD)
        # ★ 2026-10-22: 生命结界护盾只持续第1回合 → 第2回合开始【先清掉再显示】
        #   (旧实现放在回合头打印之后 → 回放里第2回合还显示着已经过期的护盾)
        if rnd >= 2:
            for _u in (A + D):
                if _u.get('bless_shield1'):
                    if (_u.get('shield', 0) or 0) <= _u['bless_shield1']:
                        _u['shield'] = 0.0
                    else:
                        _u['shield'] = _u['shield'] - _u['bless_shield1']
                    _u['bless_shield1'] = 0.0
        if VERBOSE[0]:
            print('\n──────── 第 %d 回合 ────────' % rnd)
            def _fmt(x):
                # ★ 2026-10-22 用户要求: 回合头也要显示护盾状态
                _nm = x['name'].split('·')[-1]
                if not x['alive']:
                    return '%s:(死)' % _nm
                _s = '%s:%.0f' % (_nm, x['hp'])
                if (x.get('shield') or 0) > 0:
                    _s += '[盾%.0f]' % x['shield']
                return _s
            print('  我方 %s' % '  '.join(_fmt(x) for x in A))
            print('  敌方 %s' % '  '.join(_fmt(x) for x in D))
        # ★ 嘲讽维持: 每回合开始按剩余回合数结算(服装自带嘲讽/先锋斗魂统一走 taunt_left)
        # ★★ 2026-10-19 用戶實測: 嘲諷優先級 = 【本回合誰先放誰優先】
        #   第1回合愛麗絲先放→愛麗絲優先; 第2回合殺人娃娃先放→殺人娃娃優先
        TAUNT_SEQ[0] = 0
        for u in (A + D):
            u['taunt_seq'] = 0
            # ★★ 2026-10-19 修正: _dispelled 只是「同一次行動內不重複驅散」的標記,
            #   之前從不重置 → 同一目標全場只能被驅散一次 (錯誤)
            #   實證: 第2回合白雷驅散被跳過, 導致愛麗絲重新挂的復活沒被解掉
            u['_dispelled'] = False
            u['_sb_hit_done'] = False          # ★ 受击增益每回合重置
            u['_shield_granted'] = False       # ★ 受击护盾(见下方, 已禁用重复发放)
        for u in (A + D):
            # ★★★ DODGE_ON_CAST: 概率闪避是「放技能才有的 buff」
            #   必须等该单位出手后才生效（用户 2026-10-27 指出）
            #   旧实现第1回合就激活 → 我先攻时打它已在判定75%闪避 → 低估我方胜率
            if (u.get('dodge_rounds') or 0) > 0 and u.get('_dodge_cast'):
                u['dodge_left'] = max(0, (u.get('dodge_left') or 0) - 1)
                if u.get('dodge_left', 0) <= 0:
                    u['dodge_p'] = 0.0
            u['taunt'] = u.get('taunt_left', 0) > 0
            if u.get('taunt_left', 0) > 0:
                u['taunt_left'] -= 1
            # ★ 复活 buff 回合衰减（技能写"4回合内应用复活效果", 过期失效）
            if u.get('revive_left', 0) > 0:
                u['revive_left'] -= 1
            # ★★ 减抗/减防 debuff 回合衰减(过期恢复, 减法)
            if u.get('_mr_debuff_left', 0) > 0:
                u['_mr_debuff_left'] -= 1
                if u['_mr_debuff_left'] <= 0 and u.get('_mr_debuff_pct'):
                    u['mr'] += u['_mr_debuff_pct']
                    u['_mr_debuff_pct'] = 0.0
            if u.get('_def_debuff_left', 0) > 0:
                u['_def_debuff_left'] -= 1
                if u['_def_debuff_left'] <= 0 and u.get('_def_debuff_pct'):
                    u['def'] += u['_def_debuff_pct']
                    u['_def_debuff_pct'] = 0.0
            # ★★ 2026-10-22 减攻击力/魔法力 回合衰减(百分比, 直接清掉)
            if u.get('_atk_down_left', 0) > 0:
                u['_atk_down_left'] -= 1
                if u['_atk_down_left'] <= 0:
                    u['_atk_down_pct'] = 0.0
            # ★★ 赛季47: 威力增强 每回合开始叠一层（加白值），最多 4 层
            if u.get('_wpow') and u.get('_wpow_lay', 0) < 4:
                u['_wpow_lay'] = u.get('_wpow_lay', 0) + 1
                u['_bm_atk'] = u.get('_bm_atk', 0.0) + u['_wpow']
                _P0 = (u.get('suppressed', 0) or 0) / 100.0
                u['atk'] = u['atk0'] * (1 + u['_bm_atk'] / 100.0 * (1 - _P0))
            # ★★ 突袭准备只持续【4回合】(用户确认) → 第5回合起撤销 ATK+300%
            if rnd >= 5 and u.get('_surprise_atk'):
                u['_bm_atk'] -= u['_surprise_atk']
                P = (u.get('suppressed', 0) or 0) / 100.0
                u['atk'] = u['atk0'] * (1 + u['_bm_atk'] / 100.0 * (1 - P))
                u['_surprise_atk'] = 0.0
            # ★★ 2026-10-17 用户确认: 【生命结界护盾】和【守护屏障减伤】都只持续第1回合,
            #   第1回合结束就过期 → 第2回合起护盾清零(仅扣掉庇佑那部分, 技能护盾保留)
            #   (旧实现让护盾一直留到被打光 → 我方过肉, 后半场判定过于乐观)
            if rnd >= 2 and u.get('bless_shield1'):
                if u.get('shield', 0) <= u['bless_shield1']:
                    u['shield'] = 0.0
                else:
                    u['shield'] = u['shield'] - u['bless_shield1']
                u['bless_shield1'] = 0.0
            # ★ 反击持续时间衰减（激活后 N 回合, 用完即失效）
            if u.get('counter_left', 0) > 0:
                u['counter_left'] -= 1
                if u['counter_left'] <= 0:
                    u['counter'] = None
            # ★ 技能护盾回合数衰减（爱丽丝2回合 / 安卓女王4回合）
            if u.get('shield_left', 0) > 0:
                u['shield_left'] -= 1
                if u['shield_left'] <= 0 and u.get('skill_shield_amt'):
                    u['shield'] = max(0.0, u.get('shield', 0.0) - u['skill_shield_amt'])
                    u['skill_shield_amt'] = 0.0
            # ★ 技能施加的脆弱回合衰减
            if u.get('vul_phys_left', 0) > 0:
                u['vul_phys_left'] -= 1
                if u['vul_phys_left'] <= 0:
                    u['vul_phys_amt'] = 0.0
            if u.get('vul_magic_left', 0) > 0:
                u['vul_magic_left'] -= 1
                if u['vul_magic_left'] <= 0:
                    u['vul_magic_amt'] = 0.0
            # ★ 集中射击庇佑的虚弱是「每回合刷新、持续1回合」, 故每回合先清再挂
            u['ext_vuln'] = 0
        for t, names, other in ((A, bA, D), (D, bD, A)):
            if has(names, '集中射击庇佑') and other:
                al = [x for x in other if x['alive']]
                if al:
                    min(al, key=lambda x: x['order'])['ext_vuln'] = 100
                    min(al, key=lambda x: x['order'])['focus'] = True
        # ★ 守护屏障的防护罩只持续 1 回合 → 第2回合起失效
        #   (旧代码误用上面循环残留的 u → 全场只有敌方末位单位被重置, 其余单位减伤永久生效)
        # ★ 虚弱/防護罩 回合维持: 到期清零
        for u in (A + D):
            if rnd >= 2 and 'skillred_after1' in u:
                u['skillred'] = u['skillred_after1']
            if u.get('vuln_left', 0) > 0:
                u['vuln_left'] -= 1
                if u['vuln_left'] <= 0:
                    u['vuln_stacks'] = 0
            if u.get('prot_left', 0) > 0:
                u['prot_left'] -= 1
                if u['prot_left'] <= 0:
                    u['prot'] = 0.0
        # ★ 突袭准备: 第3顺位「4回合内不可被选中」必须从【开局】就生效。
        #   旧实现写在 act() 里(等他出手才置位) → 第1回合仍能被选中秒掉, 与实战不符
        for t, bn in ((A, bA), (D, bD)):
            for u in t:
                # ★★★ 2026-10-30 用户确认: 回歸偶像「4回合回避目标」= 【施放后】才生效
                #   （与突袭准备不同：突袭准备是庇佑, 开局第1回合就生效）
                #   untarg_from 在她出手施放时被写入 → 从那一回合起算 4 回合
                _uf = u.get('untarg_from')
                u['untarg'] = 1 if (
                    (u['order'] == 3 and has(bn, '突袭准备') and rnd <= 4)
                    or (_uf is not None and _uf <= rnd <= _uf + 3)
                ) else 0
        # ★ 出手顺序修正: 两边严格交替, 每个【存活】单位每回合行动一次。
        #   死亡单位不占位 → 由本方下一个存活单位递补(旧实现是跳过该次出手,
        #   等于让对方白丢一次、我们白赚一次, 会严重高估先手优势)
        ai = di = t = 0
        while True:
            while ai < len(A) and not A[ai]['alive']:
                ai += 1
            while di < len(D) and not D[di]['alive']:
                di += 1
            if ai >= len(A) and di >= len(D):
                break
            want_mine = (t % 2 == 0) if my_first else (t % 2 != 0)
            if want_mine and ai < len(A):
                u = A[ai]; ai += 1
            elif (not want_mine) and di < len(D):
                u = D[di]; di += 1
            elif ai < len(A):
                u = A[ai]; ai += 1
            else:
                u = D[di]; di += 1
            t += 1
            if rnd == 1 and u['order'] == 1 and u.get('silenced1'):
                # ★★ 2026-10-22 用户纠正: 按兵不动只是【第1回合第1顺位不能放技能】，
                #   不是整回合跳过 —— 仍然可以普攻；且只影响第1回合
                basic_attack(u, D if u in A else A, A if u in A else D, rnd,
                             (not my_first) if u in A else my_first,
                             bA if u in A else bD)
                if not any(x['alive'] for x in A):
                    return 'D', rnd
                if not any(x['alive'] for x in D):
                    return 'A', rnd
                continue
            if rnd >= 5:                      # ★★ 赛季47 死亡时间: 第5回合起全体只能基本攻击
                basic_attack(u, D if u in A else A, A if u in A else D, rnd,
                             (not my_first) if u in A else my_first,
                             bA if u in A else bD)
                if not any(x['alive'] for x in A):
                    return 'D', rnd
                if not any(x['alive'] for x in D):
                    return 'A', rnd
                continue
            if u.get('silenced', 0) > 0:      # ★ 被沉默: 无法施放技能 → 但可以普攻
                u['silenced'] -= 1
                basic_attack(u, D if u in A else A, A if u in A else D, rnd,
                             (not my_first) if u in A else my_first,
                             bA if u in A else bD)
                if not any(x['alive'] for x in A):
                    return 'D', rnd
                if not any(x['alive'] for x in D):
                    return 'A', rnd
                continue
            # ★★★ DODGE_ON_CAST: 该单位出手时才获得概率闪避 buff
            if (u.get('dodge_rounds') or 0) > 0 and not u.get('_dodge_cast'):
                u['_dodge_cast'] = True
                u['dodge_left'] = u.get('dodge_rounds') or 2
            if VERBOSE[0]:
                print('  ▶ %s(%s) 出手' % (u['name'], '我' if u in A else '敌'))
            DMG_LOG[1] = 'A' if u in A else 'D'   # 记录本次出手归属(总伤害对账用)
            is_second = (not my_first) if u in A else my_first
            act(u, D if u in A else A, A if u in A else D, rnd, is_second, bA if u in A else bD)
            if not any(x['alive'] for x in A):
                return 'D', rnd
            if not any(x['alive'] for x in D):
                return 'A', rnd
        # ★★★ 2026-11-05 新增: 出血（持续伤害）结算 —— 官方定义「每回合【结束】时造成伤害」
        #   伤害在施加时按当时的魔法力×血气层数算好（birth-time snapshot）
        for _u in (A + D):
            if _u.get('alive') and (_u.get('bleed_left') or 0) > 0:
                _d = _u.get('bleed_dmg') or 0.0
                _u['hp'] = (_u.get('hp') or 0.0) - _d
                _u['bleed_left'] = (_u.get('bleed_left') or 1) - 1
                if VERBOSE[0]:
                    print('   [出血] %s 吃 %.0f 伤害, HP→%.0f (还剩 %d 回合)' % (
                        _u['name'], _d, max(0.0, _u['hp']), _u['bleed_left']))
                if _u['hp'] <= 0:
                    _u['alive'] = False
                    if VERBOSE[0]:
                        print('   [出血] %s ☠死亡' % _u['name'])
        # ★ 不灭庇佑: 6回合内, 每回合结束时回复100%最大生命
        if rnd <= 6:
            for tm, bn in ((A, bA), (D, bD)):
                if has(bn, '不灭庇佑'):
                    for u in tm:
                        if u['alive']:
                            u['hp'] = min(u['hpmax'], u['hp'] + u['hpmax'])
    ha = sum(x['hp'] for x in A) / max(1, sum(x['hpmax'] for x in A))
    hd = sum(x['hp'] for x in D) / max(1, sum(x['hpmax'] for x in D))
    return ('A' if ha >= hd else 'D'), maxr

# ★ 2026-10-17 校准后重搜: 针对 3400~3600 分段（114套防守）
#   #1 用 莱克莉斯·杀人娃娃（pos12，第3行第3列）当坦克抗伤
# ★ 嘲讽施放序号(多嘲讽时取最近)\
TAUNT_SEQ = [0]

# ★★ 2026-10-22 赛季47 最优庇佑（穷举搜索 + 980 套回测）
MY_FIRST = ['绑定之恩II', '速战速决', '斗魂之恩', '极限诅咒I']    # 8 点
MY_SECOND = ['先锋斗魂', '士气削弱', '开启烟幕', '按兵不动', '极限诅咒I', '绑定之恩I', '绑定之恩II', '生命结界I']  # 10 点

MY_C = [   # ★★ 2026-10-22 赛季47 终版2（635套：先攻98.0% / 后攻98.3% / 双负0.8%）
        # ★★★ 2026-10-22 用户实测纠正: 医护兵 与 恶灵 位置摆反了
        #   医护兵 = 第5行第3列(pos22)   ← 原 pos20
        #   恶作剧幽灵 = 第5行第1列(pos20) ← 原 pos22
        (1, 22, '葛兰西特', '战地医护兵'),
        (2, 6,  '莎赫拉查德', '苍蓝魔女'),
        (3, 24, '安洁莉卡', '堕落之星'),
        (4, 20, '葛兰西特', '恶作剧幽灵'),
        (5, 12, '莎赫拉查德', '魔法学校教授')]
# ★ 先攻档(7点) — 2026-10-19 贪心搜索: 均衡结界 替换 突袭准备 (2700-2800 先攻 40→41)

# ★ 后攻档(9点): 突袭准备 + 守护圣域 + 生命结界II + 光辉之恩II + 生命结界I + 极限诅咒I + 均衡结界

# ===== 赛季47 规则常量（见 铁律#128 / arena_grid_5x5.json）=====
# ★★★ 2026-10-24 用户要求: 地图尺寸/禁站格【每个赛季可能变】→ 不写死, 读 season_map.json
#   改赛季时只改 season_map.json 的 rows / cols / forbidden, 不用动代码
_MAPCFG = {}
try:
    import json as _json, os as _os
    _MAPCFG = _json.load(io.open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'season_map.json'), encoding='utf-8'))
except Exception:
    _MAPCFG = {}
S47_ROWS = int(_MAPCFG.get('rows', 5))
S47_COLS = int(_MAPCFG.get('cols', 5))
# 禁站格（pos = row*COLS + col，row0=第1行）
FORBIDDEN_POS = set(_MAPCFG.get('forbidden', [1, 3, 7, 10, 14, 17, 21, 23]))
USABLE_POS = [p for p in range(S47_ROWS * S47_COLS) if p not in FORBIDDEN_POS]


def pos2rc(p):
    """pos → (row, col)，列数跟着赛季配置走"""
    p = int(p)
    return p // S47_COLS, p % S47_COLS
S47_MAX_UNITS = 5
S47_FIRST_POINTS = 8      # 先攻庇佑点数
S47_SECOND_POINTS = 10    # 后攻庇佑点数


_BLESS_COST = None


def bless_points(names):
    """算一组庇佑的总点数（读 bless_id_map.json）"""
    global _BLESS_COST
    if _BLESS_COST is None:
        _BLESS_COST = {}
        try:
            _m = json.load(io.open(os.path.join(HERE, 'bless_id_map.json'), encoding='utf-8'))
            for k, v in _m.items():
                _BLESS_COST[v['name']] = v.get('cost', 0)
        except Exception:
            pass
    tot = 0
    for nm in (names or []):
        tot += _BLESS_COST.get(nm, 0)
    return tot


def validate_bless(names, slot='first'):
    """检查庇佑点数：先攻=8 / 后攻=10。返回问题列表"""
    lim = S47_FIRST_POINTS if slot == 'first' else S47_SECOND_POINTS
    got = bless_points(names)
    if got != lim:
        return ['%s 庇佑点数 %d ≠ %d（%s）' % (
            '先攻' if slot == 'first' else '后攻', got, lim, '+'.join(names or []))]
    return []


def validate_lineup(units, tag=''):
    """检查阵容是否合法（5 人、不占禁站格）。返回问题列表，空 = 合法"""
    errs = []
    if len(units) > S47_MAX_UNITS:
        errs.append('%s 出战 %d 人 > 上限 %d' % (tag or '阵容', len(units), S47_MAX_UNITS))
    seen = set()
    for it in units:
        pos = it[1] if isinstance(it, (tuple, list)) and len(it) > 1 else None
        if isinstance(it, dict):
            pos = it.get('pos')
        if pos is None:
            continue
        if int(pos) in FORBIDDEN_POS:
            errs.append('%s pos%d 是禁站格' % (tag or '阵容', int(pos)))
        if int(pos) in seen:
            errs.append('%s pos%d 重复站位' % (tag or '阵容', int(pos)))
        seen.add(int(pos))
    return errs


def newteam():
    return [unit_stats(c, co, o, p) for o, p, c, co in MY_C]


# ===== demo（只在直接运行本文件时执行；import 时不跑）=====
def _demo():
    lines = io.open(os.path.join(HERE, '防守阵容_最新300名.txt'), encoding='utf-8').read().splitlines()
    # ★ 敌方后攻庇佑缺失时的默认值: 主流坦克套路 + 极限诅咒II
    #   (2026-10-16 实战标定: AIRsola战 我方伤害=模型78% ⇔ 对面诅咒II压制50%, fallback成诅咒I导致先攻全盘高估28%)
    # ★ ID→名称 映射补齐 (2026-10-18 用户确认)
    DEFAULT_ENEMY_SECOND = ['光辉之恩II', '守护圣域', '守护屏障I', '守护屏障II', '极限诅咒II', '生命结界I', '突袭准备']
    defs = []; cur = None
    for ln in lines:
        s = ln.strip()
        if s.startswith('UID '):
            cur = {'head': s, 'units': [], 'first': [], 'second': []}
            defs.append(cur)
        elif cur is not None:
            if s.startswith('#') and ' pos' in s:
                t = s.split()
                if len(t) >= 9:
                    # 顺带取真实练度: 形如 '#1 pos3 马莫尼勒 死亡之夜 23112 100 +5 - 17点'
                    #   t[6]=破度('+5')  t[7]=爆发('Lv3' 或 '-')  t[8]=潜能('17点')
                    _b = t[6].lstrip('+') if len(t) > 6 else ''
                    brk = int(_b) if _b.isdigit() else None
                    bst = None
                    if len(t) > 7:
                        m = re.match(r'Lv(\d+)', t[7])
                        if m:
                            bst = int(m.group(1))
                        elif t[7] == '-':
                            bst = 0
                    cur['units'].append((int(t[0][1:]), t[1], t[2], t[3], brk, bst))
            elif s.startswith('先攻庇佑'):
                cur['first'] = [x.split('(')[0].strip() for x in s.split(':', 1)[1].split('+') if x.strip() and x.strip() != '-']
            elif s.startswith('后攻庇佑'):
                cur['second'] = [x.split('(')[0].strip() for x in s.split(':', 1)[1].split('+') if x.strip() and x.strip() != '-']

    fw = sw = 0; rows = []; n = 0
    for dfn in defs:
        if len(dfn['units']) not in (5, 6):      # ★ 赛季47 是 5 人阵
            continue
        D0 = []
        ok = True
        for o, p, c, co, brk, bst in dfn['units']:
            u = unit_stats(c, co, o, p, brk, bst)
            if not u:
                ok = False; break
            D0.append(u)
        if not ok:
            continue
        n += 1
        # 我先攻时: 我方用先攻档, 对方用后攻档; 反之对调
        r1 = battle(newteam(), [dict(x) for x in D0], True, MY_FIRST, dfn['second'] or DEFAULT_ENEMY_SECOND)[0]
        r2 = battle(newteam(), [dict(x) for x in D0], False, MY_SECOND, dfn['first'] or MY_FIRST)[0]
        fw += (r1 == 'A'); sw += (r2 == 'A')
        rows.append((int(r1 == 'A') + int(r2 == 'A'), dfn['head']))
    print('=== 我方 vs %d 套前排防守（庇佑已并入属性）===' % n)
    if n == 0:
        # ★ 2026-10-22: 赛季47 是 5 人阵，本 demo 只跑 6 人阵 → 会得到 0 套，避免除零直接跳过
        print('（当前防守阵容文件里没有 6 人阵，跳过 demo）')
        return
    print('【我先攻】胜 %d/%d = %.0f%%' % (fw, n, 100 * fw / n))
    print('【我后攻】胜 %d/%d = %.0f%%' % (sw, n, 100 * sw / n))
    print('[诊断] 驱散实际清掉护盾/减伤次数:', DISPEL_N[0])
    print('综合: %.1f%%   双胜%d / 一胜一负%d / 双负%d' % (
        100 * (fw + sw) / (2 * n), sum(1 for a, _ in rows if a == 2),
        sum(1 for a, _ in rows if a == 1), sum(1 for a, _ in rows if a == 0)))
    print('\n双负场次(两套庇佑都打不过):')
    for a, h in rows:
        if a == 0:
            print('   ', h[:70])
    print('\n一胜一负(由先后手决定, 风险对局):')
    for a, h in rows:
        if a == 1:
            print('   ', h[:70])

if __name__ == '__main__':
    _demo()
