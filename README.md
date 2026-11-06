# BD2 黄金竞技场 · 阵容模拟与搜索工具

棕色尘埃2（Brown Desert 2 / BD2）黄金竞技场的**本地阵容模拟器 + 网页控制台**。

- 用完整战斗模拟（技能 / 庇佑 / 破度 / 爆发 / 站位 / 出手顺序）算胜率
- 搜索某个分段的高胜率阵容（粗筛 → 精修 → 先攻/后攻庇佑爬坡 → 复核）
- 网页控制台：查阵容库、看对战回放、手动测试任意阵容、保存自己的阵容

> 只做**本地计算**，对游戏没有任何写操作。

---

## 数据从哪来

```
云服务器（cloud/）          本地
  定时抓取排行榜阵容    →    同步数据（SFTP）
  去重合并成总库        →    本地建对手池 + 模拟搜索 + 网页控制台
```

**本地不需要任何账号数据就能跑模拟和搜索**，只要有一份 `阵容总库.jsonl`（从云端同步来的）。

---

## 快速开始

### 1. 环境

```bash
Python 3.9+
pip install -r requirements.txt      # pycryptodome / curl_cffi / paramiko
```

### 2. 起网页控制台

```bash
python bd2dash.py        # → http://127.0.0.1:8766
```

第一次打开是空的（还没有数据），先去接云端或自己抓一份数据。

### 3. 建对手池 + 搜索

```bash
python bd2tool.py pool                      # 用 阵容总库.jsonl 建对手池
python bd2tool.py search --lo 2000 --hi 2299 --quick
```

---

## 接云端数据（推荐）

云端只做「抓 + 去重入库」，本地只负责模拟，互不干扰。

**① 一次性部署**（在服务器上跑定时抓取）

```bash
# 自己的服务器信息写在 cloud/server.json（见 cloud/server.json.example）
python cloud/deploy_cloud.py          # 装依赖 + 传脚本 + 装 systemd 定时器
```

> 抓取需要一次游戏登录请求作为凭证。把它放在**服务器上**（部署时传），
> 只在服务器本地使用，`.gitignore` 已排除，不进仓库。

**② 本地配置**

```json
// cloud.json
{ "ssh": { "host": "你的服务器", "user": "root", "password": "…",
           "remote_dir": "/opt/bd2/capture" },
  "build_pool": 1 }
```

**③ 同步**

点控制台「↓ 同步云端数据」，或：

```bash
python bd2tool.py sync        # 拉数据 + 本地重建对手池
```

---

## 可选：标记「我拥有的服饰」

放一份 `my_box.json` 到根目录即可（不放也能用，服饰库会列出全部服饰）：

```json
{ "角色·服饰": { "break": 5, "burst": 3 } }
```

标记后，选服饰时你拥有的会高亮，其余显示为未拥有。

---

## 口径说明（判断胜率的前提）

```
我方（搜索候选 / 测试默认）  一律满破满爆：破度 5，该服饰有爆发就爆 3
对手（阵容库 / 对手池）      用抓到的他本人实际破度 / 爆发
```

搜索时勾「快速模式」= 粗筛小样本 + 精修只换人；
不勾 = 换人 + 换站位 + 换顺位，结果更准但慢 3~4 倍。

---

## 主要文件

```
bd2dash.py        网页控制台（HTTP 服务 + 内置前端）
bd2tool.py        命令行入口：capture / pool / search / verify / sync / status
_sim.py           技能与数值解析
_sim3.py          战斗流程与伤害计算
_s49fast.py       阵容搜索（粗筛 + 精修）
_s49bs4/bs5.py    后攻 / 先攻庇佑爬坡
build_pool.py     对手池构建
report_lineups.py 抓包 → 可读阵容报告
cloud/            云端定时抓取（systemd timer + 只读数据服务 + SFTP 同步）
```

## 免责

仅供个人研究与学习使用；游戏数据与角色版权归其权利人所有。
