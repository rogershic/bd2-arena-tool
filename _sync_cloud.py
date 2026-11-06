# -*- coding: utf-8 -*-
"""从云端同步数据（阵容总库 / 历史库），并可选本地重建对手池

cloud.json 支持两种写法（填一种就行）：

① 数据地址（最简单，公开链接不用 token）
   {"url": "https://你的域名/bd2/阵容总库.jsonl", "build_pool": 1}
   {"url": "https://你的域名/bd2",              "build_pool": 1}   ← 目录也行，会找 manifest.json

② SSH 服务器（走 SFTP，不用开数据端口）
   {"ssh": {"host":"1.2.3.4","user":"root","password":"...","remote_dir":"/opt/bd2/capture"},
    "build_pool": 1}

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


def _cfg_path():
    """配置优先级：环境变量 > 用户目录(%USERPROFILE%/.bd2-arena/cloud.json) > 工具目录"""
    env = os.environ.get('BD2_CLOUD_CFG')
    if env:
        return env
    home = os.path.expanduser('~')
    user_cfg = os.path.join(home, '.bd2-arena', 'cloud.json')
    if os.path.exists(user_cfg):
        return user_cfg
    local = os.path.join(HERE, 'cloud.json')
    if os.path.exists(local):
        return local
    return user_cfg      # 都没有时，就写用户目录（重装不丢）


CFG = _cfg_path()
FILES = ('阵容总库.jsonl', '阵容历史库.jsonl', 'ranking_full_new.json')


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


def _kq(token):
    return ('?k=' + urllib.parse.quote(token)) if token else ''


def sync_url(cfg, got):
    """① 数据地址模式"""
    url = (cfg.get('url') or '').strip()
    tok = cfg.get('token') or ''
    if url.endswith(('.jsonl', '.json')):
        base = url.rsplit('/', 1)[0]
        direct = url
    else:
        base = url.rstrip('/')
        direct = ''
    # 先试 manifest（有行数校验，更稳）
    man = None
    try:
        man = json.loads(http_get(base + '/manifest.json' + _kq(tok), 30).decode('utf-8'))
        print('云端数据时间: %s' % man.get('ts'))
        for fn, info in (man.get('files') or {}).items():
            print('   %-18s %s 行  %.1f MB  更新 %s'
                  % (fn, info.get('lines'), (info.get('bytes') or 0) / 1048576,
                     info.get('mtime')))
    except Exception:
        man = None

    targets = []
    if man:
        for fn in FILES:
            if fn in (man.get('files') or {}):
                targets.append((fn, base + '/file/' + urllib.parse.quote(fn) + _kq(tok),
                                man['files'][fn].get('lines') or 0))
    else:
        # 没 manifest：直接按地址下（能给几个给几个）
        if direct:
            targets.append((os.path.basename(direct), direct, 0))
            for fn in FILES:
                if fn != os.path.basename(direct):
                    targets.append(('' if False else fn,
                                    base + '/' + urllib.parse.quote(fn) + _kq(tok), 0))
        else:
            for fn in FILES:
                targets.append((fn, base + '/' + urllib.parse.quote(fn) + _kq(tok), 0))

    for fn, u, want in targets:
        dst = os.path.join(HERE, fn)
        tmp = dst + '.downloading'
        print('下载 %s …' % fn, end='', flush=True)
        try:
            data = http_get(u, 600)
        except Exception:
            # serve.py 的路径是 /file/xxx；普通静态服务器是 /xxx → 再试一次
            alt = u.replace('/file/', '/')
            if alt == u:
                print(' 跳过（下载失败）')
                continue
            try:
                data = http_get(alt, 600)
            except Exception as e:
                print(' 跳过（%s）' % str(e)[:60])
                continue
        io.open(tmp, 'wb').write(data)
        lines = data.count(b'\n')
        if want and abs(lines - want) > max(5, want * 0.01):
            os.remove(tmp)
            print(' 行数不符（%d vs %d），放弃' % (lines, want))
            continue
        if os.path.exists(dst):
            shutil.copy(dst, dst + '.bak_sync')
        os.replace(tmp, dst)
        print(' %.1f MB ✔' % (len(data) / 1048576))
        got.append(fn)
    return man


def sync_sftp(ssh, got):
    """② SSH/SFTP 模式"""
    import paramiko
    rd = ssh.get('remote_dir') or '/opt/bd2/capture'
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(ssh['host'], port=int(ssh.get('port', 22)), username=ssh['user'],
                password=ssh.get('password') or '', timeout=25,
                look_for_keys=False, allow_agent=False)
    sftp = cli.open_sftp()
    man = {}
    try:
        try:
            man = json.loads(sftp.open(rd + '/cloud_manifest.json').read().decode('utf-8'))
            print('云端数据时间: %s' % man.get('ts'))
        except Exception:
            man = {'files': {fn: {} for fn in FILES}}
        for fn in FILES:
            dst = os.path.join(HERE, fn)
            tmp = dst + '.downloading'
            print('下载 %s …' % fn, end='', flush=True)
            try:
                sftp.get(rd + '/' + fn, tmp)
            except Exception as e:
                print(' 跳过（%s）' % str(e)[:50])
                continue
            size = os.path.getsize(tmp)
            if os.path.exists(dst):
                shutil.copy(dst, dst + '.bak_sync')
            os.replace(tmp, dst)
            print(' %.1f MB ✔' % (size / 1048576))
            got.append(fn)
        return man
    finally:
        try:
            sftp.close()
        except Exception:
            pass
        cli.close()


def main():
    cfg = load_cfg(sys.argv[1:])
    ssh = cfg.get('ssh') or {}
    got = []
    man = {}
    if cfg.get('url'):
        print('同步方式: 数据地址 %s' % cfg['url'])
        man = sync_url(cfg, got)
    elif ssh.get('host') and ssh.get('user'):
        print('同步方式: SSH 服务器 %s' % ssh['host'])
        try:
            man = sync_sftp(ssh, got)
        except Exception as e:
            print('SFTP 失败: %s' % e)
            return 1
    else:
        print('还没有配置数据来源。两种做法：')
        print('  ① 控制台点「↓ 同步云端数据」→ 弹窗里填【数据地址】或【服务器 SSH】')
        print('  ② 手动创建 cloud.json，格式见 cloud/server.json.example')
        return 1

    io.open(os.path.join(HERE, 'cloud_sync.json'), 'w', encoding='utf-8', newline='').write(
        json.dumps({'ts': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'remote_ts': (man or {}).get('ts'), 'files': len(got)},
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
