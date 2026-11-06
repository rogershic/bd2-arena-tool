# -*- coding: utf-8 -*-
"""部署到华为云服务器（密码登录，用 paramiko）

用法: python cloud/deploy_cloud.py
配置在 cloud/server.json（自动生成/可手改）
"""
import io
import json
import os
import posixpath
import sys
import time

import paramiko

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # capture 根目录
CFG = os.path.join(HERE, 'cloud', 'server.json')

DEFAULT = {
    'host': '',
    'port': 22,
    'user': 'root',
    'password': '',
    'remote_dir': '/opt/bd2/capture',
    'data_port': 8787,
    'token': '',
}

# 需要上传的文件（脚本 + 数据字典 + 抓取用的登录抓包）
UPLOAD = [
    '_s47_fetch_rank.py', '_fetch_all_now.py', 'report_lineups.py',
    '_archive_lineups.py', '_merge_pool.py', 'build_pool.py',
    '_sim.py', '_sim3.py', '_zh.py', '_mem.py', 'bd2cfg.py',
    'season_map.json', 'name_map.json', 'chars_db.json', 'en2cn.json',
    'bless_id_map.json', 'costume_cost_byid_s49.json', 'my_box.json',
    # ★ 名字映射表（不传的话服务器抓回来全是 role3/id304，高分阵容会被整条丢掉）
    'modding_all.txt', 'costume_id_map.txt', 'cn_map.txt', 'role_id_map.txt',
    'ranking_names.json',
    'batch_capture_s49.jsonl', 'live_session.json',
    '阵容历史库.jsonl',
    'cloud/crawl.sh', 'cloud/serve.py',
]


def load_cfg():
    cfg = dict(DEFAULT)
    if os.path.exists(CFG):
        try:
            cfg.update(json.load(io.open(CFG, encoding='utf-8')))
        except Exception:
            pass
    if not cfg.get('password'):
        cfg['password'] = os.environ.get('BD2_SSH_PASS', '')
    if not cfg.get('token'):
        cfg['token'] = os.environ.get('BD2_CLOUD_TOKEN', '') or ('bd2' + str(int(time.time()))[-6:])
    return cfg


def save_cfg(cfg):
    io.open(CFG, 'w', encoding='utf-8', newline='').write(
        json.dumps(cfg, ensure_ascii=False, indent=1))


def sh(cli, cmd, timeout=900, quiet=False):
    if not quiet:
        print('  $ %s' % cmd.split('\n')[0][:110])
    si, so, se = cli.exec_command(cmd, timeout=timeout, get_pty=True)
    out = so.read().decode('utf-8', 'replace')
    err = se.read().decode('utf-8', 'replace')
    code = so.channel.recv_exit_status()
    if not quiet and out.strip():
        for line in out.strip().split('\n')[-14:]:
            print('    ' + line[:160])
    if code != 0 and err.strip() and not quiet:
        print('    [stderr] ' + err.strip().split('\n')[-1][:200])
    return code, out, err


def main():
    cfg = load_cfg()
    if not cfg.get('password'):
        print('缺密码：在 cloud/server.json 里填 password，或设环境变量 BD2_SSH_PASS')
        return 1
    save_cfg(cfg)
    rd = cfg['remote_dir']
    print('连接 %s@%s:%s …' % (cfg['user'], cfg['host'], cfg['port']))
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(cfg['host'], port=cfg['port'], username=cfg['user'],
                password=cfg['password'], timeout=25, banner_timeout=25)
    print('  连接成功')

    print('① 检查系统与 python')
    code, out, _ = sh(cli, 'cat /etc/os-release | head -2; python3 -V; nproc; free -m | head -2')
    if 'python3' not in out:
        print('  服务器没有 python3，尝试安装')
        sh(cli, 'apt-get update -qq && apt-get install -y -qq python3 python3-pip', timeout=1200)

    print('② 安装 python 依赖')
    sh(cli, 'python3.9 -m pip install --quiet --upgrade pycryptodome curl_cffi 2>&1 | tail -3 || '
            'python3.9 -m pip install --quiet --break-system-packages --upgrade pycryptodome curl_cffi 2>&1 | tail -3',
       timeout=1800)
    code, out, _ = sh(cli, 'python3.9 -c "import Crypto, curl_cffi; print(\'deps ok\')"', quiet=True)
    print('   依赖检查: %s' % out.strip())

    print('③ 建目录')
    sh(cli, 'mkdir -p %s/logs %s/cloud' % (rd, rd))

    print('④ 上传文件')
    sftp = cli.open_sftp()
    sent = 0
    for name in UPLOAD:
        local = os.path.join(HERE, name.replace('/', os.sep))
        if not os.path.exists(local):
            print('   跳过（本地没有）: %s' % name)
            continue
        remote = posixpath.join(rd, name)
        try:
            sftp.put(local, remote)
            sent += 1
            print('   ↑ %-32s %8.1f KB' % (name, os.path.getsize(local) / 1024))
        except Exception as e:
            print('   ✘ %s: %s' % (name, e))
    sftp.close()
    print('   共上传 %d 个文件' % sent)

    print('⑤ 写 systemd 服务')
    unit_serve = """[Unit]
Description=BD2 cloud data server
After=network.target

[Service]
Type=simple
Environment=BD2_DIR=%s
Environment=BD2_TOKEN=%s
Environment=BD2_PORT=%d
ExecStart=/usr/bin/python3.9 %s/cloud/serve.py %d
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
""" % (rd, cfg['token'], cfg['data_port'], rd, cfg['data_port'])

    unit_crawl = """[Unit]
Description=BD2 crawl (fetch + dedupe into library)

[Service]
Type=oneshot
Environment=BD2_DIR=%s
Environment=BD2_N=1000
ExecStart=/bin/bash %s/cloud/crawl.sh
TimeoutStartSec=1800
""" % (rd, rd)

    unit_timer = """[Unit]
Description=Run BD2 crawl every 15min, random extra delay 0-15min (=15~30min)

[Timer]
OnBootSec=5min
OnUnitActiveSec=15min
RandomizedDelaySec=15min
AccuracySec=1min
Persistent=true

[Install]
WantedBy=timers.target
"""

    for path, body in (('/etc/systemd/system/bd2-serve.service', unit_serve),
                       ('/etc/systemd/system/bd2-crawl.service', unit_crawl),
                       ('/etc/systemd/system/bd2-crawl.timer', unit_timer)):
        sf = cli.open_sftp()
        with sf.file(path, 'w') as f:
            f.write(body)
        sf.close()
        print('   写入 %s' % path)
    sh(cli, 'chmod +x %s/cloud/crawl.sh' % rd, quiet=True)
    sh(cli, 'systemctl daemon-reload && systemctl enable --now bd2-serve.service '
            '&& systemctl enable --now bd2-crawl.timer')
    sh(cli, 'systemctl is-active bd2-serve.service; '
            'systemctl list-timers bd2-crawl.timer --no-pager | head -3')

    print('⑥ 先在服务器跑一次抓取（看能不能通）')
    code, out, err = sh(cli, 'systemctl start bd2-crawl.service', timeout=1800)
    code, out, _ = sh(cli, 'ls -lt %s/logs | head -3; tail -n 12 $(ls -t %s/logs/crawl_*.log | head -1)'
                     % (rd, rd))
    cli.close()

    print('⑦ 写本地 cloud.json')
    local_cfg = {'url': 'http://%s:%d' % (cfg['host'], cfg['data_port']),
                 'token': cfg['token'], 'build_pool': 1}
    io.open(os.path.join(HERE, 'cloud.json'), 'w', encoding='utf-8', newline='').write(
        json.dumps(local_cfg, ensure_ascii=False, indent=1))
    print('   ' + json.dumps(local_cfg, ensure_ascii=False))
    print('\n完成。控制台点「↓ 同步云端数据」即可拉取。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
