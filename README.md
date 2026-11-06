# BD2 黄金竞技场 · 阵容模拟与搜索工具

## 免安装版（推荐，不用装 Python）

下载：<https://github.com/rogershic/bd2-arena-tool/releases/latest>

解压后双击 **`启动控制台.bat`**，浏览器自动打开 <http://127.0.0.1:8766>

## 源码运行

```bash
pip install -r requirements.txt     # 需要 Python 3.9+
python bd2dash.py
```

浏览器打开 <http://127.0.0.1:8766>

第一次点「↓ 同步云端数据」会弹窗，填一次数据地址（或服务器 SSH），
配置保存在 `~/.bd2-arena/cloud.json`，之后重新下载也不用再填。

## 常用命令

```bash
python bd2tool.py status                          # 看当前状态
python bd2tool.py pool                            # 建对手池
python bd2tool.py search --lo 2000 --hi 2299      # 搜索该分段阵容（慢速）
python bd2tool.py search --lo 2000 --hi 2299 --quick   # 快速模式
python bd2tool.py sync                            # 同步云端数据
```

控制台里对应的按钮：`③ 搜索该分段阵容`、`■ 停止搜索`、`↓ 同步云端数据`。
