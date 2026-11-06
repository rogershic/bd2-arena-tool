# -*- coding: utf-8 -*-
"""目标选择(对位/检索)模块 —— 按游戏真实检索规则实现 (2026-10-16, 规则经用户确认)

规则(来源: 用户确认 + 竞技场进攻方案_数值版.md 〇·E):
  1. 「正对面」= 同(行,列) —— 两边坐标完全重合
  2. 同列检索: 正对面 → 下面一格(行+1, 朝第5行前排) → 上面一格(行-1, 朝第1行后排)
  3. 同列耗尽 → 换相邻列, 列内重复步骤2 (先右后左, 可用环境变量 BD2_COL_ORDER 调)
  4. 「回避 / 突袭准备」单位不可被直接选中(检索跳过); 全场只剩他一个时仍可被选
  5. 「跳過」(越过): 不吃"不可选中"阻挡 —— 同列从敌方后排(第1行,row0)向前排扫, 直取后排
  6. AOE 以主目标为原点, 扫到的"不可选中"单位照样受伤 (在 _sim3.act 中实现)
  7. target=自己/我方 → 增益/治疗类, 不做攻击动作(buff 已按常驻并入属性)
"""
import os, re

# ★★ 2026-10-22 赛季47: 棋盘 4行×5列 → 5行×5列（25 格，其中 8 格不可配置）
ROWS, COLS = 5, 5
COL_MODE = os.environ.get('BD2_COL_ORDER', 'right_first')   # right_first / left_first


def rc(pos):
    """pos(0~24) -> (row, col); row0=第1行(后排), row4=第5行(前排)"""
    v = re.sub(r'\D', '', str(pos))
    p = int(v) if v else 0
    return p // COLS, p % COLS


def _col_order(c):
    """列检索顺序: 自身列 → 相邻列交替展开"""
    out = [c]
    step = 1 if COL_MODE == 'right_first' else -1
    for d in range(1, COLS):
        cc = c + step * d
        if 0 <= cc < COLS:
            out.append(cc)
        cc = c - step * d
        if 0 <= cc < COLS:
            out.append(cc)
    return out


def _scan_cells(ur, uc, skip_mode):
    """生成 (row,col) 检索序列"""
    if skip_mode:
        # 跳過: 跳过敌方第一排(row0), 打【最后排优先】(row3→row1);
        #   该列 row0 后面没人, 才打 row0
        #   (2026-10-17 实战: 海边度假跳过, 优先打医护兵row3, 不是泳池派对row1)
        for c in _col_order(uc):
            for r in range(ROWS - 1, 0, -1):
                yield r, c
            yield 0, c
    else:
        # 最前方: 同列从【对面第一排(row0)】开始, 一排排往下扫; row0没人才打row1, 依此类推
        #   (2026-10-17 实战确认: 堕落之星同列 row0空→row1魔女→先打魔女)
        for c in _col_order(uc):
            for r in range(ROWS):
                yield r, c


def pick(u, enemies):
    """返回主目标; 找不到(或该单位不攻击)返回 None"""
    alive = [e for e in enemies if e.get('alive')]
    if not alive:
        return None
    mode = (u.get('target') or '最前方')
    if mode in ('自己', '我方'):
        return None                       # 增益/治疗类不做攻击动作
    sel = [e for e in alive if e.get('untarg', 0) <= 0]
    if not sel:
        sel = alive                       # 全员不可选中 → 仍可被选(规则: 除非只剩他一个)
    ok = set(map(id, sel))
    # ★ 强制目标优先: 嘲讽(挑衅) / 集中射击印记(focus) —— 【无视回避 untarg】
    # ★ 2026-10-17 用户确认: 对面多个嘲讽时, 打【最近施放嘲讽】的那个
    #   (第二回合敵方殺人娃娃刚放挑衅 → 我方全员打她, 即使回歸偶像也还带着旧嘲讽)
    #   序号 taunt_seq 由 act() 施放时递增赋值
    taunters = [e for e in alive if e.get('taunt')]
    if taunters:
        # ★★ 2026-10-19 用戶實測: 【本回合誰先放挑釅誰優先】
        #   第1回合愛麗絲先放 → 打愛麗絲
        #   第2回合殺人娃娃先放 → 打殺人娃娃
        #   taunt_seq 每回合重置, 1=本回合最先放; 0=本回合沒放(次優先)
        return min(taunters, key=lambda e: (e.get('taunt_seq') or 999, e.get('order', 99)))
    # 集中射击印记(庇佑挂的强制集火): 顺位最高者
    focusers = [e for e in alive if e.get('focus')]
    if focusers:
        return min(focusers, key=lambda e: e.get('order', 99))
    cell = {}
    for e in alive:
        r, c = rc(e.get('pos'))
        cell.setdefault((r, c), []).append(e)
    ur, uc = rc(u.get('pos'))
    # ★★ 2026-10-19 用戶確認【越過】:
    #   跳過該列最前面那一個人, 打它後面那個;
    #   該列後面沒人(只有 1 個) → 這列沒得跳 → 按列掃描順序看下一列
    #   (自身列 → 右1 → 左1 → 右2 → 左2 ...)
    #   所有列都只有 1 個人 → 直接打最前面那個
    if mode == '跳過':
        # 找到第一個有人的列(已按自身→右1→左1→右2... 的順序)
        for c in _col_order(uc):
            colu = [e for e in alive if rc(e.get('pos'))[1] == c and id(e) in ok]
            if not colu:
                continue
            colu.sort(key=lambda e: rc(e.get('pos'))[0])     # 前 → 後
            if len(colu) >= 2:
                return colu[1]        # 跳過最前面那個, 打它後面那個
            return colu[0]            # 後面沒人 → 直接打這個(不跳過, 也不換列)
    _hits = []
    for r, c in _scan_cells(ur, uc, False):
        for e in cell.get((r, c), []):
            if id(e) in ok and e not in _hits:
                _hits.append(e)
    for e in _hits:
        return e
    return sel[0]                         # 兜底(理论上到不了)
