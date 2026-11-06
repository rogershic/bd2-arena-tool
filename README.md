# BD2 黄金竞技场 · 阵容模拟与搜索工具

## 安装

```bash
pip install -r requirements.txt
```

需要 Python 3.9+

## 运行

```bash
python bd2dash.py
```

浏览器打开 <http://127.0.0.1:8766>

## 常用命令

```bash
python bd2tool.py status                          # 看当前状态
python bd2tool.py pool                            # 建对手池
python bd2tool.py search --lo 2000 --hi 2299      # 搜索该分段阵容（慢速）
python bd2tool.py search --lo 2000 --hi 2299 --quick   # 快速模式
python bd2tool.py sync                            # 同步云端数据
```

控制台里对应的按钮：`③ 搜索该分段阵容`、`■ 停止搜索`、`↓ 同步云端数据`。
