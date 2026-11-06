# 云端抓取（可选）

服务器上定时抓取 → 去重入库；本地只负责同步。

## 部署

```bash
# 1) 服务器信息写在 cloud/server.json（照 cloud/server.json.example 填）
python cloud/deploy_cloud.py

# 2) 把游戏登录请求放到服务器上（部署时一起传过去）
```

装好后自动运行：抓取每 15~30 分钟一次，另外有个只读数据服务监听 8787。

## 本地同步

```bash
python bd2tool.py sync
```

或在控制台点「↓ 同步云端数据」。

## 常用命令（服务器上）

```bash
systemctl list-timers bd2-crawl.timer     # 下次抓取时间
systemctl start bd2-crawl.service         # 立刻抓一次
tail -f /opt/bd2/capture/logs/crawl_*.log # 看日志
```
