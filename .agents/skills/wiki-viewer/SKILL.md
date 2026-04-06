---
name: wiki-viewer
description: Wiki 瀏覽器啟動 Skill - 當使用者說「更新wiki」「查看wiki」「開啟wiki」「wiki viewer」時，自動在背景啟動 serve.py 並開啟瀏覽器
argument-hint: "[open|restart|stop]"
---

# Wiki Viewer Skill

## 觸發條件

當使用者輸入以下任一關鍵字時，**立即執行本 Skill**：

- `更新wiki` / `update wiki`
- `查看wiki` / `開啟wiki` / `瀏覽wiki`
- `wiki viewer` / `wiki server`
- 寫完 wiki 內容後主動詢問是否開啟

---

## 執行步驟

### Step 1 — 確認 wiki 內容已更新

若此次 session 有新增/修改 `wiki/**/*.md`，先確認 git commit 已完成（或告知使用者尚未 commit）。

### Step 2 — 啟動 serve.py（背景執行）

```powershell
# 先檢查 port 8765 是否已佔用（避免重複啟動）
$existing = Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "✅ Wiki server 已在執行中 → http://127.0.0.1:8765/viewer.html"
} else {
    Start-Process python -ArgumentList "wiki/serve.py" -WindowStyle Hidden
    Start-Sleep -Seconds 1
    Write-Host "🚀 Wiki server 已啟動 → http://127.0.0.1:8765/viewer.html"
}
```

**PowerShell 版（Copilot CLI 使用）**：
```powershell
$port = 8765
$inUse = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
if (-not $inUse) {
    Start-Process -FilePath python -ArgumentList "wiki\serve.py" -WindowStyle Hidden
    Start-Sleep -Seconds 1
}
```

**也可以直接用 powershell 工具**：
```
powershell mode=async detach=true
command: python wiki/serve.py
```

### Step 3 — 確認啟動成功

```powershell
# 等待 1 秒後驗證 port 已開啟
Start-Sleep -Seconds 1
$check = Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue
if ($check) {
    "✅ http://127.0.0.1:8765/viewer.html"
} else {
    "❌ 啟動失敗，請手動執行 python wiki/serve.py"
}
```

### Step 4 — 回報給使用者

```
🚀 Wiki 瀏覽器已啟動！
📖 http://127.0.0.1:8765/viewer.html

側欄已自動包含所有 .md 檔（動態 manifest），無需手動更新。
停止：Ctrl+C 或關閉終端機視窗。
```

---

## 重要細節

### 動態 manifest（2026-04-06 後）

`serve.py` 現在提供 `/api/manifest` 端點，**自動掃描** `wiki/**/*.md`：
- 新增 md 檔 → 重新整理瀏覽器即可看到（無需改 HTML）
- 側欄標題從每個 md 的第一個 `# H1` 讀取
- Icon 由 `serve.py` 的 `FILE_ICONS` dict 管理；新檔案預設 📄（patterns）或 ❌（pitfalls）

### Port 衝突

若 8765 被佔用（前次未關閉）：
```powershell
# 找出佔用的 PID 並終止
$pid = (Get-NetTCPConnection -LocalPort 8765).OwningProcess
Stop-Process -Id $pid
```

### 若新增 pitfall/pattern 需要自訂 icon

在 `wiki/serve.py` 的 `FILE_ICONS` dict 加入：
```python
FILE_ICONS = {
    ...
    "patterns/new-page": "🆕",   # ← 新增
    "pitfalls/new-pitfall": "⚠️", # ← 新增
}
```

---

## 停止 Wiki Server

```powershell
$pid = (Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue).OwningProcess
if ($pid) { Stop-Process -Id $pid; "✅ Wiki server 已停止" }
else { "ℹ️ Wiki server 未在執行" }
```

---

## 相關檔案

| 檔案 | 說明 |
|------|------|
| `wiki/serve.py` | HTTP server + `/api/manifest` 端點 |
| `wiki/viewer.html` | 前端瀏覽器（動態載入 manifest） |
| `wiki/index.md` | Wiki 首頁 |
| `wiki/log.md` | append-only 操作日誌 |
