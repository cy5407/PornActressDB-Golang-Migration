# OpenClaw 審閱計畫 — Python → Go 遷移完整度檢查

**專案路徑**: `C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration`  
**建立日期**: 2026-04-06  
**目的**: 由 OpenClaw 仔細審閱每一個已宣稱完成遷移的項目，確認 Go 實作完整、Python 端已正確委派，並識別下一階段可遷移的項目。

---

## 審閱原則

1. **逐檔讀取，不得跳過**：每個檔案都要真正讀取程式碼，不能只看檔名推斷。
2. **逐方法確認**：每個 public method 都需標記遷移狀態。
3. **Go 完整性優先**：確認 Python 呼叫的 Go CLI 子命令實際存在且 JSON 格式正確。
4. **誠實回報**：若發現實作缺漏，明確指出，不可美化。

---

## 已完成 Phase 背景（不重複提議）

| Phase | 內容 | 刪減量 |
|-------|------|--------|
| 1–5   | 基礎委派：scan/move/extract/identify/db CRUD | 基礎架構建立 |
| 6A    | extractor.py, studio.py, scanner.py, file_mover.py fallback 清除 | ~250 行 |
| 6B    | cache_manager.py fallback 清除（第一波） | ~80 行 |
| 6C    | go_accelerated_db.py, go_accelerated_studio.py 整檔刪除 | ~475 行 |
| 6D    | json_database.py, incremental_json_database.py 瘦身 | ~1,200 行 |
| 7A    | Actress CRUD：GetActress/UpsertActress/DeleteActress/ListActresses | — |
| 7B    | 統計：GetActressStats/GetStudioStats | — |
| 7C    | Cache cleanup：cache_get_stats/cache_prune/cache_clear | — |
| 7D    | Backup：BackupCreate/BackupRestore/BackupList/BackupCleanup | — |
| 7E    | json_database.py Python fallback 瘦身 | -137 行 |
| 8A    | json_database.py backup fallback 全移除 | -82 行 |
| 8B    | cache_manager.py 5 個方法 fallback 全移除 | -222 行 |

**總計移除**: ~2,500+ 行 Python 程式碼

---

## 唯一合法 Python fallback 原則

| 操作類型 | Go 不可用時的正確做法 |
|---------|-------------------|
| 寫入 / 刪除 | `raise RuntimeError(...)` |
| 磁碟讀取 | `raise RuntimeError(...)` |
| 工具性功能（backup/cache） | `raise RuntimeError(...)` |
| **記憶體讀取** (`self.data.get(...)`) | **保留輕量 fallback** ← 唯一例外 |

---

## 任務一：Python 端逐方法審閱

> 對每個方法標記狀態：
> - ✅ 完全委派 Go（無 Python 實作 fallback）
> - ⚠️ 部分委派（仍保留 Python fallback，需評估是否合法）
> - ❌ 尚未委派（純 Python 實作，應考慮遷移）
> - 🔵 合法保留（GUI / 爬蟲 / 業務邏輯 / 記憶體讀取）

### 1-1. `src/models/json_database.py`（~1,457 行）
- 讀取全檔，列出所有 `def` 方法
- 確認每個方法是否呼叫 `_go_db_*` 函式
- 確認 `_GO_DB_AVAILABLE` 條件分支：false 分支是否已換成 `raise RuntimeError`
- 特別確認：`get_video`, `add_video`, `delete_video`, `update_video`, `get_actress_info`, backup 系列, stats 系列

### 1-2. `src/models/incremental_json_database.py`（~453 行）
- 讀取全檔，列出所有 `def` 方法
- 確認 journal 相關方法（`write_journal`, `compact`, `compact_if_needed`）是否委派
- 確認 `get_video`, `update_video` 是否委派

### 1-3. `src/scrapers/cache_manager.py`（~641 行）
- 讀取全檔
- 確認 Phase 8B 移除的 5 個方法是否乾淨（無殘留 Python 邏輯）
- 列出仍在 Python 的快取方法並評估是否應遷移

### 1-4. `src/services/go_bridge.py`（facade）
- 確認 facade 是否正確轉發到 go_api/* 函式
- 確認無直接 subprocess 呼叫殘留

### 1-5. `src/models/extractor.py`
- 確認 `_extract_code_python()` 是否已刪除
- 確認 Go 不可用時回傳 `None`（允許，因為提取失敗不是致命錯誤）

### 1-6. `src/models/studio.py`
- 確認 `_identify_studio_python()` 是否已刪除

### 1-7. `src/utils/scanner.py`
- 確認 Python `rglob` fallback 是否已刪除

### 1-8. `src/utils/file_mover.py`
- 確認 `shutil.move` fallback 是否已刪除

### 1-9. `src/services/go_api/db.py`（~476 行）
- 確認所有橋接函式的輸入/輸出格式
- 確認錯誤處理方式（`GoBridgeError` 是否正確傳遞）

### 1-10. `src/services/go_api/cache.py`
- 確認 `cache_get_stats`, `cache_prune`, `cache_clear` 實作

### 1-11. `src/services/go_api/scan.py`, `move.py`, `identify.py`
- 確認各函式完整性

---

## 任務二：Go 端完整性確認

> 對每個 Go 方法確認：
> - 方法是否存在
> - JSON 輸出結構是否清晰
> - 錯誤是否輸出到 stderr（而非 stdout）
> - 是否有對應單元測試

### 2-1. `pkg/database/jsondb.go`（~955 行）
確認以下方法存在且輸出 JSON：
- `GetVideo`, `UpdateVideo`, `DeleteVideo`, `ListVideos`
- `GetActress`, `UpsertActress`, `DeleteActress`, `ListActresses`
- `GetActressStats`, `GetStudioStats`
- `BackupCreate`, `BackupRestore`, `BackupList`, `BackupCleanup`
- `CompactJournal`, `GetStats`

### 2-2. `cmd/scanner/db_cmd.go`（~351 行）
確認 CLI 子命令對應：
- `db get <code>`
- `db update <code> -data <json>`
- `db delete <code>`
- `db list`
- `db actress-get <name>`
- `db actress-update <name>`
- `db actress-delete <name>`
- `db actress-list`
- `db stats --actress`, `db stats --studio`
- `db backup-create`, `db backup-restore`, `db backup-list`, `db backup-cleanup`

### 2-3. `cmd/scanner/cache_cmd.go`（~160 行）
確認子命令：`cache get`, `cache set`, `cache delete`, `cache stats`, `cache prune`, `cache clear`

### 2-4. `cmd/scanner/identify_cmd.go`（~94 行）
確認子命令：`identify <code>`, `identify batch`, `identify list`

### 2-5. `cmd/scanner/main.go`
確認所有命令路由完整（`scan`, `move`, `db`, `cache`, `identify`, `history`）

### 2-6. `pkg/extractor/extractor.go`
確認 `ExtractCode()` 函式存在且有完整正則模式

### 2-7. `pkg/mover/` 系列
確認 `Move()`, `BatchMove()`, `Rollback()`, `ListOperations()` 存在

### 2-8. `pkg/studio/identifier.go`
確認 `Identify()`, `IdentifyBatch()`, `ListStudios()` 存在

### 2-9. `pkg/cache/cache.go`
確認 `Get()`, `Set()`, `Delete()`, `GetStats()`, `Prune()`, `Clear()` 存在

### 2-10. 單元測試覆蓋確認
- `pkg/database/jsondb_test.go` — 是否涵蓋 actress/backup/stats
- `pkg/cache/cache_test.go` — 是否涵蓋 9 個測試
- `pkg/extractor/extractor_test.go`
- `pkg/mover/mover_test.go`
- `pkg/studio/identifier_test.go`

---

## 任務三：下一階段可遷移項目評估

對以下項目評估「是否值得遷移至 Go」：

| 候選項目 | 檔案 | 評估點 |
|---------|------|--------|
| Journal 讀寫 | `incremental_json_database.py` | 是否已有 Go compact 對應？Python journal 是否仍在運作？ |
| 批次搜尋快取寫入 | `cache_manager.py` | Go cache 是否能直接替代 Python file 快取？ |
| 統計計算 `_compute_*_internal` | `json_database.py` | 這些方法仍在 Python，Go 已有 stats API，是否可刪除？ |
| 驗證邏輯 `_validate_*` | `json_database.py` | 是否值得移到 Go？ |
| 進度追蹤 | `src/utils/progress_tracker.py` | 純 Python 計算，Go 加速意義不大 |

**不應遷移的項目（列出原因）：**
- `web_searcher.py`, `avwiki_scraper.py`, `javdb_scraper.py` — 網路爬蟲，依賴 BeautifulSoup/requests
- `main_gui.py`, `preferences_dialog.py` — GUI，Tkinter 是 Python 專屬
- `classifier_core.py` — 業務決策邏輯，複雜度高，遷移收益低
- `config.py` — config.ini 解析，輕量，無需遷移

---

## 任務四：產出審閱報告

**輸出檔案**: `openclaw-review/OPENCLAW_AUDIT_2026-04-06.md`

格式要求：

```markdown
# OpenClaw Migration Audit — 2026-04-06

## 審閱摘要
- 完全委派 Go 的方法數：N
- 有 Python fallback 的方法數：N（合法 M 個 / 違規 K 個）
- 尚未委派的方法數：N
- 建議下一步遷移項目數：N

## 逐檔審閱
### src/models/json_database.py
| 方法名 | 狀態 | 說明 |
|--------|------|------|
| get_video | ✅ | 呼叫 _go_db_get_video，失敗 raise RuntimeError |
| ...

（其餘檔案同格式）

## Go 端完整性確認
### 已確認完整的方法：
...
### 發現缺失或問題：
...

## 下一階段建議（Phase 9+）
### 建議遷移：
...
### 不應遷移（原因）：
...

## 程式碼品質問題
...
```

---

## 執行順序

1. **先讀 Python 端**（任務一），逐方法標記
2. **再讀 Go 端**（任務二），對照確認
3. **評估 Phase 9+**（任務三）
4. **寫出報告**（任務四）

> ⚠️ 重要：每個 Python 方法委派的 Go CLI 子命令必須真的存在於 `cmd/scanner/*.go`，不能假設「已有 Go 函式就代表 CLI 有對應命令」。請分別確認 Go pkg 層和 CLI 層。

---

**審閱報告輸出位置**: `C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration\openclaw-review\OPENCLAW_AUDIT_2026-04-06.md`
