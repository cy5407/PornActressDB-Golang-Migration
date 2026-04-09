---
category: Wails
date: 2026-04-08
---
# Wails v2 建置踩坑全記錄

## 問題 A：npm 版本衝突（@tailwindcss/vite peer dependency）

### 症狀

```
npm error ERESOLVE unable to resolve dependency tree
peer vite@"^5.1.0" from @tailwindcss/vite@4.2.2
```

### 根本原因

`@tailwindcss/vite@4.2.2` 需要 `vite@^5`，但 `package.json` 鎖定 `vite@^3`，peer dependency 衝突導致 `wails build` 失敗。

### 解決方案

修改 `wails.json` 的前端安裝命令：

```json
"frontend:install": "npm install --legacy-peer-deps"
```

> `wails.json` 是 Wails 控制前端建置流程的設定入口，不能只改 `package.json`。

---

## 問題 B：TypeScript 命名空間錯誤（backend vs services）

### 症狀

```
Property 'Preferences' does not exist on type 'typeof backend'
```

### 根本原因

Go struct `Preferences` 定義在 `services` package，Wails 自動產生的 TypeScript binding 對應命名空間為 `services`，而非 `backend`。

### 解決方案

```tsx
// ❌ 錯誤
import { backend } from '../../wailsjs/go/models'
type: backend.Preferences

// ✅ 正確
import { services } from '../../wailsjs/go/models'
type: services.Preferences
```

**規則**：Wails binding 的 TS 命名空間 = **Go struct 所在 package 名稱**。

---

## 問題 C：`OpenDirectoryDialog` 前端無法呼叫

### 症狀

`window.runtime?.OpenDirectoryDialog()` 執行後靜默失敗，對話框不出現。

### 根本原因

Wails v2 的 JavaScript runtime 物件並不暴露 `OpenDirectoryDialog` 方法；native dialog 必須透過 Go binding 呼叫。

### 解決方案

在 `app.go` 新增 binding：

```go
func (a *App) SelectDirectory(title string) string {
    dir, _ := wailsRuntime.OpenDirectoryDialog(a.ctx, wailsRuntime.OpenDialogOptions{
        Title: title,
    })
    return dir
}
```

前端改為：

```ts
import { SelectDirectory } from '../../wailsjs/go/backend/App'
const dir = await SelectDirectory("選擇影片目錄")
```

---

## 相關文件

- [docs/茶包射手/wails-e2e-scan.md](../../docs/茶包射手/wails-e2e-scan.md)（完整 8 坑紀錄）
- [architecture/wails-gui.md](../architecture/wails-gui.md)
