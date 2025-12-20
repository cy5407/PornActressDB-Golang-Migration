# Go Scanner MVP - Quick Start

## 已完成

✅ **Phase 1: Pure Logic Port**
- `pkg/extractor/extractor.go` - 核心番號提取邏輯（從 Python 移植）
- `pkg/extractor/extractor_test.go` - 完整單元測試（14 個測試案例全通過）

✅ **Phase 2: High Performance Scanner**
- `cmd/scanner/main.go` - CLI 掃描器（支援並發處理）
- 編譯產出：`classifier.exe`

✅ **Phase 3: Python Integration**
- `tools/integration/go_integration.py` - Python 呼叫 Go 的整合範例

✅ **Phase 4: File Mover** (2025-12-21 新增)
- `pkg/mover/mover.go` - 檔案移動核心邏輯
- `pkg/mover/mover_test.go` - 完整單元測試（11 個測試案例全通過）
- CLI 命令：`classifier.exe move`、`classifier.exe history`
- 功能：
  - 單檔/批次移動
  - 4 種衝突策略（skip, overwrite, rename, merge）
  - 操作日誌記錄
  - 回滾功能

## 測試結果

```bash
# 單元測試
go test ./pkg/... -v
# pkg/extractor: PASS (14 cases)
# pkg/mover: PASS (11 cases)

# CLI 掃描測試
.\classifier.exe scan -dir "C:\Users\cy540\Downloads\test_videos"
# 成功識別: STARS-707, SSIS-999, IPX-123
# 正確過濾: FC2-PPV-123456 (跳過)

# CLI 移動測試
.\classifier.exe move -src "source.mp4" -dst "dest/source.mp4" -strategy skip
.\classifier.exe move -batch moves.json -dry-run
.\classifier.exe history list
.\classifier.exe history rollback abc123

# Python 整合測試
python tools/integration/go_integration.py "C:\Users\cy540\Downloads\test_videos"
# 成功透過 subprocess 呼叫 Go 並解析 JSON
```

## 效能

- **單執行緒**: ~20ms (3 個檔案)
- **並發處理**: 支援 `-workers` 參數調整（預設 10）

## 使用方式

### 直接使用 Go CLI
```powershell
# 掃描番號
.\classifier.exe scan -dir "D:\Videos"
.\classifier.exe scan -dir "D:\Videos" -workers 20

# 移動檔案
.\classifier.exe move -src "A.mp4" -dst "dest/A.mp4"
.\classifier.exe move -batch moves.json
.\classifier.exe move -src "A.mp4" -dst "dest/A.mp4" -dry-run

# 操作歷史
.\classifier.exe history list
.\classifier.exe history show abc123
.\classifier.exe history rollback abc123
```

---

## 🎯 MVP：Python 主程式整合

> 詳細規格請參考 [GO_MIGRATION_TODO.md](GO_MIGRATION_TODO.md)

### 整合狀態

| MVP 項目 | 說明 | 狀態 |
|---------|------|------|
| MVP-1 | Go 橋接層 `src/services/go_bridge.py` | ✅ 已完成 (21 測試通過) |
| MVP-2 | 整合掃描功能 | ✅ 已完成 |
| MVP-3 | 整合檔案移動功能 | ⬜ 待實作 |
| MVP-4 | 設定檔整合 `config.ini` | ✅ 已完成 |
| MVP-5 | GUI 整合回滾功能 | ⬜ 待實作 |

### MVP-2 實作內容 (2025-12-21)

1. **config.ini** - 新增 `[go_integration]` 區塊
   ```ini
   [go_integration]
   enabled = true              # 是否啟用 Go 加速
   exe_path =                  # classifier.exe 路徑（留空自動偵測）
   scan_workers = 10           # 掃描並發數
   move_conflict_strategy = skip  # 移動衝突策略
   enable_operation_log = true    # 是否記錄操作日誌
   log_dir = logs              # 日誌目錄
   ```

2. **src/models/config.py** - 新增預設值
3. **src/utils/scanner.py** - 完整重構
   - 新增 `use_go`, `go_workers`, `go_exe_path` 參數
   - 新增 `from_config()` 類別方法
   - 新增 `scan_with_codes()` 方法（Go 專用）
   - 自動回退機制（Go 不可用時切換 Python）

4. **src/services/classifier_core.py** - 使用 `from_config()` 建立掃描器

### 整合架構

```
┌─────────────────────────────────────────────────────────┐
│                    run.py (GUI)                         │
├─────────────────────────────────────────────────────────┤
│  classifier_core.py  │  studio_classifier.py            │
├─────────────────────────────────────────────────────────┤
│                  go_bridge.py (MVP-1)                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │ scan_dir()  │  │ move_file() │  │ rollback()  │     │
│  └─────────────┘  └─────────────┘  └─────────────┘     │
├─────────────────────────────────────────────────────────┤
│              subprocess.run() (JSON)                    │
├─────────────────────────────────────────────────────────┤
│                   classifier.exe                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │ scan        │  │ move        │  │ history     │     │
│  └─────────────┘  └─────────────┘  └─────────────┘     │
├─────────────────────────────────────────────────────────┤
│  pkg/extractor   │  pkg/mover                           │
└─────────────────────────────────────────────────────────┘
```

---

## 檔案結構
```
PornActressDB-Golang-Migration/
├── pkg/
│   ├── extractor/
│   │   ├── extractor.go          # 核心提取器 ✅
│   │   └── extractor_test.go     # 單元測試 ✅
│   └── mover/
│       ├── mover.go              # 檔案移動器 ✅
│       └── mover_test.go         # 單元測試 ✅
├── cmd/
│   └── scanner/
│       └── main.go               # CLI 工具 ✅
├── src/
│   ├── services/
│   │   └── go_bridge.py          # Python 橋接層 ✅ MVP-1
│   ├── utils/
│   │   └── scanner.py            # 整合 Go 加速 ✅ MVP-2
│   └── models/
│       └── config.py             # 設定檔管理 ✅ MVP-4
├── tools/
│   └── integration/
│       └── go_integration.py     # Python 整合範例 ✅
├── config.ini                    # Go 整合設定 ✅ MVP-4
├── classifier.exe                # 編譯產出 ✅
└── go.mod
```
