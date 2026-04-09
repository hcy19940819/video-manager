# 🎬 视频管家 v2.0

> 高度整合的本地视频管理系统 - 单文件设计，简洁高效

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## ✨ 特性

- 🔍 **视频去重** - 智能哈希比对
- 👤 **AI人物识别** - 人脸识别，以图搜视频
- 🗂️ **库管理** - 可视化Web界面
- ⚡ **三档扫描** - 简单/快速/深度模式
- 💤 **硬盘保护** - 可配置休息间隔

## 📦 安装

```bash
# 安装依赖
pip install opencv-python pillow numpy tqdm flask insightface

# 初始化
python 视频管家.py init
```

## 🚀 使用

### 命令行

```bash
# 扫描视频
python 视频管家.py scan "/视频路径" --mode fast

# 查找重复
python 视频管家.py dup

# 列出人物
python 视频管家.py persons

# 库管理
python 视频管家.py lib add "/视频路径"
python 视频管家.py lib list

# 启动Web界面
python 视频管家.py web --port 5000
```

### 扫描模式

| 模式 | 说明 | 速度 |
|------|------|------|
| `simple` | 仅去重，无AI | ⚡⚡⚡ |
| `fast` | 去重+AI适中采样 | ⚡⚡ |
| `deep` | 去重+AI密集采样 | ⚡ |

### Web界面

访问 `http://localhost:5000`

- 📊 统计面板
- 📚 库管理
- ➕ 添加视频库

## 📁 项目结构

```
视频管家整合/
├── 视频管家.py      # 单文件核心（全部功能）
├── README.md
└── data/            # 数据目录（自动生成）
    └── video_manager.db
```

## 📝 许可证

MIT License
