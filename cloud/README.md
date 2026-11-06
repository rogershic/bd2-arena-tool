# 云端抓取 + 本地同步（2026-11-07）

## 分工

```
云服务器（Ubuntu/Debian，每 15~30 分钟随机跑一次）
  ① 拉排行榜 → ② 建队列 → ③ 抓每个人阵容 → ④ 报告
  → ⑤ 入库（同 UID 覆盖）→ ⑥ 去重合并进【阵容总库.jsonl】→ ⑦ 写清单
  同时跑一个只读 HTTP 服务（8787），把总库/历史库给本地拉

本地（这台机器）
  控制台点「同步云端数据」→ 拉 阵容总库.jsonl / 阵容历史库.jsonl
  → 本地重建对手池（_opp_cache.pkl）→ 工具里就能看到最新数据
```

## 部署（一次性）

```bash
# 1) 先把公钥加到服务器
ssh-copy-id root@你的服务器IP

# 2) 在 capture 目录执行（会装依赖、传脚本、装 systemd 定时器、写 cloud.json）
bash cloud/deploy.sh root@你的服务器IP 你的口令

# 3) 把登录用的抓包放上去（抓取要用它登录，和本机同一套）
scp batch_capture_s49.jsonl live_session.json root@你的服务器IP:/opt/bd2/capture/
```

## 日常

```
· 服务器自动跑，不用管（systemctl list-timers bd2-crawl.timer 可看下次时间）
· 本地想要最新数据 → 控制台「阵容」标签点「同步云端数据」
  （或命令行 python bd2tool.py sync）
· 同步完会在本地重建对手池，然后阵容库/测试阵容立刻用新数据
```

## 常用命令

```bash
# 服务器上
systemctl list-timers bd2-crawl.timer     # 下次抓取时间
systemctl start bd2-crawl.service         # 立刻手动抓一次
tail -f /opt/bd2/capture/logs/crawl_*.log # 看日志
systemctl status bd2-serve.service        # 数据服务状态

# 本地
python _sync_cloud.py            # 同步 + 建池
python _sync_cloud.py --no-pool  # 只同步
```

## 注意事项

```
· 抓取用的是【你给的那个账号的登录抓包】，云服务器 IP 与常用地不同
  → 账号可能有异地登录提示；用小号更稳
· 版本号（b2_app_version / bundle）会随游戏更新失效
  → 抓取报 VERSION_CHECK 时，重新抓一次 /LoginUser 并更新 live_session.json
· 数据服务只读、要口令（cloud.json 里的 token），只暴露总库/历史库/my_box
· 服务器只做「抓 + 去重入库」，建对手池留在本地（省服务器 CPU/内存）
```
