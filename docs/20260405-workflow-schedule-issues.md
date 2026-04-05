# 2026-04-05 GitHub Actions 排程設定問題記錄

## 📋 今日遇上的問題與解決方案

### 1️⃣ GitHub Actions Schedule 排程不執行

**問題描述**：
- 在 `.github/workflows/copilot-refactor-go.yml` 中添加了 `schedule: '*/30 * * * *'` 配置
- 預期每 30 分鐘自動執行，但沒有自動觸發
- 只有手動執行 (`workflow_dispatch`) 才能跑

**根本原因** ❌：
- 在 `schedule` 事件中使用了 `branches` 過濾
- **GitHub Actions 的 `schedule` 事件不支持 `branches` 過濾**
- 只有 `push` 和 `pull_request` 事件才支持 branch filtering

**錯誤配置**：
```yaml
on:
  schedule:
    - cron: '*/30 * * * *'
      branches:                    # ❌ 無效！schedule 不支持 branches
        - refactor/go-migration-phase2
```

**解決方案** ✅：
```yaml
on:
  workflow_dispatch:
  schedule:
    - cron: '*/30 * * * *'         # 直接使用，無需 branches 過濾
```

**說明**：
- 排程事件會在 **workflow 檔案所在的分支** 執行
- 你的 workflow 檔案在 `refactor/go-migration-phase2` 分支，所以排程會自動在該分支執行
- 每 30 分鐘執行一次（UTC 時間）

**Commit**：`05af10b`

---

### 2️⃣ Workflow Markdown 輸出 Permission Denied

**問題描述**：
```
##[error]/home/runner/work/_temp/.sh: line 4: cmd/scanner/cache_cmd.go: Permission denied
Line |
   2 |  … git diff --name-only | sed 's#^#- `#; s#$#`#'
```

**根本原因** ❌：
- Bash 指令中使用了未轉義的 backticks
- `echo "- Scope: `pkg/**`"` 被 bash 解釋為執行 `` `pkg/**` `` 命令
- 導致 bash 嘗試執行 `pkg/**` 作為指令，觸發權限錯誤

**錯誤配置**：
```bash
echo "- Scope: `pkg/**`, `cmd/scanner/**`, bridge wrappers"
# ^ Bash 會嘗試執行 `pkg/**` 和 `cmd/scanner/**` 作為命令
```

**解決方案** ✅：
```bash
echo "- Scope: \`pkg/**\`, \`cmd/scanner/**\`, bridge wrappers"
# 使用 \` 轉義 backtick，告訴 bash 這是文字而非命令替換
```

**Commit**：`9d18553`

---

### 3️⃣ Go 1.24 兼容性 - os.Root 新方法不存在

**問題描述**：
```
Error: pkg/safefile/safefile.go:52:14: root.ReadFile undefined (type *os.Root has no field or method ReadFile)
Error: pkg/safefile/safefile.go:67:14: root.WriteFile undefined
Error: pkg/safefile/safefile.go:118:14: root.MkdirAll undefined
```

**根本原因** ❌：
- `os.Root` 的新方法 `ReadFile()`, `WriteFile()`, `MkdirAll()` 是 **Go 1.26 才有**
- GitHub Actions CI 使用 Go 1.24.5，不支持這些方法

**失敗環境**：
- Go 1.24.5 (GitHub Actions runner)

**成功環境**：
- Go 1.26 (本機開發環境)

**解決方案** ✅：

改用 Go 1.24 兼容的 API 組合：

```go
// 舊（Go 1.26 only）
data, err := root.ReadFile(filepath)

// 新（Go 1.24 compatible）
f, err := root.Open(filepath)
if err != nil {
    return nil, err
}
defer f.Close()
data, err := io.ReadAll(f)
```

```go
// 舊（Go 1.26 only）
err := root.WriteFile(filepath, data, 0644)

// 新（Go 1.24 compatible）
f, err := root.OpenFile(filepath, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0644)
if err != nil {
    return err
}
defer f.Close()
_, err = f.Write(data)
```

```go
// 舊（Go 1.26 only）
err := root.MkdirAll(path, 0755)

// 新（Go 1.24 compatible）
parts := strings.Split(strings.TrimPrefix(path, "/"), "/")
currentRoot := root
for _, part := range parts {
    subRoot, err := currentRoot.OpenRoot(part)
    if err != nil {
        if os.IsNotExist(err) {
            err = currentRoot.Mkdir(part, 0755)
            if err != nil && !os.IsExist(err) {
                return err
            }
            subRoot, _ = currentRoot.OpenRoot(part)
        }
    }
    currentRoot = subRoot
}
```

**Commit**：`fa96974`
**新增測試**：`pkg/safefile/safefile_test.go`

---

### 4️⃣ GitHub Actions Node.js 版本棄用警告

**問題描述**：
```
##[warning]Node.js 20 actions are deprecated. The following actions are running on Node.js 20 and may not work as expected: 
actions/checkout@v4, actions/setup-go@v5, actions/setup-node@v4, actions/setup-python@v5. 
Actions will be forced to run with Node.js 24 by default starting June 2nd, 2026.
```

**根本原因** ⚠️：
- GitHub 已棄用 Node.js 20 支持
- 2026-06-02 起會強制升級至 Node.js 24

**解決方案** ✅：
```yaml
# 舊
- name: Set up Node.js
  uses: actions/setup-node@v4
  with:
    node-version: '20'

# 新
- name: Set up Node.js
  uses: actions/setup-node@v4
  with:
    node-version: '24'
```

**Commit**：`9d18553`

---

### 5️⃣ Workflow 架構改進 - 從 PR 模式改為直接 Commit

**之前的設計** ❌：
- 使用 `create-pull-request@v8` action 建立 PR
- 從 refactor 分支對 refactor 分支開 PR（邏輯混亂）
- 需要 `pull-requests: write` 權限

**改進後** ✅：
- 直接使用 `git commit` 和 `git push`
- Commit 到源分支 (`${{ github.ref_name }}`)
- 簡化流程，避免 PR 開銷

**新流程**：
```yaml
- name: Commit and push migration changes
  if: steps.scope.outputs.has_changes == 'true'
  shell: bash
  run: |
    git config user.name "github-actions[bot]"
    git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
    git add pkg cmd/scanner src/...
    git commit -m "refactor: advance python-to-go migration"
    git push origin "HEAD:${TARGET_BRANCH}"
```

**Commit**：`e1ac78f`
**權限更新**：只需 `contents: write` (移除 `pull-requests: write`)

---

## 📊 今日 Commit 摘要

| Hash | 時間 | 說明 | 類型 |
|------|------|------|------|
| `05af10b` | 07:20 | fix: remove branches filter from schedule | 🐛 |
| `9d18553` | 06:43 | fix: escape backticks + update Node.js 24 | 🐛 |
| `edcd3db` | 06:32 | fix: limit schedule trigger branch | 🐛 |
| `e8f4243` | 06:36 | fix: correct cron schedule to every 30 min | 🐛 |
| `c03ffc2` | 06:25 | chore: schedule workflow to run every 30 min | ⚙️ |
| `e1ac78f` | 04:20 | refactor: push changes to source branch | ♻️ |
| `fa96974` | 04:12 | fix: support safefile on go 1.24 | 🐛 |

---

## ✅ 最終狀態

- ✅ GitHub Actions 排程配置已修正
- ✅ 每 30 分鐘自動執行 (UTC 時間)
- ✅ Workflow Markdown 輸出 backtick 已轉義
- ✅ Go 1.24 兼容性通過測試
- ✅ Node.js 升級至 v24
- ✅ 直接 commit 模式已啟用
- ⏳ 等待下一個 30 分鐘排程點自動執行

---

## 🔍 關鍵學習點

1. **GitHub Actions `schedule` 限制**：
   - 不支持 `branches` 過濾
   - 排程在 workflow 檔案所在分支執行
   - 分支條件應該在 workflow 檔案路徑中解決

2. **Bash Backtick 轉義**：
   - Backtick `` ` `` 在 bash 中是命令替換語法
   - 在 markdown 中需要 escape 為 `` \` ``
   - GitHub Actions 日誌輸出需要特別注意

3. **跨版本兼容性**：
   - Go API 新增方法通常在小版本中出現
   - Go 1.24 vs 1.26 的 `os.Root` 方法完全不同
   - CI/CD 環境的 Go 版本可能比開發環境舊

4. **GitHub Actions 權限聲明**：
   - 改為直接 commit 不需要 PR 權限
   - 簡化權限模型提高安全性

---

## 📝 建議下一步

1. 監控下一個 30 分鐘排程點的執行
2. 驗證 workflow 是否正常自動觸發
3. 若還有問題，檢查 Actions 日誌了解具體原因
4. 考慮添加 Slack/Discord 通知機制用於 workflow 失敗告警
