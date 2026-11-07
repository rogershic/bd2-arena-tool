# -*- coding: utf-8 -*-
"""直接拉最新 ColosseumRanking（不需要开游戏），写 uid_queue.txt + ranking_full_new.json

修正点:
  · 登录包从【最新的 batch_capture_*.jsonl】里取（旧脚本写死 req_dump.jsonl，早已过期）
  · 字段映射按 report_lineups.py 已验证的规则:
      f1=UID  f2=名字  f7.1=胜利分  f7.2=名次  f6.2=公会
"""
import io
import os
import sys
import json
import base64
import re
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import sys as _bd2sys
HERE = (os.environ.get('BD2_HOME') or
        (os.path.dirname(os.path.abspath(_bd2sys.executable))
         if getattr(_bd2sys, 'frozen', False)
         else os.path.dirname(os.path.abspath(__file__))))
from curl_cffi import requests as cr
from Crypto.Cipher import AES

FK = b'abcdefghijkrstuv024680wxyzlmnopq'
HOST = 'api-cf.bd2.pmang.cloud'


def _pad(b):
    n = 16 - (len(b) % 16)
    return b + bytes([n]) * n


def varint(n):
    o = b''
    while True:
        x = n & 0x7f
        n >>= 7
        o += bytes([x | (0x80 if n else 0)])
        if not n:
            return o


def enc(proto, key):
    return base64.b64encode(AES.new(key, AES.MODE_CBC, iv=b'\x00' * 16).encrypt(_pad(base64.b64encode(proto)))).decode()


def dec(data, key):
    ct = base64.b64decode(data) if isinstance(data, str) else data
    pt = AES.new(key, AES.MODE_CBC, iv=b'\x00' * 16).decrypt(ct)
    n = pt[-1]
    if 1 <= n <= 16:
        pt = pt[:-n]
    return pt


def rd(b, i):
    v = s = 0
    while True:
        x = b[i]
        i += 1
        v |= (x & 0x7f) << s
        if not x & 0x80:
            return v, i
        s += 7


def walk(b):
    i = 0
    out = []
    while i < len(b):
        try:
            tag, i = rd(b, i)
        except Exception:
            break
        fn, wt = tag >> 3, tag & 7
        if wt == 0:
            v, i = rd(b, i)
            out.append((fn, 0, v))
        elif wt == 2:
            ln, i = rd(b, i)
            v = b[i:i + ln]
            i += ln
            out.append((fn, 2, v))
        elif wt == 1:
            v = b[i:i + 8]
            i += 8
            out.append((fn, 1, v))
        elif wt == 5:
            v = b[i:i + 4]
            i += 4
            out.append((fn, 5, v))
        else:
            break
    return out


H = {'Content-Type': 'multipart/form-datas',
     'User-Agent': 'UnityPlayer/2022.3.62f2 (UnityWebRequest/1.0, libcurl/8.10.1-DEV)',
     'Accept': '*/*',
     'b2_app_version': os.environ.get('B2_APP', '2.37.13'),
     'b2_bundle_version': os.environ.get('B2_BUNDLE', '20261022174708'),
     'market_type': '6',
     'x-unity-version': '2022.3.62f2'}


# ★★★ 2026-10-23: 请求头从 live_session.json 读（游戏更新会改版本号，写死必挂 -6/401）
def _load_hdrs(base):
    try:
        _ses = io.open(os.path.join(HERE, 'live_session.json'), encoding='utf-8')
        _real = (json.load(_ses) or {}).get('hdrs') or {}
        _out = {k: v for k, v in _real.items()
                if k.lower() not in ('content-length', 'host', 'cookie', 'accept-encoding')}
        if _out:
            _out.setdefault('Accept-Encoding', 'deflate, gzip')
            return _out
    except Exception:
        pass
    return dict(base)

H = _load_hdrs(H)
H.pop('Cookie', None)   # ★ 登录时不能用旧 cookie，否则服务端返回空 data

# ---------- 取最新登录包 ----------
cands = sorted([f for f in os.listdir(HERE) if f.startswith('batch_capture') and f.endswith('.jsonl')],
               key=lambda f: os.path.getmtime(os.path.join(HERE, f)), reverse=True)
body = None
for f in cands:
    for l in io.open(os.path.join(HERE, f), encoding='utf-8'):
        try:
            r = json.loads(l)
        except Exception:
            continue
        if r.get('path', '').endswith('/LoginUser') and r.get('req_body_b64'):
            body = base64.b64decode(r['req_body_b64'])
            break
    if body:
        print('登录包来源: %s' % f)
        break
if not body:
    print('❌ 找不到登录包（需要先抓一次登录）')
    sys.exit(1)

r = cr.post('https://%s/LoginUser' % HOST, data=body, headers=H, impersonate='chrome110', timeout=25, verify=False)
cookie = None
for k, v in r.headers.items():
    if k.lower() == 'set-cookie':
        cookie = v.split(';')[0]
        break
_j = r.json()
if not _j.get('data'):
    print('❌ 登录返回空 data: err=%s msg=%s' % (_j.get('errorType'), _j.get('errorMessage'))); sys.exit(1)
pt = dec(_j['data'], FK)
try:
    pb = base64.b64decode(pt)
except Exception:
    pb = pt
m = re.search(rb'[0-9a-f]{32}', pb)
if not m:
    print('❌ 登录未拿到 session key')
    sys.exit(1)
key = m.group()
print('登录成功, key=%s...' % key.decode()[:10])
H['Cookie'] = cookie

# ---------- 拉排行榜 ----------
N = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
b = enc(b'\x08' + varint(N) + b'\x10' + varint(int(os.environ.get('BD2_SEASON', '48'))), key)
rr = cr.post('https://%s/ColosseumRanking' % HOST, data=b, headers=H, impersonate='chrome110', timeout=30, verify=False)
e = rr.json()
if not e.get('data'):
    print('❌ 排行榜无数据 err=%s' % e.get('errorType'))
    sys.exit(1)
pt2 = dec(e['data'], key)
try:
    pb2 = base64.b64decode(pt2)
except Exception:
    pb2 = pt2

players = []
for f, w, v in walk(pb2):
    if f != 1 or w != 2:
        continue
    d = {'uid': None, 'name': '', 'score': None, 'rank': None, 'guild': ''}
    for sf, sw, sv in walk(v):
        if sf == 1 and sw == 0:
            d['uid'] = sv
        elif sf == 2 and sw == 2:
            try:
                d['name'] = sv.decode('utf-8')
            except Exception:
                pass
        elif sf == 7 and sw == 2:
            for xf, xw, xv in walk(sv):
                if xf == 1 and xw == 0:
                    d['score'] = xv
                elif xf == 2 and xw == 0:
                    d['rank'] = xv
        elif sf == 6 and sw == 2:
            for xf, xw, xv in walk(sv):
                if xf == 2 and xw == 2:
                    try:
                        d['guild'] = xv.decode('utf-8')
                    except Exception:
                        pass
    if d['uid']:
        players.append(d)

players.sort(key=lambda x: (-(x['score'] or 0), x['rank'] or 9999))
print('解析到玩家 %d 名' % len(players))
if players:
    print('  第1名: %s 分=%s 名次=%s  uid=%s' % (players[0]['name'], players[0]['score'], players[0]['rank'], players[0]['uid']))
    print('  末位  : %s 分=%s' % (players[-1]['name'], players[-1]['score']))

io.open(os.path.join(HERE, 'ranking_full_new.json'), 'w', encoding='utf-8').write(
    json.dumps(players, ensure_ascii=False, indent=1))
io.open(os.path.join(HERE, 'uid_queue.txt'), 'w', encoding='utf-8', newline='').write(
    '\n'.join(str(p['uid']) for p in players) + '\n')
io.open(os.path.join(HERE, 'current_userkey.txt'), 'w', encoding='utf-8', newline='').write(key.decode())
print('已写 ranking_full_new.json / uid_queue.txt / current_userkey.txt')
