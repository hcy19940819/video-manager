# VideoFaceManager 快速安装指南

**10分钟搞定，周末按这个做就行**

---

## 需要准备的

| 项目 | 说明 |
|------|------|
| Python 3.8+ | https://www.python.org/downloads/ |
| Git | https://git-scm.com/download/win |
| 已分类视频 | 每人一个文件夹，里面是该人物的视频 |
| 未分类视频 | 等待识别的视频 |

---

## 安装步骤

### 1. 安装软件（5分钟）

**安装 Python**
- 下载安装包
- **⚠️ 必须勾选 "Add Python to PATH"**
- 点击 Install Now

**安装 Git**
- 下载安装包
- 一直点 Next 默认安装

### 2. 下载代码（2分钟）

打开 CMD（开始菜单搜"cmd"）：

```cmd
D:
cd \
git clone https://github.com/hcy19940819/GitHub.git
cd GitHub/VideoFaceManager
```

### 3. 安装依赖（5-10分钟）

在 CMD 里继续执行：

```cmd
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

等它下载完成...

### 4. 初始化（1分钟）

```cmd
python cli.py init
```

看到 `✓ 数据库已初始化` 就成功了。

---

## 使用方法

### 第一步：准备已分类视频

假设你的视频已经分好类了：

```
D:/已分类视频/
├── 张三/           ← 文件夹名就是人物名
│   ├── 视频1.mp4
│   └── 视频2.mp4
├── 李四/
│   └── 视频3.mp4
└── 王五/
    └── 视频4.mp4
```

### 第二步：让系统学习

```cmd
python cli.py learn "D:/已分类视频"
```

系统会自动：
1. 扫描每个人物文件夹
2. 从视频里提取人脸
3. 保存人物特征
4. 生成人脸截图（在 `data/faces/`）

### 第三步：识别新视频

```cmd
python cli.py identify "D:/未分类视频" -o "D:/已识别" --auto-move
```

参数说明：
- `"D:/未分类视频"` - 待识别的视频在哪
- `-o "D:/已识别"` - 识别结果存哪
- `--auto-move` - 自动按人物分类

### 第四步：看结果

打开 `D:/已识别/` 文件夹：

```
D:/已识别/
├── 张三/              ← 包含张三的视频
│   ├── video1.mp4
│   └── video2.mp4
├── 李四/              ← 包含李四的视频
├── 王五/              ← 包含王五的视频
├── 未识别/            ← 没认出来的
├── 识别报告.json      ← 详细数据
└── 人物标签.txt       ← 人读的标签
```

---

## 懒人一键版

如果嫌上面步骤麻烦，直接用：

```cmd
python workflow.py
```

然后按提示输入路径，全自动完成。

---

## 常见问题

**Q: pip install 很慢？**  
用清华镜像（已经在上面的命令里了）

**Q: 提示缺 DLL？**  
安装 Visual C++ Redistributable：  
https://aka.ms/vs/17/release/vc_redist.x64.exe

**Q: 识别很慢？**  
正常。CPU跑人脸识别，一个5分钟视频约30秒-1分钟。

**Q: 识别不准？**  
多给点学习视频，每人至少5个，20个以上最好。

**Q: 可以用显卡加速吗？**  
你的 AMD RX 6750XT 不支持 CUDA，只能用CPU。

---

## 完整文档

详细说明看 `README.md`：  
https://github.com/hcy19940819/GitHub/blob/main/VideoFaceManager/README.md

有问题随时问我！