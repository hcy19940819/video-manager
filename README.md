# 🎬 视频管家 v3.0 - 终极整合版

整合自 hcy19940819/GitHub 私有仓库的 4 个项目

## ✨ 整合功能

| 来源项目 | 功能 | 状态 |
|---------|------|------|
| VideoDedup | 🔍 多层pHash去重 | ✅ 已整合 |
| VideoFaceManager | 👤 花名册学习 | ✅ 已整合 |
| VideoFaceManager | 🔎 以图搜视频 | ✅ 已整合 |
| video-manager | 🗂️ 库管理 | ✅ 已整合 |
| video-manager | 🌐 Web界面 | ✅ 已整合 |

## 🚀 安装

```bash
pip install opencv-python pillow numpy tqdm flask insightface
python 视频管家.py init
```

## 📖 使用

### 1. 扫描视频
```bash
# 快速模式
python 视频管家.py scan "/视频路径" --mode fast

# 深度模式（含AI识别）
python 视频管家.py scan "/视频路径" --mode deep

# 增量扫描
python 视频管家.py scan "/视频路径" --incremental
```

### 2. 查找重复视频
```bash
# 多层pHash去重
python 视频管家.py dup

# 快速模式（仅快速pHash）
python 视频管家.py dup --mode quick
```

### 3. 花名册学习
```bash
# 学习已分类视频
python 视频管家.py roster learn "/已分类视频"

# 列出花名册
python 视频管家.py roster list

# 识别未分类视频
python 视频管家.py roster identify "/未分类视频"
```

### 4. 以图搜视频
```bash
python 视频管家.py search "/查询图片.jpg" --lib "/视频库路径"
```

### 5. 库管理
```bash
python 视频管家.py lib add "/视频路径"
python 视频管家.py lib list
```

### 6. Web界面
```bash
python 视频管家.py web --port 5000
```

## 🏗️ 架构

```
单文件设计：视频管家.py (1500+行)
├── 数据库类：统一SQLite管理
├── 视频处理器：多层指纹+人物识别
├── 花名册管理器：学习+识别
├── 图片搜索引擎：以图搜视频
├── 库管理器：视频库管理
└── Web界面：Flask可视化
```

## 📁 数据目录

```
data/
├── video_master.db      # 统一数据库
├── faces/               # 花名册人脸数据
└── screenshots/         # 截图
```

## 📊 多层去重原理

1. **文件大小+时长** → 快速分组
2. **快速pHash**（64位，中间帧）→ 初步筛选
3. **详细pHash序列**（关键帧序列）→ 精确匹配
4. **文件MD5**（前1MB）→ 完全重复检测

## 🎯 花名册工作流程

```
已分类视频/           ← 学习
├── 张三/
├── 李四/
└── 王五/
        ↓ roster learn
        ↓ 提取平均特征
        
未分类视频/           ← 识别
├── video1.mp4  →  张三 (85%)
└── video2.mp4  →  李四+王五 (72%)
```

## 📄 许可证

MIT License
