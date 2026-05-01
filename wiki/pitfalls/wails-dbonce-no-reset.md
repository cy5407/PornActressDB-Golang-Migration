---
category: Wails
date: 2026-04-08
status: resolved
---
# Wails dbOnce 無法重置：設定變更後 DB 路徑不生效

> ✅ **狀態：已修復**。`wails-app/backend/app.go` 現行做法：
> - `App` struct 持有 `dbMu sync.Mutex`（非 `sync.Once`，line 39）
> - `ensureDB()`（line 1037）每次都進 mutex、檢查 `data.json` modtime，必要時重建 `*JSONDatabase`
> - `UpdatePreferences()` / `ResetPreferences()` 寫完設定後呼叫 `a.resetDB()`（line 1074），把 `a.db` 設為 nil
>
> 下一次任何操作呼叫 `ensureDB()` 就會以新 `JSONDataDir` 重新初始化，不需重啟。本頁保留作為 sync.Once 一旦執行無法逆轉的歷史教訓。

## 症狀

用戶在 PreferencesDialog 修改 DB 路徑後儲存，但 `BatchSearch`、`BatchMove` 等操作仍然使用舊路徑。必須完整重啟 actress-classifier.exe 才會生效。

## 根因

`app.go` 使用 `sync.Once` 初始化 DB，保證 DB 只建立一次：

```go
var dbOnce sync.Once

func (a *App) ensureDB() {
    dbOnce.Do(func() {
        dataDir := resolveDataDir()
        a.db, _ = database.NewJSONDatabase(dataDir)
    })
}
```

`sync.Once` 執行過後無法重置。即使用戶透過 `SaveConfig()` 寫入新的 DB 路徑，`dbOnce` 已完成，下次呼叫 `ensureDB()` 不會重新初始化。

## 正確做法

改用可重置的方式初始化 DB，例如用 mutex + nil 判斷：

```go
var dbMu sync.Mutex

func (a *App) ensureDB() {
    dbMu.Lock()
    defer dbMu.Unlock()
    if a.db != nil {
        return
    }
    dataDir := resolveDataDir()
    db, err := database.NewJSONDatabase(dataDir)
    if err != nil {
        return
    }
    a.db = db
}

// 設定變更後呼叫此方法重置 DB
func (a *App) resetDB() {
    dbMu.Lock()
    defer dbMu.Unlock()
    a.db = nil
}
```

在 `SaveConfig()` 後呼叫 `a.resetDB()`，下次操作時會自動用新路徑重新初始化。

## 驗證 fix 是否在你的 build

```powershell
# 應命中 → fix 已套用
Select-String "dbMu sync.Mutex" wails-app\backend\app.go
Select-String "func \(a \*App\) resetDB\(\)" wails-app\backend\app.go

# 不應命中 → 若命中代表回到舊 sync.Once 寫法（regression）
Select-String "dbOnce sync.Once" wails-app\backend\app.go
```

## 參考

- `wails-app/backend/app.go` — `ensureDB()`、`UpdatePreferences()`、`resetDB()`
- Go `sync.Once` 文件：Once 一旦完成無法逆轉
