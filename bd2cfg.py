# -*- coding: utf-8 -*-
"""统一读取赛季配置（season_map.json），所有脚本/网页共用
   改规则只需要改 season_map.json，不用动代码
"""
import io
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
_PATH = os.path.join(HERE, 'season_map.json')

DEFAULTS = {
    'season': 49, 'season_name': '赛季49',
    'rows': 5, 'cols': 5, 'forbidden': [4, 6, 18, 20],
    'max_units': 7, 'max_cost': 240,
    'bless_first': 6, 'bless_second': 8,
    'initial_score': 1000, 'death_countdown': 5, 'death_round_start': 5,
}


def rules():
    d = dict(DEFAULTS)
    try:
        d.update(json.load(io.open(_PATH, encoding='utf-8')))
    except Exception:
        pass
    return d


def save(patch):
    """合并保存（只覆盖传入的键）"""
    d = rules()
    d.update(patch or {})
    io.open(_PATH, 'w', encoding='utf-8', newline='').write(
        json.dumps(d, ensure_ascii=False, indent=1))
    return d


def cells():
    r = rules()
    n = int(r['rows']) * int(r['cols'])
    forb = set(int(x) for x in (r.get('forbidden') or []))
    return [p for p in range(n) if p not in forb]


def max_cost():
    return int(rules().get('max_cost') or 240)


def max_units():
    return int(rules().get('max_units') or 7)


def bless_points(first):
    r = rules()
    return int(r.get('bless_first' if first else 'bless_second') or (6 if first else 8))


if __name__ == '__main__':
    r = rules()
    print('赛季 %s' % r['season_name'])
    print('  阵形 %d×%d  禁用格 %s' % (r['rows'], r['cols'], r['forbidden']))
    print('  人数上限 %d  费用上限 %d' % (r['max_units'], r['max_cost']))
    print('  庇佑点数 先攻 %d / 后攻 %d' % (r['bless_first'], r['bless_second']))
    print('  可用格 %d 个: %s' % (len(cells()), cells()))
