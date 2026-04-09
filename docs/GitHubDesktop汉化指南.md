# GitHub Desktop 汉化指南

## 一键汉化（推荐）

复制以下代码，保存为 `汉化GitHubDesktop.ps1`，右键选择"使用 PowerShell 运行"：

```powershell
# GitHub Desktop 汉化脚本
Write-Host "正在下载 GitHub Desktop 汉化包..." -ForegroundColor Green

# 下载地址（由社区维护的汉化包）
$downloadUrl = "https://github.com/robotze/-GitHubDesktop-.git"
$tempPath = "$env:TEMP\GitHubDesktopChinese"

# 克隆汉化包仓库
if (Test-Path $tempPath) {
    Remove-Item $tempPath -Recurse -Force
}

git clone --depth 1 $downloadUrl $tempPath

# 查找 GitHub Desktop 安装目录
$githubDesktopPath = "${env:LOCALAPPDATA}\GitHubDesktop"
$appPath = Get-ChildItem -Path "$githubDesktopPath\app-*" -Directory | Sort-Object Name -Descending | Select-Object -First 1

if (-not $appPath) {
    Write-Host "未找到 GitHub Desktop 安装目录，请确认已安装 GitHub Desktop" -ForegroundColor Red
    exit 1
}

Write-Host "找到安装目录: $($appPath.FullName)" -ForegroundColor Green

# 复制汉化文件
$localesPath = "$($appPath.FullName)\locales"
$zhCnPath = "$tempPath\GitHubDesktop-main\main\zh-Hans"

if (Test-Path $zhCnPath) {
    Copy-Item -Path "$zhCnPath\*" -Destination $localesPath -Force -Recurse
    Write-Host "汉化完成！重启 GitHub Desktop 即可生效。" -ForegroundColor Green
} else {
    Write-Host "汉化文件下载失败，请检查网络连接。" -ForegroundColor Red
}

# 清理临时文件
Remove-Item $tempPath -Recurse -Force
pause
```

## 手动汉化步骤

如果脚本运行失败，可以手动操作：

### 1. 下载汉化包
访问：https://github.com/robotze/-GitHubDesktop-.git
点击 "Code" → "Download ZIP"

### 2. 找到 GitHub Desktop 安装目录
默认路径：
```
C:\Users\你的用户名\AppData\Local\GitHubDesktop\app-版本号
```

### 3. 复制汉化文件
将下载的汉化包中的 `zh-Hans` 文件夹复制到：
```
C:\Users\你的用户名\AppData\Local\GitHubDesktop\app-版本号\locales\
```

### 4. 重启 GitHub Desktop
完全退出后重新打开，即可显示中文。

---

## 你截图的问题

"This directory does not appear to be a Git repository"

**原因**：你选择的文件夹 `D:\AI\GitHub\自动下载工作` 不是 Git 仓库

**解决方法**：
1. 点击蓝色的 "create a repository" 链接，在这个文件夹新建仓库
2. 或者选择已经有的 Git 仓库文件夹

---

## 注意事项

1. 每次 GitHub Desktop 更新后，需要重新汉化
2. 汉化包由社区维护，可能存在翻译不全的情况
3. 官方原版其实也很好用，建议习惯英文界面
