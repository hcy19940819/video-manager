# 🎬 视频管家 v4.0 - AI-Native 视频管理系统

像聊天一样管理你的视频库。

## 🚀 快速开始

```bash
# 安装依赖
pip install flask flask-cors opencv-python

# 启动 Web 界面
python 视频管家.py web --port 5000

# 或使用 Kimi API 增强（可选）
export KIMI_API_KEY="your-api-key"
python 视频管家.py web
```

访问 http://localhost:5000

## ✨ 核心功能

| 功能 | 说明 |
|------|------|
| 🤖 AI 对话 | 自然语言控制，支持本地/Kimi 双引擎 |
| 📁 视频库 | 海报墙浏览，内置播放器 |
| 👤 花名册 | 人脸识别，以图搜视频 |
| 🔍 智能去重 | 四层 pHash 检测重复视频 |
| 📋 任务队列 | 异步处理，实时进度显示 |

## 🗂️ 项目结构

```
.
├── 视频管家.py          # 主程序 (~2100行，单文件架构)
├── requirements.txt     # 依赖列表
├── README.md            # 本文件
├── docs/                # 文档
│   ├── v4.0_README.md   # 详细功能文档
│   ├── 使用手册.md      # 使用指南
│   ├── 产品设计白皮书.md
│   └── 竞品对比分析.md
├── archive/             # 历史版本存档
│   ├── v1/              # videodedup 早期版本
│   ├── v2/              # VideoFaceManager 版本
│   └── v3/              # 视频管家 v3.0
└── data/                # 数据目录
```

## 📖 更多文档

- [详细功能说明](docs/v4.0_README.md)
- [使用手册](docs/使用手册.md)
- [产品设计](docs/产品设计白皮书.md)

## 📝 使用示例

```
💬 "扫描下载文件夹"
💬 "找包含小宝的视频"
💬 "找重复视频"
💬 "学习小宝的视频"
💬 "查看统计"
```

## 📄 License

MIT
