# 新增 Go API 函式 ← 必讀

> ⚠️ **注意**：`src/services/go_api/`、`go_bridge.py`、`go_runner.py` 已於 2026-04-07 W6 **全數移除**。
> 本文件已更新為現行架構（Wails binding + `go_cli.py`）。

---

## 現行架構下的「Go API」分兩種

### 情況 A：Wails GUI 需要新功能

在 `wails-app/backend/app.go` 新增 binding 方法。
→ 詳見 [patterns/add-gui-button.md](add-gui-button.md)

### 情況 B：Python 搜尋管線需要呼叫 Go CLI

透過 `src/services/go_cli.py` 呼叫 `classifier.exe`。

---

## 情況 A：新增 Wails Binding

### 📋 三步驟 Checklist

```
[ ] Step 1: wails-app/backend/app.go  ← 實作 Go 方法 + 回傳型別 struct
[ ] Step 2: wails build               ← 自動產生 TypeScript bindings
[ ] Step 3: 前端 React 元件呼叫新函式
```

```go
// Step 1: wails-app/backend/app.go
type NewFeatureResult struct {
    Data  string `json:"data"`
    Error string `json:"error,omitempty"`
}

func (a *App) NewFeature(param string) NewFeatureResult {
    result, err := somePackage.DoSomething(param)
    if err != nil {
        return NewFeatureResult{Error: err.Error()}
    }
    return NewFeatureResult{Data: result}
}
```

---

## 情況 B：Python 呼叫 Go CLI（go_cli.py）

若 Python 搜尋管線（`src/services/`、`src/models/`）需要呼叫新的 `classifier.exe` 子命令，統一透過 `go_cli.py`：

```python
# src/services/go_cli.py 使用範例
from services import go_cli

result = go_cli.run(["db", "get", "STARS-707"], exe_path=exe_path)
data = json.loads(result.stdout)
```

若需要新的 CLI 子命令，先在 `cmd/scanner/` 實作，再透過 `go_cli.run()` 呼叫。
→ 詳見 [patterns/add-go-cli-command.md](add-go-cli-command.md)

---

## 為什麼不再需要「三個地方同步」？

舊架構（已移除）：

```
go_api/db.py → go_api/__init__.py → go_bridge.py  ← 三處必須同步
```

現行架構：

- **Wails 路徑**：`app.go` → `wails build`（TypeScript bindings 自動產生）
- **Python 路徑**：直接 `go_cli.run([...])` → 無需額外層

---

## 相關踩坑

- [go_api 匯出遺漏](../pitfalls/go-api-export-missing.md)（Issue 14）— 歷史紀錄，舊架構問題
- [GUI Bridge 取法錯誤](../pitfalls/gui-bridge-wrong-access.md)（Issue 13）— 歷史紀錄，舊架構問題
