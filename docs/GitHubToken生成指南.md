# GitHub Personal Access Token 生成指南

## 步骤（图文）

### 1. 打开设置页面
访问：https://github.com/settings/tokens

或手动路径：
```
点击右上角头像 → Settings → 左侧 Developer settings → Personal access tokens → Tokens (classic)
```

### 2. 生成新 Token
点击绿色按钮 **"Generate new token"** → 选择 **"Tokens (classic)"**

### 3. 填写信息

| 字段 | 填写内容 |
|------|----------|
| **Note** | `Delete Repos` 或任意名字 |
| **Expiration** | 选 `30 days` 或 `No expiration` |

### 4. 勾选权限（Scopes）

**必须勾选：**
- [x] **repo** - 仓库相关
  - [x] repo:status
  - [x] repo_deployment
  - [x] public_repo
  - [x] repo:invite
  - [x] security_events
- [x] **delete_repo** - **删除仓库（重要）**

**可选（如果需要）：**
- [ ] workflow
- [ ] read:org

### 5. 生成
点击底部 **"Generate token"** 绿色按钮

### 6. 复制 Token
⚠️ **重要**：Token 只显示一次！

```
ghp_xxxxxxxxxxxxxxxxxxxx
```

**立即复制保存**，刷新页面后就看不到了。

---

## 给我之后

把 Token 发给我，格式：
```
ghp_xxxxxxxxxxxxxxxxxxxx
```

我会：
1. 列出你所有仓库
2. 你确认要删哪些
3. 执行删除

---

## Token 安全提醒

- Token 等于你的密码，不要泄露给别人
- 用完可以删除或过期
- 如果泄露，立即到 GitHub 删除该 Token
