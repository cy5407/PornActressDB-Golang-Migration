---
category: Wails
date: 2026-04-08
---
# Wails dbOnce 無法重置：設定變更後 DB 路徑不生效

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

## 參考

- `wails-app/backend/app.go` — `ensureDB()`、`SaveConfig()`
- Go `sync.Once` 文件：Once 一旦完成無法逆轉
