# Wails GUI 架構

> 記錄 Wails v2 + React/TypeScript 桌面應用程式架構，取代原有 Python Tkinter GUI。  
> 完成於：2026-04-07（W1~W6 全部由 Nova agent 實作完畢）

---

## 整體架構

```
Wails GUI (React 18 + TypeScript 前端)
        ↓ Wails binding（直接呼叫 Go 函數，無需橋接）
Go 後端 (wails-app/backend/app.go)
        ↓ 直接 import
pkg/ (extractor / mover / database / studio / cache / app)
        ↓ subprocess
Python 爬蟲服務 (src/scrapers/run_search.py)
```

**與舊架構的差異：**
- ❌ 舊：`Python Tkinter → go_api/ → go_bridge.py → Go CLI`
- ✅ 新：`React → Wails binding → Go 函數`（零橋接層）

---

## 目錄結構

```
wails-app/
├── wails.json                  # Wails 設定（productName、版本、圖示）
├── main.go                     # 進入點，初始化 App struct
├── backend/
│   ├── app.go                  # 所有 Wails binding 方法
│   ├── app_test.go             # backend 單元測試
│   └── services/
│       └── config.go           # config.ini 讀寫（ConfigService）
└── frontend/
    ├── src/
    │   ├── App.tsx             # 主畫面骨架
    │   ├── components/
    │   │   ├── DirectoryPicker.tsx
    │   │   ├── VideoList.tsx / VideoCard.tsx
    │   │   ├── SearchPanel.tsx
    │   │   ├── ProgressBar.tsx
    │   │   ├── StatusBar.tsx
    │   │   ├── SearchResultDialog.tsx
    │   │   ├── OperationHistoryDialog.tsx
    │   │   └── PreferencesDialog.tsx
    │   ├── stores/
    │   │   └── taskStore.ts    # Zustand 狀態管理
    │   └── wailsjs/            # 自動產生的 TypeScript bindings
    ├── tailwind.config.js
    └── package.json
```

---

## Go Bindings（backend/app.go）

| 方法 | 對應 pkg/ | 說明 |
|------|----------|------|
| `ScanDirectory(dir, workers, recursive)` | pkg/app/scan_service | 並發掃描目錄 |
| `MoveFile(src, dst, strategy)` | pkg/app/move_service | 單檔移動 |
| `BatchMove(items, strategy)` | pkg/app/move_service | 批次移動 |
| `RollbackLast()` | pkg/app/history_service | 回滾最近操作 |
| `RollbackOperation(id)` | pkg/app/history_service | 回滾指定操作 |
| `ListOperations()` | pkg/app/history_service | 列出操作記錄 |
| `GetOperation(id)` | pkg/app/history_service | 取得單筆記錄 |
| `DbGetVideo(code)` | pkg/database | 查詢影片資料 |
| `DbUpdateVideo(code, data)` | pkg/database | 更新影片資料 |
| `DbListVideos()` | pkg/database | 列出所有影片 |
| `IdentifyStudio(code)` | pkg/studio | 識別片商 |
| `ListStudios()` | pkg/studio | 列出所有片商 |
| `StudioClassifyMove(codes, outputDir, workers)` | pkg/database + pkg/app/move_service | 片商分類移動（W7）→ 詳見 [片商分類架構](studio-classification.md) |
| `GetPreferences()` | backend/services/config | 讀取設定 |
| `UpdatePreferences(prefs)` | backend/services/config | 儲存設定 |
| `ResetPreferences()` | backend/services/config | 重設設定 |
| `PythonSearch(code)` | subprocess | 呼叫 Python 爬蟲 |
| `BatchSearch(codes)` | subprocess + goroutine pool | 批次搜尋 |

---

## Python 爬蟲整合（subprocess）

```
Go: PythonSearch("STARS-001")
      ↓
subprocess: python src/scrapers/run_search.py --code STARS-001
      ↓ stdout JSON
{"code":"STARS-001","title":"...","actress":"...","studio":"..."}
      ↓
Go 解析 JSON → 回傳 React 前端
```

**錯誤分類**：
- `timeout`：60 秒超時
- `stderr`：Python 執行錯誤
- `json_parse`：輸出格式不合法

**批次搜尋**：goroutine pool（semaphore 限流），透過 Wails Events 推送進度：
```
EventsEmit(ctx, "search:progress", {...})
EventsEmit(ctx, "search:result", {...})
EventsEmit(ctx, "search:done", {...})
```

---

## Wails Events（後端 → 前端推送）

| 事件名稱 | 觸發時機 | payload |
|---------|---------|---------|
| `scan:progress` | 掃描每批完成 | `{current, total}` |
| `search:progress` | 批次搜尋進度 | `{current, total, code}` |
| `search:result` | 單筆搜尋完成 | `{code, result}` |
| `search:done` | 全部批次搜尋完畢 | `{total, success, failed}` |
| `studio:move:progress` | 片商分類移動進度（W7） | `{current, total, code}` |
| `studio:move:done` | 片商分類移動完畢（W7） | `{total, success, failed}` |

---

## 已移除的舊元件（W6 清理）

| 移除項目 | 行數 | 說明 |
|---------|------|------|
| `src/ui/` | ~2,588 | Python Tkinter GUI（5 個檔案） |
| `src/services/go_bridge.py` | 146 | Python→Go 橋接 facade |
| `src/services/go_runner.py` | 102 | subprocess 執行器 |
| `src/services/go_api/` | ~1,339 | 領域 API 層（scan/move/db/identify） |
| `src/services/classifier_core.py` | 1,498 | 分類核心（已移至 Wails 路徑） |
| `src/services/interactive_classifier.py` | 255 | 互動分類器 |
| `src/services/studio_classifier.py` | 853 | 片商分類器 |
| `src/services/encoding_enhancer.py` | 169 | 孤立模組 |
| `src/services/japanese_site_enhancer.py` | 248 | 孤立模組 |
| `src/scrapers/unified_scraper.py` | 527 | 孤立模組 |
| **合計** | **~7,725 行** | — |

---

## W7 待辦（E2E 驗收）

- [ ] 執行 `e2e/run_e2e.sh` 通過
- [ ] `wails build` 產生 `.exe`
- [ ] NSIS installer 安裝/解安裝正常
- [ ] Python 爬蟲在打包後可被正確呼叫
- [ ] 乾淨 Windows 環境 smoke test

詳見：[docs/plans/Tasks.md](../../docs/plans/Tasks.md)
