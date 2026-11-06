#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""云端只读数据服务：给本地工具拉取 阵容总库 / 阵容历史库 / 清单

启动:
    BD2_DIR=/opt/bd2/capture BD2_TOKEN=你的口令 python3 serve.py 8787

接口（都要带 ?k=口令）:
    /manifest.json              数据清单（时间/行数/大小）
    /file/<文件名>              下载白名单内的文件
"""
import io
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.parse
from urllib.parse import urlparse, parse_qs, unquote

DIR = os.environ.get('BD2_DIR', '/opt/bd2/capture')
TOKEN = os.environ.get('BD2_TOKEN', '')
PORT = int(os.environ.get('BD2_PORT', '8787'))
ALLOW = {'阵容总库.jsonl', '阵容历史库.jsonl', 'cloud_manifest.json', 'my_box.json', 'ranking_full_new.json'}

if not TOKEN:
    print('必须设置 BD2_TOKEN 环境变量（本地工具用它拉数据）')
    sys.exit(1)


class H(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        ts = time.strftime('%m-%d %H:%M:%S')
        sys.stderr.write('[%s] %s %s\n' % (ts, self.address_string(), fmt % args))

    def _send(self, code, body, ctype='text/plain; charset=utf-8', extra=None):
        if isinstance(body, str):
            body = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if (q.get('k') or [''])[0] != TOKEN:
            return self._send(403, 'forbidden')

        if u.path in ('/', '/manifest.json'):
            p = os.path.join(DIR, 'cloud_manifest.json')
            if not os.path.exists(p):
                return self._send(404, json.dumps({'ok': False, 'msg': '还没有抓过数据'},
                                                  ensure_ascii=False))
            return self._send(200, io.open(p, 'rb').read(), 'application/json; charset=utf-8')

        if u.path.startswith('/file/'):
            name = unquote(u.path[len('/file/'):])
            if name not in ALLOW:
                return self._send(403, 'not allowed')
            p = os.path.join(DIR, name)
            if not os.path.exists(p):
                return self._send(404, 'not found')
            data = io.open(p, 'rb').read()
            # ★ HTTP 头只能用 latin-1，中文文件名会报错（之前 502 就是这个）→ 用 RFC5987 编码
            fn_ascii = urllib.parse.quote(name)
            return self._send(200, data, 'application/octet-stream',
                              {'Content-Disposition':
                               "attachment; filename*=UTF-8''%s" % fn_ascii})

        return self._send(404, 'not found')


if __name__ == '__main__':
    if len(sys.argv) > 1:
        PORT = int(sys.argv[1])
    srv = ThreadingHTTPServer(('0.0.0.0', PORT), H)
    print('云端数据服务已启动: 0.0.0.0:%d  dir=%s' % (PORT, DIR), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('已停止')
