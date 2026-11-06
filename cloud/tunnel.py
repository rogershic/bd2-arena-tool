# -*- coding: utf-8 -*-
"""SSH 隧道：把远端的 8787 映射到本地 127.0.0.1:<本地端口>，不用开安全组端口"""
import selectors
import socket
import threading

import paramiko


class Tunnel:
    def __init__(self, host, port, user, password, remote_port, local_port=0):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.remote_port = remote_port
        self.local_port = local_port
        self.cli = None
        self.srv = None
        self._stop = threading.Event()
        self._threads = []

    def start(self, timeout=25):
        self.cli = paramiko.SSHClient()
        self.cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.cli.connect(self.host, port=self.port, username=self.user,
                         password=self.password, timeout=timeout,
                         look_for_keys=False, allow_agent=False)
        transport = self.cli.get_transport()
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(('127.0.0.1', self.local_port))
        srv.listen(32)
        self.local_port = srv.getsockname()[1]
        self.srv = srv
        t = threading.Thread(target=self._accept_loop, args=(transport,), daemon=True)
        t.start()
        self._threads.append(t)
        return self.local_port

    def _accept_loop(self, transport):
        while not self._stop.is_set():
            try:
                conn, _ = self.srv.accept()
            except OSError:
                return
            t = threading.Thread(target=self._handle, args=(conn, transport), daemon=True)
            t.start()
            self._threads.append(t)

    def _handle(self, conn, transport):
        try:
            chan = transport.open_channel('direct-tcpip',
                                          ('127.0.0.1', self.remote_port),
                                          conn.getpeername())
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            return
        sel = selectors.DefaultSelector()
        sel.register(conn, selectors.EVENT_READ, 'local')
        sel.register(chan, selectors.EVENT_READ, 'remote')
        try:
            while True:
                for key, _ in sel.select(timeout=1):
                    if key.data == 'local':
                        data = conn.recv(65536)
                        if not data:
                            chan.close()
                            return
                        chan.sendall(data)
                    else:
                        data = chan.recv(65536)
                        if not data:
                            conn.close()
                            return
                        conn.sendall(data)
        except Exception:
            pass
        finally:
            try:
                sel.close()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
            try:
                chan.close()
            except Exception:
                pass

    def stop(self):
        self._stop.set()
        try:
            self.srv.close()
        except Exception:
            pass
        try:
            self.cli.close()
        except Exception:
            pass
