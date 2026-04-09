# VideoDedup - 视频快速去重工具

参考 DoubleKiller，专门针对视频优化。解决传统文件去重工具对视频识别不准确的问题。

## 核心特性

| 特性 | 说明 |
|------|------|
| **多层指纹** | 文件大小 → 时长 → 快速pHash → 详细pHash序列 |
| **增量扫描** | 保存指纹数据库，只处理新文件 |
| **跨库对比** | 支持对比多个路径/机器的指纹库 |
| **相似识别** | 识别不同格式/编码/轻微剪辑的同内容视频 |
| **重命名标记** | 发现重复后自动添加后缀标识，方便手动处理 |
| **可视化报告** | 生成HTML报告，带缩略图、勾选删除、脚本导出 |

## 安装

```bash
pip install -r requirements.txt
```

## 快速开始

### 1. 扫描视频生成指纹

```bash
# 基础扫描
python videodedup.py scan /path/to/videos

# 扫描多个目录
python videodedup.py scan /videos /downloads /backup

# 完整重新扫描（非增量）
python videodedup.py scan /videos --full

# 更新已修改的文件
python videodedup.py scan /videos --update
```

### 2. 查找重复视频

```bash
# 查找所有重复
python videodedup.py find

# 只查找指定路径
python videodedup.py find --paths /videos /downloads

# 指定输出文件
python videodedup.py find -o result.md

# 跨目录对比模式（不同目录间才认为是重复）
python videodedup.py find --cross
```

**查找后会自动生成三个文件：**
- `duplicates.md` - 可读的Markdown报告
- `duplicates.json` - 供 rename 命令使用的数据
- `report.html` - 📊 **可视化HTML报告**（推荐在浏览器中打开查看）

**HTML可视化报告功能：**
- 🖼️ **缩略图预览** - 每个视频显示中间帧截图
- 📊 **对比表格** - 大小、时长、分辨率并排对比
- ✅ **勾选删除** - 勾选要删除的文件，一键生成删除脚本
- 🔍 **搜索筛选** - 按文件名搜索，按类型筛选
- 📥 **脚本导出** - 导出删除/重命名脚本，安全可控

### 3. 重命名重复文件（添加重复ID后缀）

这是最推荐的处理方式！不删除任何文件，只添加后缀标识，方便你手动决定。

```bash
# 预览重命名（默认，不会实际执行）
python videodedup.py rename --groups duplicates.json

# 实际执行重命名
python videodedup.py rename --groups duplicates.json --execute

# 自定义后缀格式
python videodedup.py rename --groups duplicates.json --suffix "_重复{id:03d}"

# 导出重命名脚本（审核后手动执行）
python videodedup.py rename --groups duplicates.json -o rename.sh
```

**重命名效果：**
```
# 假设第 1 组重复包含这 3 个视频：
/videos/movie_hd.mkv     →  movie_hd_dup001.mkv
/videos/movie.mp4        →  movie_dup001.mp4
/downloads/movie.avi     →  movie_dup001.avi

# 第 2 组重复：
/videos/show_s01e01.mkv  →  show_s01e01_dup002.mkv
/videos/show_s01e01(1).mkv → show_s01e01(1)_dup002.mkv
```

**处理后你可以：**
- 按文件名排序，所有重复文件会聚在一起
- 根据文件大小、分辨率等决定保留哪个
- 手动删除带 `_dupXXX` 后缀的文件

### 4. 与外部指纹库对比

```bash
# 对比另一个数据库
python videodedup.py compare /path/to/other.db

# 对比并指定输出
python videodedup.py compare other.db -o compare_result.md
```

### 5. 查看统计

```bash
python videodedup.py stats
```

## 完整工作流程示例

```bash
# 步骤1: 扫描视频库
python videodedup.py scan ~/Videos

# 步骤2: 查找重复
python videodedup.py find

# 步骤3: 打开 report.html 可视化报告（推荐！）
# 在浏览器中查看缩略图，勾选要删除的文件

# 步骤4: 导出删除脚本（从HTML报告或命令行）
python videodedup.py rename --groups duplicates.json -o delete.sh

# 步骤5: 审核脚本后执行
bash delete.sh

# 或者使用重命名方式
# 步骤4b: 预览重命名效果
python videodedup.py rename --groups duplicates.json

# 步骤5b: 执行重命名（添加 _dupXXX 后缀）
python videodedup.py rename --groups duplicates.json --execute

# 步骤6b: 手动处理带 _dupXXX 后缀的文件
```

## 技术原理

### 为什么传统工具识别不出视频重复？

传统文件去重工具（如 DoubleKiller）使用 MD5/CRC32 等哈希算法，只能识别**完全相同的文件**。但视频有以下情况：

1. **格式转换**：同一视频转码为 MP4/AVI/MKV
2. **压缩差异**：不同码率、分辨率的版本
3. **元数据修改**：修改时间戳、添加标签
4. **轻微剪辑**：去片头片尾、加水印

这些情况下文件哈希完全不同，但内容实质相同。

### VideoDedup 的解决方案

```
┌─────────────────────────────────────────────────────────┐
│                    多层指纹架构                          │
├─────────────────────────────────────────────────────────┤
│  L1: 文件元数据 (大小、时长、分辨率) - 快速预筛选         │
│  L2: 快速pHash (均匀采样10帧) - 粗筛相似视频             │
│  L3: 详细pHash (关键帧序列) - 精确比对内容               │
│  L4: 文件MD5 - 确认完全重复                              │
└─────────────────────────────────────────────────────────┘
```

#### 感知哈希 (pHash)

不同于 MD5，pHash 是基于内容的"感知指纹"：

- 对视频格式、编码变化**不敏感**
- 对轻微裁剪、压缩**有容忍度**
- 相似视频产生**相似哈希**

通过**汉明距离**比较两个 pHash 的相似度：
- 距离 ≤ 5：极可能是同一视频
- 距离 5~10：可能是相似内容
- 距离 > 10：内容不同

#### 关键帧提取

视频连续帧高度冗余，VideoDedup 使用帧间差分算法提取关键帧：

1. 根据视频时长动态决定关键帧数量（5~20帧）
2. 对每个关键帧计算 pHash
3. 形成关键帧哈希序列
4. 通过序列比对判断视频相似度

### 增量对比实现

```
┌────────────────────────────────────────┐
│           指纹数据库 (SQLite)           │
├────────────────────────────────────────┤
│  fingerprints 表                        │
│  ├── path: 文件路径                      │
│  ├── size: 文件大小                      │
│  ├── mtime: 修改时间                     │
│  ├── duration: 视频时长                  │
│  ├── quick_hash: 快速pHash              │
│  ├── detail_hashes: 详细pHash序列(JSON)  │
│  └── file_hash: 文件MD5                 │
├────────────────────────────────────────┤
│  scan_sessions 表 (扫描历史记录)         │
└────────────────────────────────────────┘
```

增量扫描逻辑：
1. 检查数据库是否已有该路径的指纹
2. 如有，对比文件修改时间
3. 文件未修改 → 跳过
4. 文件已修改/新增 → 重新生成指纹
5. 批量写入新指纹

### 跨库对比

支持将指纹库复制到其他机器，对比不同位置的重复：

```
机器A: videodedup.db (路径: /home/user/videos)
机器B: videodedup.db (路径: /mnt/backup)

在A上执行: python videodedup.py compare /mnt/backup/videodedup.db
→ 找出A和B之间的重复视频
```

## 命令详解

### scan 命令

```
python videodedup.py scan [选项] <路径1> [路径2] ...

选项:
  --full          完整扫描，忽略已有指纹
  --update        检查文件修改时间，更新变化的文件
  --db PATH       指定数据库路径
  --workers N     并行线程数（默认4）
```

### find 命令

```
python videodedup.py find [选项]

选项:
  --paths PATH    只查找指定路径下的重复
  --output FILE   结果输出文件前缀（默认 duplicates）
  --cross         跨目录对比（不同目录间才认为是重复）
```

**输出文件：**
- `{output}.md` - Markdown格式报告
- `{output}.json` - JSON数据（供rename命令使用）
- `report.html` - 📊 HTML可视化报告（包含缩略图）

**HTML报告依赖：**
```bash
pip install opencv-python pillow numpy
```

### rename 命令

```
python videodedup.py rename --groups <JSON文件> [选项]

必选:
  --groups FILE   重复组JSON文件（由find命令生成）

选项:
  --execute       实际执行重命名（默认只预览）
  --suffix FMT    后缀格式，{id}会被替换为组ID（默认: _dup{id:03d}）
  -o, --output    导出重命名脚本路径
```

**后缀格式示例：**
- `_dup{id:03d}` → `_dup001`, `_dup002` ...
- `_重复{id}` → `_重复1`, `_重复2` ...
- `_{id:04d}_copy` → `_0001_copy`, `_0002_copy` ...

### compare 命令

```
python videodedup.py compare [选项] <外部数据库>

选项:
  --paths PATH    当前库中只对比指定路径
  --output FILE   结果输出文件
```

## 输出格式

### Markdown 报告 (duplicates.md)

```markdown
# VideoDedup 去重报告
生成时间: 2024-01-15T10:30:00
发现重复组: 5

## 重复组 #1 [identical]
原因: identical_quick_hash
视频数量: 3

| 建议 | 文件路径 | 大小 | 时长 | 分辨率 |
|------|----------|------|------|--------|
| 保留 | `/videos/movie_hd.mkv` | 2048.0MB | 7200.0s | 1920x1080 |
| 可删除 | `/videos/movie.mp4` | 1024.0MB | 7200.0s | 1920x1080 |
| 可删除 | `/downloads/movie.avi` | 1536.0MB | 7200.0s | 1920x1080 |
```

### JSON 数据 (duplicates.json)

供 rename 命令使用，包含完整的重复组信息：

```json
[
  {
    "group_id": 1,
    "similarity_type": "identical",
    "reason": "identical_quick_hash",
    "videos": [
      {"path": "/videos/movie_hd.mkv", "size": 2147483648, ...},
      {"path": "/videos/movie.mp4", "size": 1073741824, ...}
    ]
  }
]
```

## 性能优化

### 扫描速度

| 视频数量 | 总大小 | 首次扫描 | 增量扫描 |
|----------|--------|----------|----------|
| 1000 | 100GB | ~15分钟 | ~30秒 |
| 5000 | 500GB | ~1小时 | ~2分钟 |

### 加速技巧

1. **使用 SSD**：指纹数据库和视频文件都在 SSD 上
2. **增加线程**：`--workers 8`（根据 CPU 核心数调整）
3. **分库管理**：不同目录使用不同数据库，最后合并对比

## 注意事项

1. **pHash 不是万能的**：
   - 大幅剪辑（去掉50%内容）可能无法识别
   - 旋转、翻转后的视频识别率降低
   - 极短视频（<5秒）可能误判

2. **建议操作**：
   - 首次使用前在测试目录验证
   - 使用 `--execute` 前先用预览模式检查
   - 重要视频删除前手动确认

3. **数据库维护**：
   - 定期备份 `.db` 文件
   - 文件移动/重命名后需要重新扫描

## 与其他工具对比

| 功能 | DoubleKiller | VideoDedup |
|------|--------------|------------|
| 完全重复检测 | ✅ | ✅ |
| 格式不同同内容 | ❌ | ✅ |
| 压缩版本识别 | ❌ | ✅ |
| 增量对比 | ❌ | ✅ |
| 跨库对比 | ❌ | ✅ |
| 相似视频检测 | ❌ | ✅ |
| 保存对比路径 | ❌ | ✅ |
| 重命名标记重复 | ❌ | ✅ |
| 可视化HTML报告 | ❌ | ✅ |

## 路线图

- [x] 重命名标记重复文件
- [x] 可视化HTML报告（带缩略图）
- [ ] GUI 界面
- [ ] 更多哈希算法（aHash, dHash, wHash）
- [ ] 深度学习特征提取
- [ ] 支持水印检测
