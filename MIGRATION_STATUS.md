# Migration Status

> **Managed by GitHub Actions workflow.**
> Do NOT manually edit the completed sections — the AI workflow updates this file after each task.
> Human reviewers: check this file to see current migration progress.

---

## ✅ Completed Tasks

### Phase 1 — Runner injection for go_api layer

- [x] `src/services/go_api/db.py` — runner keyword injection added to all public functions
- [x] `src/services/go_api/identify.py` — runner keyword injection added to all public functions
- [x] `tests/test_go_api_runner_injection.py` — 33 tests covering db.py + identify.py
- [x] `tests/test_go_api_move_scan_injection.py` — runner injection tests for move.py + scan.py
- [x] `src/services/go_api/move.py` — `_get_runner()` helper + runner injection in all public functions
- [x] `src/services/go_api/scan.py` — `_get_runner()` + `_get_context()` helpers; refactored `scan_directory()`

### Phase 2 — Replace Python reimplementations with Go delegation

- [x] `src/models/extractor.py` — `extract_code()` delegates to Go (`_extract_code_via_go()`) with Python fallback
- [x] `src/models/studio.py` — `identify_studio()` delegates to Go (`_identify_studio_via_go()`) with Python fallback

### Phase 3 — Thin wrapper cleanup

- [x] `src/models/go_accelerated_db.py` — removed dead `_go_bridge` attr; moved Go API imports to module level; simplified `_check_go_availability`
- [x] `src/models/go_accelerated_studio.py` — removed dead `_go_bridge` attr; moved Go API imports to module level; added `_GO_API_IMPORT_OK` guard; simplified `_check_go_availability`

### Phase 6A — 薄適配層 Python fallback 移除（低風險）

- [x] Task 6A-1: `src/models/extractor.py` — deleted `_extract_code_python()`, `_validate_code()`, `_should_skip_file()`, `__init__`, and all Python-only attributes; `extract_code()` now calls `_extract_code_via_go()` directly; updated `tests/test_extractor.py` to remove tests of deleted methods
- [x] Task 6A-2: `src/models/studio.py` — deleted `_identify_studio_python()`; Go 不可用時自訂規則檔走 `code_to_studio` 前綴查詢；預設 studios.json 走 Go
- [x] Task 6A-3: `src/utils/scanner.py` — deleted Python `rglob` fallback; Go 不可用時 `raise RuntimeError`
- [x] Task 6A-4: `src/utils/file_mover.py` — deleted `shutil.move` fallback; Go 不可用時 raise RuntimeError

### Phase 6B — 快取層清除

- [x] Task 6B-1: `src/scrapers/cache_manager.py` — deleted `_set_python/_get_python/_delete_python` (~175 行); Go 不可用時 no-op

### Phase 6C — 冗餘包裝類別刪除

- [x] Task 6C-1: `src/models/go_accelerated_db.py` — 整個刪除 (258 行)；刪除對應測試
- [x] Task 6C-2: `src/models/go_accelerated_studio.py` — 整個刪除 (217 行)；刪除對應測試

### Phase 6D — 核心資料庫模組瘦身

- [x] Task 6D-1: `src/models/incremental_json_database.py` — deleted `_update_video_python()` / `_get_video_info_python()`; Go 不可用時 raise RuntimeError；記憶體讀取改直接呼叫 `base_db.get_video_info()`
- [x] Task 6D-2: `src/models/json_database.py` — deleted `_add_or_update_video_python` / `_get_video_info_python` / `_get_all_videos_python` / `_delete_video_python` (~280 行); 寫入 Go 不可用時 raise RuntimeError；讀取從記憶體 cache 返回

---

### Phase 10 — Go availability guards 全移除

- [x] Task 10-1: `src/models/json_database.py` — 移除 `_GO_DB_AVAILABLE` flag、`_check_go_db_available()` 方法、13 個方法的 `if self._GO_DB_AVAILABLE:` guard；改為直接委派 Go
- [x] Task 10-2: `src/models/incremental_json_database.py` — 移除 `_GO_DB_AVAILABLE` 類別屬性、`_check_go_db_available()` 靜態方法、4 個方法的 guard
- [x] Task 10-3: `src/scrapers/cache_manager.py` — 移除 `_GO_CACHE_AVAILABLE` flag、`_check_go_available()` 靜態方法、set/get/delete early-return guard

### Phase 11 — 測試補強 & CI 整合

- [x] Task 11-1: `tests/test_extractor.py` — 補 `489155.com@` site prefix 委派測試、通用 siteRe 測試
- [x] Task 11-2: `.github/workflows/integration-test.yml` — 加入 e2e 整合測試步驟（`go build → pytest tests/integration/`）

### Phase 12 — Python 程式碼進一步精簡

- [x] Task 12-1: `src/services/go_bridge_test.py` → 移至 `tests/test_go_bridge.py`（測試誤放 src/，-592 行 from src）
- [x] Task 12-2: `src/models/json_database.py` — 移除 Python filelock 機制（`_acquire_read_lock`/`_release_locks`/`FileLock`，-88 行）
- [x] Task 12-3: `src/models/incremental_json_database.py` — 移除冗餘 journal dead code（`JournalEntry`/`_replay_journal`/`_append_journal` 等，-60 行）
- [x] Task 12-4: `src/services/classifier_core.py` — 移除 dead code 與重複迭代邏輯（`process_and_search_japanese_sites` 等，-130 行）

---

## 🔄 Current Status

**✅ Phase 12 完成。** src/ Python 程式碼縮減至 15,419 行，276 tests 通過。

### 累計刪減統計

| Phase | 刪除行數 | 說明 |
|-------|---------|------|
| 6A（4 個薄適配層） | ~250 行 | extractor/studio/scanner/file_mover Python fallback |
| 6B（cache_manager） | ~175 行 | _set/get/delete_python() 移除 |
| 6C（2 個整刪檔案） | ~475 行 | go_accelerated_db/studio 整個刪除 |
| 6D（2 個核心 DB 模組） | ~317 行 | json_database/incremental Python fallback |
| 7-8（DB/cache 深度委派） | ~441 行 | actress CRUD / backup / cache 5 方法 |
| 10（guards 全移除） | ~100 行 | _GO_DB_AVAILABLE / _GO_CACHE_AVAILABLE guards |
| 12（進一步精簡） | ~870 行 | filelock / journal dead code / classifier dead code / test 移位 |
| **合計** | **~2,628 行** | 相較 Phase 6 前基準 |

### Phase 5 — JSONDBManager Go 完整委派

- [x] Task 5-1: `pkg/database/jsondb.go` + `cmd/scanner/db_cmd.go` — added `GetAllVideos()` method; extended `db list` with `--full` flag
- [x] Task 5-2: `src/services/go_api/db.py` — added `db_get_all_videos()` function; 4 tests in `tests/test_go_api_db_all_videos.py`
- [x] Task 5-3: `src/models/json_database.py` — added `_GO_DB_API_IMPORT_OK` guard + `_check_go_db_available()`; delegated `get_video_info`, `add_or_update_video`, `delete_video` to Go with Python fallback
- [x] Task 5-4: `src/models/json_database.py` + `tests/test_json_db_go_delegation.py` — `get_all_videos` delegated to Go with Python fallback; 15 tests in 4 classes all pass



### Phase 4A — CacheManager Go core

- [x] Task 4A-1: `pkg/cache/cache.go` — added `Get`/`Set`/`Delete`/`Exists` methods + `CachePayload` struct in `types.go`; 4 new tests added to `cache_test.go`
- [x] Task 4A-2: `cmd/scanner/cache_cmd.go` — added `get`/`set`/`delete` sub-commands with JSON output and base64 value encoding
- [x] Task 4A-3: `src/services/go_api/cache.py` — created thin wrapper with `cache_get`/`cache_set`/`cache_delete` + runner injection; 22 tests in `tests/test_go_api_cache.py`
- [x] Task 4A-4: `src/scrapers/cache_manager.py` — delegate `get()`/`set()`/`delete()` to Go

### Phase 4B — IncrementalJSONDB Go delegation

- [x] Task 4B-1: `src/models/incremental_json_database.py` — delegate `get_video`/`update_video` to `go_api/db.py`

---

## 📝 Notes

- Phase 3 / go_accelerated_db.py (2026-04-05): Removed dead `_go_bridge` instance variable; moved 5 Go API function imports + `GoBridgeError` to module level (replacing repeated inline imports in 6 methods); simplified `_check_go_availability` to skip bridge storage. All 191 tests pass.
- Phase 3 / go_accelerated_studio.py (2026-04-05): Removed dead `_go_bridge` instance variable; moved `identify_studio` + `identify_studios_batch` Go API imports to module level (replacing 4 inline imports across 4 methods); added `_GO_API_IMPORT_OK` guard; simplified `_check_go_availability`. All 191 tests pass.
- Phase 4A / Task 4A-1 (2026-04-05): Added `CachePayload` struct to `pkg/cache/types.go`; added `hashKey`, `cacheFilePath`, `Set`, `Get`, `Delete`, `Exists` to `pkg/cache/cache.go` (with `crypto/sha256` import); added 4 new tests (`TestCacheGetSetDelete`, `TestCacheExpiry`, `TestCacheGetMissing`, `TestCacheIndexUpdatedOnSet`). All 13 cache tests + full Go pkg suite pass.
- Phase 5 / Task 5-2 (2026-04-05): Added `db_get_all_videos(data_dir, *, runner)` to `src/services/go_api/db.py` — calls `["db", "list", "--full"]`, mirrors `db_list_videos` pattern; created `tests/test_go_api_db_all_videos.py` with 4 tests. All 228 tests pass.
- Phase 6A / Task 6A-1 (2026-04-06): Deleted `_extract_code_python()`, `_validate_code()`, `_should_skip_file()`, `__init__`, and all Python-only attributes (`tech_suffix_pattern`, `skip_prefixes`, `code_patterns`, `supported_formats`) from `src/models/extractor.py` (~130 lines removed). Removed `re`/`Path` imports. `extract_code()` now calls `_extract_code_via_go()` directly (returns `None` if Go unavailable). Updated `tests/test_extractor.py` to remove 2 tests of deleted methods (`test_should_skip_various_formats`, `test_supported_formats`). All 243 tests pass.
