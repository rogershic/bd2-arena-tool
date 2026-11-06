# -*- coding: utf-8 -*-
"""从云端服务器同步数据（阵容总库 / 历史库），可选本地重建对手池

两种方式（cloud.json 里配了 ssh 就用 SFTP，最稳；否则用 http url）：
    SFTP: {"ssh": {"host":..., "user":..., "password":..., "remote_dir":"/opt/bd2/capture"}}
    HTTP: {"url": "http://ip:8787", "token": "..."}

用法:
    python _sync_cloud.py            # 同步 + 建池
    python _sync_cloud.py --no-pool  # 只同步
"""
import io
import json
import os
import shutil
import sys
import time
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, 'cloud.json')
FILES = ('阵容总库.jsonl', '阵容历史库.jsonl')


def load_cfg(argv):
    cfg = {'url': '', 'token': '', 'build_pool': 1, 'ssh': {}}
    if os.path.exists(CFG):
        try:
            cfg.update(json.load(io.open(CFG, encoding='utf-8')))
        except Exception:
            pass
    for i, a in enumerate(argv):
        if a == '--url' and i + 1 < len(argv):
            cfg['url'] = argv[i + 1]
        if a == '--token' and i + 1 < len(argv):
            cfg['token'] = argv[i + 1]
    if '--no-pool' in argv:
        cfg['build_pool'] = 0
    return cfg


def http_get(url, timeout=600):
    req = urllib.request.Request(url, headers={'User-Agent': 'bd2-tool/1.0'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def sync_sftp(ssh, got_files):
    import paramiko
    rd = ssh.get('remote_dir') or '/opt/bd2/capture'
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(ssh['host'], port=int(ssh.get('port', 22)), username=ssh['user'],
                password=ssh.get('password') or '', timeout=25,
                look_for_keys=False, allow_agent=False)
    sftp = cli.open_sftp()
    try:
        man = json.loads(sftp.open(rd + '/cloud_manifest.json').read().decode('utf-8'))
        print('云端数据时间: %s' % man.get('ts'))
        for fn, info in (man.get('files') or {}).items():
            print('   %-18s %s 行  %.1f MB  更新 %s'
                  % (fn, info.get('lines'), (info.get('bytes') or 0) / 1048576,
                     info.get('mtime')))
        for fn in FILES:
            if fn not in (man.get('files') or {}):
                print('云端没有 %s，跳过' % fn)
                continue
            dst = os.path.join(HERE, fn)
            tmp = dst + '.downloading'
            print('下载 %s …' % fn, end='', flush=True)
            t0 = time.time()
            sftp.get(rd + '/' + fn, tmp)
            size = os.path.getsize(tmp)
            lines = sum(1 for _ in io.open(tmp, encoding='utf-8', errors='replace'))
            want = (man['files'][fn].get('lines') or 0)
            if want and abs(lines - want) > max(5, want * 0.01):
                os.remove(tmp)
                print(' 行数不符（%d vs %d），放弃' % (lines, want))
                continue
            if os.path.exists(dst):
                shutil.copy(dst, dst + '.bak_sync')
            os.replace(tmp, dst)
            print(' %.1f MB ✔ (%.0fs)' % (size / 1048576, time.time() - t0))
            got_files.append(fn)
        return man
    finally:
        try:
            sftp.close()
        except Exception:
            pass
        cli.close()


def sync_http(cfg, got_files):
    base = (cfg.get('url') or '').rstrip('/')
    tok = cfg.get('token') or ''
    q = '?k=' + urllib.parse.quote(tok)
    man = json.loads(http_get(base + '/manifest.json' + q, 60).decode('utf-8'))
    print('云端数据时间: %s' % man.get('ts'))
    for fn, info in (man.get('files') or {}).items():
        print('   %-18s %s 行  %.1f MB  更新 %s'
              % (fn, info.get('lines'), (info.get('bytes') or 0) / 1048576,
                 info.get('mtime')))
    for fn in FILES:
        if fn not in (man.get('files') or {}):
            continue
        dst = os.path.join(HERE, fn)
        tmp = dst + '.downloading'
        print('下载 %s …' % fn, end='', flush=True)
        data = http_get(base + '/file/' + urllib.parse.quote(fn) + q)
        io.open(tmp, 'wb').write(data)
        lines = data.count(b'\n')
        want = (man['files'][fn].get('lines') or 0)
        if want and abs(lines - want) > max(5, want * 0.01):
            os.remove(tmp)
            print(' 行数不符，放弃')
            continue
        if os.path.exists(dst):
            shutil.copy(dst, dst + '.bak_sync')
        os.replace(tmp, dst)
        print(' %.1f MB ✔' % (len(data) / 1048576))
        got_files.append(fn)
    return man


def main():
    cfg = load_cfg(sys.argv[1:])
    ssh = cfg.get('ssh') or {}
    got = []
    if ssh.get('host') and ssh.get('user'):
        print('用 SFTP 同步（%s）' % ssh['host'])
        try:
            man = sync_sftp(ssh, got)
        except Exception as e:
            print('SFTP 失败: %s' % e)
            return 1
    else:
        if not cfg.get('url') or not cfg.get('token'):
            print('还没有配置云端服务器。')
            print('  做法① 控制台点「↓ 同步云端数据」→ 会弹出配置窗，填地址/账号/密码即可')
            print('  做法② 手动创建 cloud.json，格式见 cloud/server.json.example')
            return 1
        print('用 HTTP 同步（%s）' % cfg['url'])
        try:
            man = sync_http(cfg, got)
        except Exception as e:
            print('HTTP 失败: %s' % e)
            return 1

    io.open(os.path.join(HERE, 'cloud_sync.json'), 'w', encoding='utf-8', newline='').write(
        json.dumps({'ts': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'remote_ts': man.get('ts'), 'files': len(got)},
                   ensure_ascii=False, indent=1))
    print('同步完成：%d 个文件，本地 %s' % (len(got), time.strftime('%H:%M')))

    if str(cfg.get('build_pool')) in ('1', 'True', 'true') and got:
        print('本地重建对手池 …')
        os.environ.setdefault('BD2_DB', '阵容总库.jsonl')
        os.environ.setdefault('BD2_ALL', '1')
        os.environ.setdefault('BD2_MINSCORE', '0')
        os.environ.setdefault('BD2_SEASON_TAG', '赛季49')
        import subprocess
        r = subprocess.run([sys.executable, '-u', os.path.join(HERE, 'build_pool.py')],
                           cwd=HERE)
        print('建池退出码:', r.returncode)
    return 0


if __name__ == '__main__':
    sys.exit(main())
