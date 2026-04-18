# 新增 GUI 按鈕（Wails / React）

> ⚠️ **注意**：Python Tkinter GUI（`src/ui/`）已於 2026-04-07 W6 完全移除。
> 本文件已更新為 **Wails v2 + React/TypeScript** 規範。
> 舊 Tkinter 版本請見 `docs/archive/`（若存在）。

---

## 前提知識

- GUI 位於 `wails-app/frontend/src/`（React 18 + TypeScript）
- Go bindings 定義於 `wails-app/backend/app.go`
- 新增功能需要同時修改：**前端 React 元件** + **後端 Go binding**（若需要新 API）

---

## 完整範本：新增一個操作按鈕

### 1. 後端：在 `app.go` 新增 binding 方法

```go
// wails-app/backend/app.go

// MyFeature 執行某項功能。
func (a *App) MyFeature(param string) MyFeatureResult {
    // 直接呼叫 pkg/ 套件
    result, err := somePackage.DoSomething(param)
    if err != nil {
        return MyFeatureResult{Error: err.Error()}
    }
    return MyFeatureResult{Data: result}
}
```

### 2. 後端：定義回傳型別

```go
type MyFeatureResult struct {
    Data  string `json:"data"`
    Error string `json:"error,omitempty"`
}
```

### 3. 重新產生 TypeScript bindings

```powershell
cd wails-app
wails build  # 或 wails generate
```

這會自動更新 `frontend/src/wailsjs/go/backend/App.js` 及對應 `.d.ts`。

### 4. 前端：在 React 元件中呼叫

```tsx
// wails-app/frontend/src/App.tsx（或對應元件）

import { MyFeature } from '../wailsjs/go/backend/App'

const handleMyFeature = async () => {
  setLoading(true)
  try {
    const result = await MyFeature(param)
    if (result.error) {
      setStatus(`❌ 錯誤：${result.error}`)
    } else {
      setStatus(`✅ 完成`)
    }
  } catch (e) {
    setStatus(`❌ 呼叫失敗：${e}`)
  } finally {
    setLoading(false)
  }
}

// 在 JSX 中加入按鈕
<button onClick={handleMyFeature} disabled={loading}>
  🔧 功能名稱
</button>
```

### 5. 使用 Wails Events 推送進度（耗時操作）

```go
// app.go — 後端主動推送進度
func (a *App) MyLongFeature(codes []string) {
    for i, code := range codes {
        // 處理 code...
        wailsRuntime.EventsEmit(a.ctx, "myfeature:progress", map[string]interface{}{
            "current": i + 1,
            "total":   len(codes),
            "code":    code,
        })
    }
    wailsRuntime.EventsEmit(a.ctx, "myfeature:done", map[string]interface{}{
        "total": len(codes),
    })
}
```

```tsx
// 前端監聽事件
import { EventsOn } from '../wailsjs/runtime/runtime'

useEffect(() => {
  const unsubProgress = EventsOn('myfeature:progress', (data) => {
    setProgress(`${data.current} / ${data.total}`)
  })
  const unsubDone = EventsOn('myfeature:done', (data) => {
    setStatus(`✅ 完成 ${data.total} 項`)
  })
  return () => { unsubProgress(); unsubDone() }
}, [])
```

---

## ❌ 常見錯誤

| 錯誤 | 說明 | 修正 |
|------|------|------|
| 直接在 Go binding 做耗時操作而不推送進度 | 前端顯示無回應 | 用 `EventsEmit` 推送中間狀態 |
| TypeScript bindings 未重新產生 | 呼叫新函式報 undefined | 執行 `wails build` 或 `wails generate` |
| 忘記定義回傳型別 | JSON 解析失敗 | 在 `app.go` 補上對應 struct |
| 在 Goroutine 中直接寫 React state | 不適用，Wails 已有 Event 機制 | 改用 `EventsEmit` |

---

## GUI 執行緒規則

- Go binding 函式預設在主 Goroutine 執行；耗時操作應用 `go func()` + `EventsEmit` 推送進度
- `a.ctx` 須在 `Startup()` 後才可用；若在 `NewApp()` 時呼叫 `EventsEmit` 會 panic
- 取消操作：使用 `a.cancelScan`（`context.CancelFunc`）搭配 `context.WithCancel`

---

## 相關頁面

- [wails-gui.md](../architecture/wails-gui.md) — Wails 架構與 Bindings 對照表
- [add-go-cli-command.md](add-go-cli-command.md) — 若需同時新增 CLI 子命令
