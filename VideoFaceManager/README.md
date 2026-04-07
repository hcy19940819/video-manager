# VideoFaceManager 视频人物花名册系统

## 功能手册 V1.0

### 系统架构
```
人物库 → 识别引擎 → 花名册数据库 → Web管理面板
```

### 核心功能

#### 1. 人物库管理
- 创建人物：人名 + 3-5张参考照片
- 补充照片：给现有人物添加更多照片
- 删除人物：从人物库移除

#### 2. 视频识别引擎
- 扫描视频文件夹
- 提取人脸特征
- 匹配人物库
- 保存到花名册

#### 3. Web管理面板
- 概览页：统计信息
- 视频库：视频列表+缩略图
- 人物页：人物相册+视频列表
- 编辑纠正：修改人物标签

### 安装依赖
```bash
pip install -r requirements.txt
```

### 使用方法

#### 第一步：准备人物库
```
data/person_library/
├── 张三/
│   ├── 正面照1.jpg
│   ├── 侧面照2.jpg
│   └── 其他照片.jpg
├── 李四/
└── ...
```

#### 第二步：扫描视频
```bash
python cli.py scan /path/to/videos
```

#### 第三步：启动管理面板
```bash
python manager.py
```
浏览器自动打开 http://localhost:5000

### 数据库结构

**videos表**：视频信息
- md5: 视频唯一标识
- path: 文件路径
- persons: 识别出的人物（逗号分隔）
- thumbnail: 缩略图路径

**persons表**：人物信息
- name: 人物名称
- face_features: 人脸特征数据

**appearances表**：人物出现记录
- video_id: 视频ID
- person_id: 人物ID
- confidence: 置信度
