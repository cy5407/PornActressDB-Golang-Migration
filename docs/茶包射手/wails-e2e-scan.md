# Wails GUI E2E 完整踩坑記錄

> 歸檔日期：2026-04-07  
> 來源：Wails GUI 建置 + 實測（W1~W6 Nova agent 完成後的驗收測試）  
> 環境：Windows 11、actress-classifier.exe、掃描目錄 `C:\Users\cy5407\Downloads\AV`

---

## 踩到的坑（共 8 個）

### 坑 1：Wails 建置失敗 — npm 版本衝突

**症狀**

`wails build` 失敗，npm install 階段報錯：

```
npm error  ERESOLVE unable to resolve dependency tree
@tailwindcss/vite@4.2.2: requires vite@^5.x but package.json uses vite@^3
```

**根本原因**

Nova agent 在初始化時用了 `@tailwindcss/vite@4.2.2`（需要 vite@^5），但 `package.json` 鎖定了 `vite@^3`，依賴樹衝突。

**修法（2026-04-07 已修）**

修改 `wails.json` 的 `frontend:install` 加上 `--legacy-peer-deps`：

```json
"frontend:install": "npm install --legacy-peer-deps"
```

**教訓**

Wails 專案用 `wails.json` 控制 npm 安裝命令，遇到 peer dependency 衝突時要在此加參數，不能只改 `package.json`。

---

### 坑 2：Wails 建置失敗 — TypeScript 命名空間錯誤

**症狀**

`wails build` 在 `tsc && vite build` 階段失敗：

```
Property 'Preferences' does not exist on type 'typeof backend'
```

**根本原因**

`PreferencesDialog.tsx` 引用 `backend.Preferences`，但 `Preferences` struct 定義在 Go 的 `services` package，Wails 自動產生的 binding 對應 `services.Preferences` 命名空間。

**修法（2026-04-07 已修）**

```tsx
// ❌ 錯誤
import { backend } from '../../wailsjs/go/models'
// ...
const prefs: backend.Preferences = ...

// ✅ 正確
import { services } from '../../wailsjs/go/models'
// ...
const prefs: services.Preferences = ...
```

**教訓**

Wails binding 的 TypeScript 命名空間 = Go struct 所在的 **package 名稱**，不是 `backend`（那是 `app.go` 的 package）。每次新增跨 package 的 struct 都要確認 TS 端命名空間。

---

### 坑 3：📂 目錄瀏覽按鈕完全無反應

**症狀**

點擊「📂 瀏覽」按鈕後沒有任何反應，沒有錯誤訊息，目錄選擇對話框不出現。

**根本原因**

Nova agent 的 `DirectoryPicker.tsx` 使用 `window.runtime?.OpenDirectoryDialog()`，但 Wails v2 的 JS runtime 並未暴露此方法；正確做法是透過 Go binding 呼叫。

```ts
// ❌ Nova 的做法（不存在）
const dir = await window.runtime?.OpenDirectoryDialog({})

// ✅ 正確做法
import { SelectDirectory } from '../../wailsjs/go/backend/App'
const dir = await SelectDirectory("選擇影片目錄")
```

**修法（2026-04-07 已修）**

在 `app.go` 新增 binding：

```go
func (a *App) SelectDirectory(title string) string {
    dir, _ := wailsRuntime.OpenDirectoryDialog(a.ctx, wailsRuntime.OpenDialogOptions{
        Title: title,
    })
    return dir
}
```

**教訓**

Wails v2 的前端無法直接呼叫 runtime dialog API，**所有 native dialog 都必須透過 Go binding 包一層**。

---

### 坑 4：掃描過程彈出大量 CMD 視窗

**症狀**

每次搜尋一個番號，就會在螢幕背景閃出一個黑色 CMD 視窗（`python run_search.py`），批次搜尋時會閃出幾十個視窗。

**根本原因**

Go `exec.Command()` 在 Windows 上預設會建立可見的 Console 視窗。

**修法（2026-04-07 已修）**

建立 `wails-app/backend/proc_windows.go`（Build tag 限定 Windows）：

```go
//go:build windows

package backend

import (
    "os/exec"
    "syscall"
)

func hideWindow(cmd *exec.Cmd) {
    cmd.SysProcAttr = &syscall.SysProcAttr{
        HideWindow:    true,
        CreationFlags: 0x08000000, // CREATE_NO_WINDOW
    }
}
```

搭配 `proc_other.go`（`//go:build !windows`）提供空實作，避免非 Windows 平台編譯錯誤。

**教訓**

Windows subprocess 靜默執行需要 `CREATE_NO_WINDOW`。Build tag 檔案必須放在 `package` 宣告之前（第一行）。

---

### 坑 5：搜尋 log 中文字元顯示亂碼

**症狀**

```
搜尋中 (10/65)：EBON-004
? EBON-004: ??????????????????????????????????????????
```

日文片名、女優名全部變成 `?`。

**根本原因**

Python subprocess 的 stdout 預設使用系統編碼（Windows 上可能是 cp950 / cp932），輸出時無法正確處理 UTF-8 日文字元。

**修法（2026-04-07 已修）**

在 `PythonSearch()` 呼叫 Python 時加入：

```go
cmd := exec.Command("python", "-X", "utf8", "src/scrapers/run_search.py", ...)
cmd.Env = append(os.Environ(),
    "PYTHONIOENCODING=utf-8",
    "PYTHONUTF8=1",
)
```

**教訓**

Windows 上呼叫 Python subprocess 必須同時設 `-X utf8` flag 和 `PYTHONIOENCODING=utf-8` env，兩者缺一可能在不同 Python 版本下仍然亂碼。

---

### 坑 6：掃描未遞迴到最深層子目錄

**症狀**

勾選「含子目錄」後，只掃描到第一層子資料夾，更深的資料夾被跳過。

**根本原因**

Nova agent 原始碼用 `filepath.Walk`，加上邏輯錯誤導致非第一層目錄被 `SkipDir`。

**修法（2026-04-07 已修）**

改為 `filepath.WalkDir`（Go 1.16+，效能更好），並正確處理 recursive 邏輯：

```go
_ = filepath.WalkDir(dir, func(path string, d os.DirEntry, err error) error {
    if d.IsDir() {
        if !recursive && path != dir {
            return filepath.SkipDir   // 非遞迴模式：只掃描根目錄
        }
        return nil                    // 遞迴模式：繼續往下
    }
    // 處理檔案...
})
```

取消信號改用 `filepath.SkipAll`（Go 1.20+），立即終止整棵樹的遍歷。

**教訓**

`filepath.Walk` 和 `filepath.WalkDir` 的行為略有不同；有取消需求時優先用 `WalkDir` + `SkipAll`。

---

### 坑 7：掃描中無法取消（只能強制關閉程式）

**症狀**

掃描大型目錄或搜尋途中沒有取消按鈕，只能 Alt+F4 強制關閉。

**根本原因**

Nova agent 未實作取消機制。

**修法（2026-04-07 已修）**

1. `App` struct 加入 `cancelScan context.CancelFunc` + `cancelMu sync.Mutex`
2. `ScanDirectory` 改用 `context.WithCancel`，每次迭代檢查 `scanCtx.Done()`
3. 新增 `CancelOperation()` binding
4. 前端 `isRunning` 狀態下顯示紅色「取消」按鈕（`StopCircle` 圖示）

**教訓**

長時間操作必須從一開始就設計取消機制（`context.CancelFunc`）。Go 的 context cancellation 是標準模式，應在設計 binding 時就納入。

---

### 坑 8：同番號重複出現在掃描結果（浪費搜尋請求）

**症狀**

掃描 99 個檔案後，EBON-004 出現兩次（#8、#52），CEMD-818 出現兩次（#78、#88），搜尋也跟著各送兩次請求。

**根本原因**

同一番號的影片存在於不同路徑（不同子目錄），或影片本體與字幕/封面 NFO 都被 extractor 提取到相同番號。`ScanDirectory` 原本沒有去重邏輯。

**修法（2026-04-07 已修）**

加入 `seen map`，相同番號只保留第一個路徑：

```go
seen := make(map[string]bool)
if code != "" && !seen[code] {
    seen[code] = true
    results = append(results, ScanResult{Path: path, Code: code})
    wailsRuntime.EventsEmit(a.ctx, "scan:progress", len(results), code)
}
```

同時修正 progress counter 顯示「已找到番號數」而非「已掃描檔案數」。

**教訓**

掃描去重應在 **Go 端**做；progress counter 應顯示對使用者有意義的數字（有效番號數），不是原始檔案掃描計數。

---

## 已知限制（未修，待 W7+）

| 功能缺口 | 原版行為 | Wails 版現況 |
|---------|---------|-------------|
| 移動目標路徑 | `outputDir/女優名/番號/` | `outputDir/番號/`（缺少女優名資料夾）|
| 互動分類確認 | 顯示女優候選、逐一確認 | 無此流程 |
| 片商分類工作流程 | 依片商分資料夾 | 無此功能 |
| 資料庫瀏覽 UI | 可查詢已建立記錄 | 無此頁面 |

---

## E2E 效能數據（2026-04-07 實測）

| 步驟 | 耗時 | 備註 |
|------|------|------|
| 掃描 99 個檔案 | **< 1 秒** | 純 Go `filepath.WalkDir` |
| 辨識有效番號（修復前）| — | 65 筆（含 2 重複）|
| 辨識有效番號（修復後）| — | 63 筆（去重）|
| 搜尋 65 筆（修復前）| **75 秒** | 09:17:17 → 09:18:32 |
| 搜尋平均每筆 | **~1.15 秒** | Python subprocess + HTTP |
| 搜尋成功率 | **65/65 = 100%** | AV-WIKI 為主要來源 |
| 並行 workers | **5** | 可調高到 10-15 |

**效能瓶頸**：Python subprocess 啟動 + HTTP 往返延遲  
**優化建議**：workers 調高到 10-15（需留意 AV-WIKI 速率限制）

---

## 資料庫路徑注意事項

`actress-classifier.exe` 使用相對路徑讀取設定與資料庫：

```ini
[database]
json_data_dir = data/json_db   ← 相對於 CWD
```

**必須從專案根目錄啟動 exe**，否則找不到 `data/json_db` 和 `config.ini`：

```powershell
cd C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration
.\wails-app\build\bin\actress-classifier.exe
```

若要打包發行，需將路徑改為絕對路徑或隨 exe 附帶 config.ini。

---

## 延伸閱讀

- [wiki/pitfalls/wails-scan-duplicate.md](../../wiki/pitfalls/wails-scan-duplicate.md)
- [wiki/architecture/wails-gui.md](../../wiki/architecture/wails-gui.md)
- [wiki/architecture/search-engine.md](../../wiki/architecture/search-engine.md)
