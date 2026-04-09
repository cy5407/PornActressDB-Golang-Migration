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

手動（或建置腳本中）複製：

```powershell
Copy-Item studios.json dist\studios.json
Copy-Item major_studios.json dist\major_studios.json
```

---

## 長期建議

在 Wails 建置後步驟自動同步：

```powershell
# wails build 之後執行
wails build -platform windows/amd64
Copy-Item studios.json "wails-app\build\bin\studios.json"
Copy-Item major_studios.json "wails-app\build\bin\major_studios.json"
```

或在 `Makefile` / `build.ps1` 中加入此步驟，避免每次手動操作遺忘。

---

## 相關檔案

- `wails-app/backend/app.go` — `resolveStudiosPath()`、`resolveMajorStudiosPath()`
- `studios.json` — 番號前綴→片商對應表（需同步到 dist/）
- `major_studios.json` — 大片商名稱清單（需同步到 dist/）
