# UC云盘自动转存工具 V2

## 功能特性

- ✅ 自动启动UC浏览器
- ✅ 支持带/不带提取码链接
- ✅ 多行格式解析（链接+提取码）
- ✅ 3次重试机制
- ✅ 自动跳过无效链接
- ✅ 保存无效链接到文件
- ✅ 自动读取STboy最新链接

## 文件结构

```
D:\AI\AI_Tool\自动下载工作\
├── uc_auto_v2.py          # 主程序
├── window_manager.py      # 窗口管理模块
├── stable_locator.py      # 坐标定位模块
├── auto_coords.json       # 按钮坐标配置
├── uc_links.txt           # 默认链接列表
├── 开始转存.bat           # 主入口（支持拖放）
├── 获取坐标.bat           # 坐标校准工具
├── STboy自动转存.bat      # STboy专用入口
├── retry_links.json       # 待重试链接（自动生成）
├── invalid_links.txt      # 无效链接（自动生成）
└── transfer_log.json      # 转存日志（自动生成）
```

## 使用方式

### 1. 首次使用 - 获取坐标

双击 `获取坐标.bat`
```
→ 复制UC分享链接，等待弹出窗口
→ 鼠标移到【保存到网盘】，按 Enter
→ 点击保存到网盘，等待成功弹出
→ 鼠标移到【知道了】，按 Enter
→ 坐标自动保存
```

### 2. 日常转存

**方式A：默认链接文件**
```
双击 开始转存.bat
→ 使用当前目录 uc_links.txt
```

**方式B：拖放文件**
```
将任意txt文件拖到 开始转存.bat 上
→ 使用该文件作为链接列表
```

**方式C：STboy自动模式**
```
双击 STboy自动转存.bat
→ 自动读取 D:\AI\AI_Tool\STboy_Auto\extracted_links\最新文件夹\uc_pan_links.txt
```

## 链接文件格式

### uc_links.txt 格式

```
# 无需提取码
https://drive.uc.cn/s/xxxxx

# 带提取码（多行格式）
https://drive.uc.cn/s/yyyyy
提取码：abcd

# 已有提取码参数
https://drive.uc.cn/s/zzzzz?pwd=1234
```

## 工作流程

```
开始
  ↓
自动启动UC浏览器（如未运行）
  ↓
等待5秒加载
  ↓
读取链接文件
  ↓
循环处理每个链接:
  ├─ 复制链接 → 粘贴
  ├─ 等待窗口弹出（5秒超时）
  │   └─ 超时 → 标记跳过，重试次数+1
  ├─ 点击【保存到网盘】
  ├─ 等待成功弹窗（5秒超时）
  │   └─ 超时 → 标记跳过，重试次数+1
  ├─ 点击【知道了】
  └─ 标记成功
  ↓
保存结果:
  ├─ 成功链接：完成
  ├─ 待重试：保存到 retry_links.json
  └─ 3次无效：保存到 invalid_links.txt
```

## 重试机制

| 次数 | 处理 |
|------|------|
| 第1次失败 | 保存到 retry_links.json，计数=1 |
| 第2次失败 | 更新计数=2 |
| 第3次失败 | 移动到 invalid_links.txt |

## 命令行参数

```bash
# 默认使用 uc_links.txt
python uc_auto_v2.py

# 指定链接文件
python uc_auto_v2.py D:\下载\links.txt

# STboy自动模式
python uc_auto_v2.py --auto

# 指定目录
python uc_auto_v2.py --dir D:\下载
```

## 注意事项

1. **首次使用必须先运行 `获取坐标.bat` 校准按钮坐标**
2. 确保UC浏览器可以正常打开网盘页面
3. 转存过程中请勿移动鼠标
4. 无效链接会自动跳过并记录，无需手动处理
