# VideoFaceManager 综合模式

**反向学习 + 主动录入 + 纠正反馈 = 越用越准**

---

## 三种方式构建人物库

```
┌─────────────────────────────────────────────────────────────┐
│                      混合特征来源                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  📹 反向学习         📸 主动录入          ✏️ 纠正反馈        │
│  (权重1.0)          (权重1.2)           (权重1.5)           │
│      │                  │                   │               │
│      ▼                  ▼                   ▼               │
│  从分类视频          上传参考照片         用户确认正确        │
│  自动提取特征        多角度补充           或标记错误          │
│      │                  │                   │               │
│      └──────────────────┴───────────────────┘               │
│                        │                                    │
│                  融合人物档案                                │
│                        │                                    │
│                  智能识别视频                                │
│                        │                                    │
│              发现错误 → 纠正 → 增强学习                       │
└─────────────────────────────────────────────────────────────┘
```

---

## 快速开始

### 安装
```bash
# 1. 下载代码
git clone https://github.com/hcy19940819/GitHub.git
cd GitHub/VideoFaceManager

# 2. 安装依赖
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 3. 初始化
python cli_hybrid.py init
```

### 使用方法

#### 方法一：一键工作流（推荐）
```bash
python workflow_hybrid.py
```
按提示输入路径，全自动完成。

#### 方法二：分步执行

**1. 构建人物库**
```bash
# 方式A：反向学习（从已分类视频）
python cli_hybrid.py learn "/已分类视频"

# 方式B：主动录入（从照片）
python cli_hybrid.py add_photos "/人物照片"

# 方式C：两种方式都用
python cli_hybrid.py build --videos "/已分类视频" --photos "/人物照片"
```

**2. 识别视频**
```bash
python cli_hybrid.py identify "/未分类视频" -o "/输出" --auto-move
```

**3. 纠正反馈**
```bash
# 确认正确
python cli_hybrid.py correct "/视频路径" 张三 --positive

# 标记错误
python cli_hybrid.py correct "/视频路径" 李四 --negative
```

---

## 目录结构要求

### 已分类视频（反向学习）
```
已分类视频/
├── 张三/
│   ├── 聚会视频1.mp4
│   ├── 旅游视频.mp4
│   └── 生日记录.mp4
├── 李四/
│   ├── 工作记录.mp4
│   └── 会议视频.mp4
└── 王五/
    └── 采访视频.mp4
```
- 每人一个文件夹
- 文件夹名=人物名
- 每个文件夹至少3-5个视频

### 人物照片（主动录入）
```
人物照片/
├── 张三/
│   ├── 正面.jpg
│   ├── 侧面.jpg
│   └── 其他角度.png
├── 李四/
│   └── 照片.jpg
└── ...
```
- 每人一个文件夹
- 3-5张不同角度的照片
- 脸部清晰，不要太小

---

## 特征权重系统

不同来源的特征有不同的可信度权重：

| 来源 | 权重 | 说明 |
|------|------|------|
| 主动录入照片 | 1.2 | 用户精心挑选，角度好 |
| 反向学习视频 | 1.0 | 基准水平 |
| 纠正反馈确认 | 1.5 | 用户验证过，最可信 |

识别时会综合计算加权相似度，**确认过正确的特征权重更高**，识别更准确。

---

## 迭代优化

随着使用次数增加，系统会越来越准：

```
第1轮: 反向学习 → 识别 → 发现50%错误
         ↓
第2轮: 纠正反馈 → 重新学习 → 错误率降到20%
         ↓
第3轮: 继续纠正 → 权重调整 → 错误率降到5%
```

---

## 命令参考

### 学习命令
| 命令 | 说明 |
|------|------|
| `learn <目录>` | 从已分类视频学习 |
| `add_photos <目录>` | 从照片导入特征 |
| `build --videos <v> --photos <p>` | 综合建库 |

### 识别命令
| 命令 | 说明 |
|------|------|
| `identify <目录> -o <输出>` | 批量识别 |
| `identify_one <视频>` | 识别单个视频 |
| `--auto-move` | 自动分类移动 |
| `--min-confidence 0.7` | 设置置信度 |

### 纠正命令
| 命令 | 说明 |
|------|------|
| `correct <视频> <人名> --positive` | 确认正确 |
| `correct <视频> <人名> --negative` | 标记错误 |
| `merge <人1> <人2>` | 合并重复人物 |

### 管理命令
| 命令 | 说明 |
|------|------|
| `stats` | 查看统计 |
| `persons` | 查看人物库 |
| `export <人名> <目录>` | 导出人物数据 |
| `import_person <文件>` | 导入人物数据 |

---

## Web 管理面板

```bash
python manager.py
```
浏览器打开 `http://localhost:5000`

功能：
- 📊 概览统计
- 👥 人物库管理
- 🎥 视频库浏览
- ✏️ 纠正识别结果

---

## 文件结构

```
VideoFaceManager/
├── cli_hybrid.py              ← 综合模式CLI
├── workflow_hybrid.py         ← 一键工作流
├── manager.py                 ← Web面板
├── core/
│   ├── hybrid_library.py      ← 混合人物库
│   ├── hybrid_recognizer.py   ← 智能识别器
│   ├── video_learner.py       ← 反向学习
│   └── ...
├── data/
│   ├── faces/                 ← 人脸截图
│   ├── person_library/        ← 人物照片
│   └── video_persons.db       ← 数据库
└── web/                       ← Web界面
```

---

## 依赖项

- opencv-python
- insightface (ArcFace模型)
- onnxruntime
- numpy, Pillow
- Flask (Web面板)
- click (CLI)

---

## 许可证

MIT License