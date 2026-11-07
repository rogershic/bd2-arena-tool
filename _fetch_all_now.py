# -*- coding: utf-8 -*-
"""一键抓取: 登录 -> 刷新 session/key -> 并发拉前 N 名的 ColosseumRankDetail
无代理版(直连 api-cf.bd2.pmang.cloud)
用法: python _fetch_all_now.py [N]
"""
import io, os, sys, json, base64, re, threading, time
from Crypto.Cipher import AES
from concurrent.futures import ThreadPoolExecutor
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from curl_cffi import requests as cffi_req

import sys as _bd2sys
HERE = (os.environ.get('BD2_HOME') or
        (os.path.dirname(os.path.abspath(_bd2sys.executable))
         if getattr(_bd2sys, 'frozen', False)
         else os.path.dirname(os.path.abspath(__file__))))
FIXED_KEY = b'abcdefghijkrstuv024680wxyzlmnopq'
HOST = 'api-cf.bd2.pmang.cloud'
URL = 'https://%s/ColosseumRankDetail' % HOST
LOGIN = 'https://%s/LoginUser' % HOST
OUT = os.path.join(HERE, 'piggy_raw.jsonl')

HDRS = {
    'Content-Type': 'multipart/form-datas',
    'User-Agent': 'UnityPlayer/2022.3.62f2 (UnityWebRequest/1.0, libcurl/8.10.1-DEV)',
    'Accept': '*/*',
    'b2_app_version': '2.37.13',
    'b2_bundle_version': '20261022174708',
    'market_type': '6',
    'x-unity-version': '2022.3.62f2',
}


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

HDRS = _load_hdrs(HDRS)


def _pad(b):
    n = 16 - (len(b) % 16)
    return b + bytes([n]) * n


def varint(n):
    out = b''
    while True:
        x = n & 0x7f
        n >>= 7
        out += bytes([x | (0x80 if n else 0)])
        if not n:
            return out


def login():
    rows = []
    for l in io.open(os.path.join(HERE, os.environ.get('BD2_LOGIN_FILE', 'req_dump.jsonl')), encoding='utf-8'):
        try:
            rows.append(json.loads(l))
        except Exception:
            continue
    lu = [r for r in rows if r.get('path', '').endswith('/LoginUser') and r.get('req_body_b64')][-1]
    body = base64.b64decode(lu['req_body_b64'])
    r = cffi_req.put(LOGIN, data=body, headers=HDRS, impersonate='chrome110', timeout=20, verify=False)
    cookie = None
    for k, v in r.headers.items():
        if k.lower() == 'set-cookie':
            cookie = v.split(';')[0]
            break
    env = r.json()
    data = env.get('data')
    userkey = None
    if data:
        pt = AES.new(FIXED_KEY, AES.MODE_CBC, iv=b'\x00' * 16).decrypt(base64.b64decode(data))
        n = pt[-1]
        if 1 <= n <= 16:
            pt = pt[:-n]
        pb = base64.b64decode(pt)
        m = re.search(rb'[0-9a-f]{32}', pb)
        if m:
            userkey = m.group().decode()
    return cookie, userkey


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    cookie, userkey = login()
    print('登录: key=%s cookie=%s' % (userkey, (cookie or '')[:24]))
    if not cookie or not userkey:
        print('登录失败'); return

    # 持久化会话
    # ★★★ 2026-10-24 修 BUG: 不能把 hdrs 写成空，会把真实请求头冲掉（导致后续全部 NOT_FOUND_SESSION）
    _old_hdrs = {}
    try:
        _old_hdrs = (json.load(io.open(os.path.join(HERE, 'live_session.json'), encoding='utf-8')) or {}).get('hdrs') or {}
    except Exception:
        pass
    if not _old_hdrs:
        _old_hdrs = dict(HDRS)
    json.dump({'ts': time.strftime('%Y-%m-%dT%H:%M:%S'), 'cookie': cookie, 'hdrs': _old_hdrs, 'host': HOST},
              io.open(os.path.join(HERE, 'live_session.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    io.open(os.path.join(HERE, 'current_userkey.txt'), 'w').write(userkey)
    old = ''
    p = os.path.join(HERE, 'userkey_history.txt')
    if os.path.exists(p):
        old = io.open(p, encoding='utf-8').read()
    if userkey not in old:
        io.open(p, 'a', encoding='utf-8').write(userkey + '\n')

    KEY = userkey.encode()
    q = [int(x) for x in io.open(os.path.join(HERE, 'uid_queue.txt'), encoding='utf-8').read().split() if x.strip().isdigit()][:N]
    got = set()
    if os.path.exists(OUT):
        for l in io.open(OUT, encoding='utf-8'):
            try:
                got.add(int(json.loads(l)['uid']))
            except Exception:
                pass
    todo = [u for u in q if u not in got]
    print('队列 %d 名, 已有 %d, 待抓 %d' % (len(q), len(q) - len(todo), len(todo)))

    hdrs = dict(HDRS); hdrs['Cookie'] = cookie
    seq = [1000]   # ★ 2026-10-23: 序号必须 ≥1000，否则 HTTP 401
    lock = threading.Lock()
    stat = {'ok': 0, 'fail': 0}

    def enc(uid, sq):
        proto = b'\x08' + varint(sq) + b'\x10' + varint(uid)
        return base64.b64encode(AES.new(KEY, AES.MODE_CBC, iv=b'\x00' * 16).encrypt(_pad(base64.b64encode(proto)))).decode()

    def one(uid):
        for attempt in range(3):
            with lock:
                seq[0] += 1
                sq = seq[0]      # ★ 每次重试都取新序号（旧序号用过就 401）
            try:
                rr = cffi_req.put(URL, data=enc(uid, sq), headers=hdrs, impersonate='chrome110', timeout=20, verify=False)
                env = rr.json()
                rec = {'ts': time.strftime('%Y-%m-%dT%H:%M:%S'), 'path': '/ColosseumRankDetail',
                       'uid': uid, 'resp_len': len(rr.text), 'data': env.get('data'),
                       'err': env.get('errorType'), 'msg': env.get('errorMessage'), 'key': userkey}
                if env.get('data') and not env.get('errorType'):
                    return rec
                time.sleep(0.6)
            except Exception:
                time.sleep(0.8)
        return None

    def _save(rec):
        with lock:
            io.open(OUT, 'a', encoding='utf-8').write(json.dumps(rec, ensure_ascii=False) + '\n')
            stat['ok'] += 1

    t0 = time.time()
    failed = []
    with ThreadPoolExecutor(max_workers=5) as ex:
        for i, (uid, rec) in enumerate(zip(todo, ex.map(one, todo)), 1):
            if rec:
                _save(rec)
            else:
                stat['fail'] += 1
                failed.append(uid)
            if i % 25 == 0:
                print('  进度 %d/%d  成功%d 失败%d  %.0fs' % (i, len(todo), stat['ok'], stat['fail'], time.time() - t0))

    # ★★★ 2026-11-06 用户要求: 失败的自动补抓（最多 3 轮，每轮降低并发、拉长间隔）
    ROUNDS = int(os.environ.get('RETRY_ROUNDS', '3') or 3)
    for rnd in range(1, ROUNDS + 1):
        if not failed:
            break
        batch = list(failed)
        failed = []
        time.sleep(2 + rnd)
        print('  补抓第 %d 轮：%d 个…' % (rnd, len(batch)))
        with ThreadPoolExecutor(max_workers=max(1, 5 - rnd)) as ex:
            for uid, rec in zip(batch, ex.map(one, batch)):
                if rec:
                    stat['fail'] -= 1
                    _save(rec)
                else:
                    failed.append(uid)
        print('    第 %d 轮补抓后仍失败 %d 个' % (rnd, len(failed)))

    fp = os.path.join(HERE, 'failed_uids.txt')
    if failed:
        io.open(fp, 'w', encoding='utf-8').write('\n'.join(str(u) for u in failed))
        print('  仍失败 %d 个，已写入 failed_uids.txt' % len(failed))
    elif os.path.exists(fp):
        os.remove(fp)

    print('完成: 成功 %d, 失败 %d, 用时 %.0fs' % (stat['ok'], len(failed), time.time() - t0))


if __name__ == '__main__':
    main()
