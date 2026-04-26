# Wails GUI 架構

> 記錄現行 Wails v2 + React/TypeScript 桌面應用程式架構，取代原有 Python Tkinter GUI。
> 更新：2026-04-27（校正 binding、事件 payload 與 portable 發行現況）

---

## 整體架構

```
Wails GUI (React 18 + TypeScript 前端)
        ↓ Wails binding（直接呼叫 Go 函數，無需橋接）
Go 後端 (wails-app/backend/app.go)
        ↓ 直接 import
pkg/ (extractor / mover / database / studio / cache / app)
        ↓ subprocess
Python 搜尋腳本 (run_search.py / run_batch_search.py)
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
| `GetStudiosByCodes(codes)` | studios.json | 批次依番號前綴查片商 |
| `GetStudioByCode(code)` | studios.json | 單番號查片商 |
| `GetActressPrimaryStudios(names)` | pkg/database | DB fallback 查女優主要片商 |
| `BatchMoveDirs(items, strategy)` | pkg/app/move_service | 批次移動整個女優資料夾 |
| `GetPreferences()` | backend/services/config | 讀取設定 |
| `UpdatePreferences(prefs)` | backend/services/config | 儲存設定 |
| `ResetPreferences()` | backend/services/config | 重設設定 |
| `PythonSearch(code)` | subprocess | 呼叫 Python 爬蟲 |
| `BatchSearch(codes, workers)` | subprocess + JSON Lines | 預設級聯批次搜尋 |
| `BatchSearchAVWiki(codes, workers)` | subprocess + `source_mode=avwiki` | AV-WIKI-only 補搜 |
| `BatchSearchJAVDB(codes, workers)` | subprocess + `source_mode=javdb` | JAVDB-only 補搜 |

---

## Python 爬蟲整合（subprocess）

```
Go: PythonSearch("STARS-001")
      ↓
subprocess: python src/scrapers/run_search.py STARS-001 [source_mode]
      ↓ stdout JSON
{"code":"STARS-001","title":"...","actresses":["..."],"studio":"...","search_method":"..."}
      ↓
Go 解析 JSON → 回傳 React 前端
```

**錯誤分類**：
- `timeout`：60 秒超時
- `stderr`：Python 執行錯誤
- `json_parse`：輸出格式不合法

**批次搜尋**：Wails backend 啟動單一 `run_batch_search.py` 子程序，Python 端用 `ThreadPoolExecutor` 平行處理並逐行輸出 JSON Lines；Go 端即時讀取每行結果、寫入 DB，並透過 Wails Events 推送進度：

```
EventsEmit(ctx, "search:progress", current, total, code)
EventsEmit(ctx, "search:result", SearchResult)
EventsEmit(ctx, "search:done", summary)
```

---

## Wails Events（後端 → 前端推送）

| 事件名稱 | 觸發時機 | payload |
|---------|---------|---------|
| `scan:progress` | 掃描找到一筆去重後結果 | `(foundCount, code)` |
| `search:progress` | 批次搜尋進度 | `(current, total, code)` |
| `search:result` | 單筆搜尋完成 | `(SearchResult)` |
| `search:done` | 全部批次搜尋完畢或提前失敗 | `(summary)` |
| `error` | 後端流程錯誤 | `(message)` |

後端目前以 `emitEvent("error", message)` 發送錯誤事件。前端事件集中於 `wails-app/frontend/src/lib/wailsEvents.ts`，維護時需確保事件名稱與 backend 相同；move / studio move 主要透過 binding 回傳值更新 UI，不是後端事件主路徑。

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

## 建置與發行

正式桌面發行目標是 Windows portable bundle：

```powershell
.\setup.ps1
```

腳本會：

1. 建置 `classifier.exe`
2. 執行 `wails build` 並複製 `actress-classifier.exe` 到 repo root
3. 組裝 `dist\portable\`
4. 壓縮成 `dist\PornActressDB-windows-portable.zip`

portable bundle 內必須包含 `src\`、`requirements.txt`、`Start-ActressClassifier.bat` 與 `Setup-SearchRuntime.ps1`，因為搜尋功能仍透過 Python 腳本執行。第一次啟動由 `Start-ActressClassifier.bat` 建立 `.venv` 並安裝搜尋依賴。
