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

---

## 🔄 Current Status

**Phase 6A 進行中。** Task 6A-1 完成（extractor.py Python fallback 已移除）。下一個任務：Task 6A-2（studio.py）。

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
