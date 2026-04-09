# VideoDedup Smart 智能版使用说明

## 这个版本有什么特别？

**6个鉴定师同时工作 + 你能教它认视频**

### 6种算法
1. **pHash** - 老鉴定师，抗压缩格式转换
2. **aHash** - 快鉴定师，速度最快
3. **dHash** - 边缘专家，能看出剪辑痕迹
4. **wHash** - 细节控，用放大镜看
5. **ColorHist** - 颜色专家，识别滤镜调色
6. **ORB** - 结构专家，识别旋转裁剪

### 自主学习
- 系统不确定时问你
- 你教它之后，它会记住
- 越用越准

---

## 使用方法

### 1. 第一次用 - 扫描视频

```bash
python videodedup_smart.py scan /你的视频文件夹
```

### 2. 查找重复

```bash
python videodedup_smart.py find
```

会显示找到了哪些重复视频。

### 3. 主动学习模式（推荐）

```bash
python videodedup_smart.py find --active-learning
```

如果系统有不确定的视频对，会问你：
```
🤔 系统有 3 对视频不确定，请帮忙判断：

1. 电影_1080p.mkv
   电影_720p.mp4
   系统觉得相似度: 65%
   
这两个是相同的吗？(y/n): 
```

你回答几次后，系统就越来越准。

### 4. 教系统认视频

如果你发现系统判断错了，可以教它：

```bash
# 告诉系统这两个视频是相同的
python videodedup_smart.py teach 视频A.mp4 视频B.mp4 --same

# 告诉系统这两个视频是不同的
python videodedup_smart.py teach 视频A.mp4 视频B.mp4 --different
```

### 5. 查看系统状态

```bash
python videodedup_smart.py status
```

显示：
- 数据库里有多少视频
- 已经学了多少个例子
- 6种算法现在的权重（哪个算法最被信任）

---

## 学习效果展示

教了5个例子后，系统会显示：

```
🧠 系统学习了 5 个例子，更新权重：
   phash:  ████████░░░░░░░░░░░░ 35%
   dhash:  ██████░░░░░░░░░░░░░░ 25%
   ahash:  ████░░░░░░░░░░░░░░░░ 20%
   whash:  ███░░░░░░░░░░░░░░░░░ 15%
   color:  █░░░░░░░░░░░░░░░░░░░  5%
```

这意味着：
- 在你的视频库中，**pHash最管用**
- 系统以后会更信任pHash的判断

---

## 数据存在哪里

| 文件 | 内容 |
|------|------|
| `videodedup_smart.db` | 视频指纹数据库 |
| `learner.db` | 你的教学记录和权重 |

这两个文件可以备份，换电脑时拷贝过去，系统记得你教过的东西。

---

## 完整工作流程

```bash
# 1. 扫描
python videodedup_smart.py scan ~/Videos

# 2. 查找（带主动学习）
python videodedup_smart.py find --active-learning

# 3. 回答系统的问题（教它）
# 4. 重复步骤2-3几次，系统越来越准

# 5. 查看学习成果
python videodedup_smart.py status
```

---

## 和普通版的区别

| 功能 | 普通版 | 智能版 |
|------|--------|--------|
| 算法数量 | 1种 | 6种 |
| 能学习吗 | 不能 | 能 |
| 主动问问题 | 不能 | 能 |
| 自适应权重 | 固定 | 动态调整 |

**建议**：先用普通版，熟悉了再换智能版。
