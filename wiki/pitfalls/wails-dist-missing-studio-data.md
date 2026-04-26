---
category: Wails
date: 2026-04-08
---
# Wails dist 缺少片商資料導致分類失敗

**日期**：2026-04-08  
**嚴重度**：🟡 中（片商識別功能完全失效，其餘功能正常）

---

## 問題描述

Wails app 的 `actress-classifier.exe` 執行時找不到 `studios.json`，
導致所有影片都無法識別片商，片商分類功能整體失效。

---

## 根本原因

`wails-app/backend/app.go` 的 `resolveStudiosPath()` 以「與 EXE 同目錄」為最高優先搜尋路徑：

```go
func resolveStudiosPath() string {
    // 1. 與 EXE 同目錄（最優先）
    exeDir, _ := filepath.Abs(filepath.Dir(os.Args[0]))
    candidate := filepath.Join(exeDir, "studios.json")
    if _, err := os.Stat(candidate); err == nil {
        return candidate
    }
    // 2. 當前工作目錄... 等 fallback
}
```

但 `dist/` 目錄下只有：
```
dist/
└── actress-classifier.exe   ← EXE 在這裡
    （沒有 studios.json！）
```

專案根目錄的 `studios.json` / `major_studios.json` **不會自動複製**到 `dist/`。

---

## 修復方案

### 現行修復

目前正式發行改走 `setup.ps1` 組裝 Windows portable bundle。腳本會把下列檔案複製進 `dist\portable\`：

- `studios.json`
- `major_studios.json`

因此一般發行時應分發：

```text
dist\PornActressDB-windows-portable.zip
```

不要只複製單一 `actress-classifier.exe`。

### 歷史手動修復

若仍在手動測試舊 `dist\` 目錄，可手動複製：

```powershell
Copy-Item studios.json dist\studios.json
Copy-Item major_studios.json dist\major_studios.json
```

---

## 長期建議

在 Wails 建置後步驟自動同步。現行 `setup.ps1` 已負責 portable bundle；若另外維護獨立 build script，至少要包含：

```powershell
# wails build 之後執行
wails build -platform windows/amd64
Copy-Item studios.json "dist\portable\studios.json"
Copy-Item major_studios.json "dist\portable\major_studios.json"
```

或在 `Makefile` / `build.ps1` 中加入同等步驟，避免每次手動操作遺忘。

---

## 相關檔案

- `wails-app/backend/app.go` — `resolveStudiosPath()`、`resolveMajorStudiosPath()`
- `setup.ps1` — 現行 portable bundle 組裝腳本
- `studios.json` — 番號前綴→片商對應表（需同步到 bundle）
- `major_studios.json` — 大片商名稱清單（需同步到 bundle）
