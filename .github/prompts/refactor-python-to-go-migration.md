# Goal
Safely advance the Python-to-Go migration in this repository.
Pick the **first incomplete task** from the task list below and complete it.
Do not attempt multiple tasks in one run.

# Progress tracking (read this FIRST)
**Before picking a task**, read `MIGRATION_STATUS.md` to see which tasks are already completed.
Skip any task that already appears in the `## ✅ Completed Tasks` section of that file.
Do NOT rely on the `[x] DONE` markers in this prompt file — they may be stale.
The source of truth is `MIGRATION_STATUS.md`.

# Task list (execute in order, skip already-done ones)

## Phase 1 — Runner injection for go_api layer (bridge decoupling)
- [x] DONE: `src/services/go_api/db.py` — add `runner` keyword injection to all public functions
- [x] DONE: `src/services/go_api/identify.py` — add `runner` keyword injection to all public functions
- [x] DONE: `tests/test_go_api_runner_injection.py` — 33 tests covering db.py + identify.py
- [x] DONE: `tests/test_go_api_move_scan_injection.py` — add runner injection tests for `go_api/move.py` and `go_api/scan.py` (mirror the pattern in test_go_api_runner_injection.py)
- [x] DONE: `src/services/go_api/move.py` — added `_get_runner()` helper; runner injection in all public functions
- [x] DONE: `src/services/go_api/scan.py` — added `_get_runner()` + `_get_context()` helpers; refactored `scan_directory()`

## Phase 2 — Replace Python reimplementations with Go delegation
- [x] DONE: `src/models/extractor.py` — `extract_code()` delegates to `_extract_code_via_go()` with `_extract_code_python()` fallback; `cmd/scanner/main.go` extended with `-extract` flag
- [x] DONE: `src/models/studio.py` — `identify_studio()` delegates to `_identify_studio_via_go()` with `_identify_studio_python()` fallback; skips Go when using custom rules_file

## Phase 3 — Thin wrapper cleanup
- [x] DONE: `src/models/go_accelerated_db.py` — removed dead `_go_bridge` attr; moved Go API imports to module level; simplified `_check_go_availability`
- [x] DONE: `src/models/go_accelerated_studio.py` — removed dead `_go_bridge` attr; moved Go API imports to module level; added `_GO_API_IMPORT_OK` guard; simplified `_check_go_availability`

## Phase 4A — CacheManager Go core
> Detailed plan: `docs/superpowers/plans/2026-04-05-phase4-cache-and-incremental-db-go-migration.md`

- [ ] TODO: **Task 4A-1** — `pkg/cache/cache.go` + `pkg/cache/types.go` — add `CachePayload` struct and `Get(key string) ([]byte, bool, error)`, `Set(key string, value []byte, ttlHours int) error`, `Delete(key string) error`, `Exists(key string) bool` methods. Key is hashed with SHA256 (first 2 chars = subdir, `.json` extension). TTL: `ttlHours<=0` means immediately expired (never returned). Disk format mirrors Python: `{"version":1,"created_at":<unix>,"ttl_seconds":<n>,"compressed":false,"data":<base64>}`. Add tests in `pkg/cache/cache_test.go`. **Before coding**: run `grep -n "func " pkg/cache/cache.go` to see existing methods. **Build**: `go build ./pkg/cache`. **Verify**: `go test ./pkg/cache -v` — all tests must pass. `git diff HEAD -- pkg/cache/cache.go` must be non-empty.

- [ ] TODO: **Task 4A-2** — `cmd/scanner/cache_cmd.go` — add `get <key>`, `set <key> <value> [--ttl-hours N]`, `delete <key>` sub-commands to the `cache` command. Output must be JSON (`{"success":true,"value":"..."}` or `{"success":false,"error":"..."}`). Wire into `main.go` dispatch. **Before coding**: run `grep -n "case" cmd/scanner/main.go | head -20` to see dispatch pattern. **Build**: `go build -o classifier_test.exe ./cmd/scanner && rm -f classifier_test.exe`. **Verify**: `go test ./... -v` — all tests must pass. `git diff HEAD -- cmd/scanner/cache_cmd.go` must be non-empty.

- [ ] TODO: **Task 4A-3** — `src/services/go_api/cache.py` (create new file) — thin wrapper over `classifier.exe cache get/set/delete`. Functions: `cache_get(key, runner=None) -> Optional[bytes]`, `cache_set(key, value: bytes, ttl_hours: int = 24, runner=None) -> bool`, `cache_delete(key, runner=None) -> bool`. Follow runner-injection pattern from `go_api/db.py`. Create `tests/test_go_api_cache.py` with mock-runner tests. **Before coding**: read `src/services/go_api/db.py` lines 1-60 to see pattern. **Verify**: `python -m pytest tests/test_go_api_cache.py -v` — all tests must pass. `git diff HEAD -- src/services/go_api/cache.py` must be non-empty.

- [ ] TODO: **Task 4A-4** — `src/scrapers/cache_manager.py` — delegate `get()`, `set()`, `delete()` to `go_api/cache.py` with Python fallback. Rename existing body to `_get_python()`, `_set_python()`, `_delete_python()`. Add `_GO_CACHE_AVAILABLE = GoBridge().is_available` flag at class level. Keep public signature identical. **Before coding**: run `grep -n "def " src/scrapers/cache_manager.py | head -30` to list methods, then `grep -rn "cache_manager" src/ tests/ | head -20` to see call sites. **Verify**: `python -m pytest tests/ -v --tb=short` — all tests must pass. `git diff HEAD -- src/scrapers/cache_manager.py` must be non-empty.

## Phase 4B — IncrementalJSONDB Go delegation
> Detailed plan: `docs/superpowers/plans/2026-04-05-phase4-cache-and-incremental-db-go-migration.md`

- [ ] TODO: **Task 4B-1** — `src/models/incremental_json_database.py` — delegate `get_video(code)` and `update_video(code, data)` to `go_api/db.py` (`db_get_video` / `db_update_video`). Add `_GO_DB_AVAILABLE: bool` class attribute (set via `GoBridge().is_available`). Rename existing bodies to `_get_video_python()` / `_update_video_python()`. Keep public signature + return types identical. Create `tests/test_incremental_db_go_delegation.py` with mock-runner tests verifying delegation path and Python fallback. **Before coding**: run `grep -n "def " src/models/incremental_json_database.py` to list methods, then `grep -rn "incremental_json_database\|IncrementalJSONDB" src/ tests/ | head -20`. **Verify**: `python -m pytest tests/ -v --tb=short` — all tests must pass. `git diff HEAD -- src/models/incremental_json_database.py` must be non-empty.

## Phase 5 — JSONDBManager Go 完整委派
> Detailed plan: `docs/superpowers/plans/2026-04-05-phase5-json-database-go-delegation.md`

- [ ] TODO: **Task 5-1** — `pkg/database/jsondb.go` + `cmd/scanner/db_cmd.go` — add `GetAllVideos() ([]*VideoData, error)` method to `JSONDatabase` (iterate `db.root.Videos` under RLock after merging journal); extend `db list` sub-command in `db_cmd.go` with `--full` flag: when set, call `GetAllVideos()` and `outputJSON(videos)`, otherwise call existing `ListVideos()`. **Before coding**: run `grep -n "func.*JSONDatabase" pkg/database/jsondb.go` and `grep -n "case \"list\"" cmd/scanner/db_cmd.go`. **Build**: `go build -o classifier.exe ./cmd/scanner`. **Verify**: `go test ./pkg/... -v` — all pass; smoke-test: `./classifier.exe db list --full -data-dir data/json_db` returns JSON array. `git diff HEAD -- pkg/database/jsondb.go cmd/scanner/db_cmd.go` must be non-empty.

- [ ] TODO: **Task 5-2** — `src/services/go_api/db.py` — append `db_get_all_videos(data_dir="data/json_db", *, runner=None) -> list[dict]` function that calls `["db", "list", "--full"]` (with optional `-data-dir`), parses JSON, returns list or `[]` on error. Follow the exact same runner-injection and error-handling pattern as `db_list_videos`. Create `tests/test_go_api_db_all_videos.py` with 3 mock-runner tests: (1) returns list and calls correct command, (2) default data-dir omits `-data-dir` flag, (3) returns `[]` on `GoBridgeError`. **Before coding**: read `src/services/go_api/db.py` lines 130-175 to see `db_list_videos` pattern. **Verify**: `python -m pytest tests/test_go_api_db_all_videos.py -v` — 3 tests pass; `python -m pytest tests/ -q` — no regressions. `git diff HEAD -- src/services/go_api/db.py` must be non-empty.

- [ ] TODO: **Task 5-3** — `src/models/json_database.py` — (a) add module-level import guard for `db_get_video`, `db_update_video`, `db_delete_video`, `db_get_all_videos` from `services.go_api.db`, setting `_GO_DB_API_IMPORT_OK`; (b) add `_check_go_db_available()` private method using `get_bridge().is_available`; (c) set `self._GO_DB_AVAILABLE = self._check_go_db_available()` in `__init__`; (d) rename `get_video_info` → `_get_video_info_python`, add new `get_video_info` that tries `db_get_video(code, data_dir=str(self.data_dir))` first; (e) rename `add_or_update_video` → `_add_or_update_video_python`, add new `add_or_update_video` that tries `db_update_video(video_code, merged_dict, data_dir=...)` then syncs memory cache; (f) rename `delete_video` → `_delete_video_python`, add new `delete_video` that tries `db_delete_video(code, data_dir=...)` then cleans up `self.data["links"]`. All new public methods fall back to the `_*_python` helper on exception. **Before coding**: run `grep -n "def " src/models/json_database.py | head -30` and `grep -rn "JSONDBManager\|json_database" src/ tests/ | head -20`. **Verify**: `python -m pytest tests/ -v --tb=short` — all tests pass. `git diff HEAD -- src/models/json_database.py` must be non-empty.

- [ ] TODO: **Task 5-4** — `src/models/json_database.py` + `tests/test_json_db_go_delegation.py` — (a) rename `get_all_videos` → `_get_all_videos_python`, add new `get_all_videos(filter_dict=None)` that tries `db_get_all_videos(data_dir=str(self.data_dir))`, ensures each video has `code` field, applies `self._apply_video_filters` if `filter_dict` is set, falls back to `_get_all_videos_python(filter_dict)` on exception; (b) create `tests/test_json_db_go_delegation.py` with 15 tests as specified in `docs/superpowers/plans/2026-04-05-phase5-json-database-go-delegation.md` Task 4 Step 1 (4 classes: `TestGetVideoInfoDelegation`, `TestAddOrUpdateVideoDelegation`, `TestDeleteVideoDelegation`, `TestGetAllVideosDelegation`, 3-4 tests each). **Before coding**: read `src/models/json_database.py` lines 885-934 for original `get_all_videos` body. **Verify**: `python -m pytest tests/test_json_db_go_delegation.py -v` — 15 tests pass; `python -m pytest tests/ -q` — no regressions. `git diff HEAD -- src/models/json_database.py` must be non-empty.

## Phase 6A — 薄適配層 Python fallback 移除（低風險）

> **Phase 6 policy**: Go CLI has been stable through Phase 1-5 (243 tests passing). Phase 6 **removes** Python fallback implementations. Do NOT add new Python fallbacks in this phase.

- [ ] TODO: **Task 6A-1** — `src/models/extractor.py` — delete the `_extract_code_python()` method and all attributes only used by it (`tech_suffix_pattern`, `skip_prefixes`, `code_patterns`, `supported_formats`); also delete `_validate_code()`, `_should_skip_file()`; simplify `extract_code()` to call `_extract_code_via_go()` and return `None` if Go is unavailable (no Python path). **Before editing**: run `grep -n "def \|self\." src/models/extractor.py | head -40` and `grep -rn "UnifiedCodeExtractor\|extractor\.py" src/ tests/ | head -20`. **Verify**: `python -m pytest tests/test_extractor.py tests/test_code_review_regressions.py -v --tb=short` — all tests must pass. `git diff HEAD -- src/models/extractor.py` must show deletions. Estimated removal: ~120 lines.

- [ ] TODO: **Task 6A-2** — `src/models/studio.py` — delete the `_identify_studio_python()` method and all Python-only helper methods/data (regex patterns, studio lists used only by Python path); simplify `identify_studio()` to call `_identify_studio_via_go()` and return `"UNKNOWN"` if Go unavailable. **Before editing**: run `grep -n "def " src/models/studio.py` and `grep -rn "StudioIdentifier\|studio\.py" src/ tests/ | head -20`. **Verify**: `python -m pytest tests/test_studio.py tests/test_studio_integration.py -v --tb=short` — all tests must pass. `git diff HEAD -- src/models/studio.py` must show deletions.

- [ ] TODO: **Task 6A-3** — `src/utils/scanner.py` — delete the Python `rglob` fallback block inside `scan_directory()` (the `logger.warning("使用 Python 降級掃描...")` branch and the lines after it); when `self.go_bridge` is unavailable, raise `RuntimeError("Go CLI 不可用，無法掃描目錄")` instead. **Before editing**: run `grep -n "def \|rglob\|warning" src/utils/scanner.py`. **Verify**: `python -m pytest tests/test_scanner_integration.py -v --tb=short` — all tests must pass. `git diff HEAD -- src/utils/scanner.py` must show deletions.

- [ ] TODO: **Task 6A-4** — `src/utils/file_mover.py` — delete all `shutil.move` fallback blocks in `move_file()`, `move_dir()`, and `batch_move()`; when `self.go_bridge` is unavailable, return `{"success": False, "error": "Go CLI 不可用，無法搬移檔案", ...}` with appropriate keys instead of using shutil. **Before editing**: run `grep -n "def \|shutil\|warning" src/utils/file_mover.py`. **Verify**: `python -m pytest tests/ -v --tb=short` — all tests must pass. `git diff HEAD -- src/utils/file_mover.py` must show deletions.

## Phase 6B — 快取層 Python fallback 移除

- [ ] TODO: **Task 6B-1** — `src/scrapers/cache_manager.py` — delete `_get_python()`, `_set_python()`, `_delete_python()` methods and all file I/O logic in them; when Go is unavailable, `get()` returns `None`, `set()` / `delete()` are no-ops (return silently). **Before editing**: run `grep -n "def " src/scrapers/cache_manager.py` and `grep -rn "cache_manager\|CacheManager" src/ tests/ | head -20`. **Verify**: `python -m pytest tests/test_cache_manager_security.py tests/test_go_api_cache.py -v --tb=short` — all must pass. `git diff HEAD -- src/scrapers/cache_manager.py` must show deletions.

## Phase 6C — 冗餘包裝類別整檔刪除

- [ ] TODO: **Task 6C-1** — `src/models/go_accelerated_db.py` + `tests/test_go_accelerated_db.py` — **Step 1**: run `grep -rn "GoAcceleratedDB\|go_accelerated_db" src/ tests/ scripts/ tools/ *.py` (NOT inside the file itself) to confirm there are zero production callers outside of test files. **Step 2**: if zero production callers confirmed, delete `src/models/go_accelerated_db.py` entirely; rewrite `tests/test_go_accelerated_db.py` to test `go_api/db.py` functions directly (mock runner). **Verify**: `python -m pytest tests/ -v --tb=short` — all tests must pass. `git status` must show `src/models/go_accelerated_db.py` as deleted.

- [ ] TODO: **Task 6C-2** — `src/models/go_accelerated_studio.py` + `tests/test_studio_integration.py` — same process as 6C-1: confirm zero production callers outside tests, then delete `src/models/go_accelerated_studio.py`; update `tests/test_studio_integration.py` to test `go_api/identify.py` directly. **Verify**: `python -m pytest tests/ -v --tb=short` — all tests must pass.

## Phase 6D — 核心資料庫模組大幅瘦身

- [ ] TODO: **Task 6D-1** — `src/models/incremental_json_database.py` — delete `_get_video_python()`, `_update_video_python()`, and all Python journal read/write helper methods that are only reachable from those paths; the public `get_video()` and `update_video()` methods should call Go and raise `RuntimeError` if Go is unavailable (remove the fallback branch). Keep `compact_if_needed()`, `compact()`, `get_stats()`, and `get_all_videos()`. **Before editing**: run `grep -n "def " src/models/incremental_json_database.py`. **Verify**: `python -m pytest tests/test_incremental_db.py tests/test_incremental_db_go_delegation.py -v --tb=short` — all tests must pass. `git diff HEAD -- src/models/incremental_json_database.py` must show substantial deletions (>100 lines).

- [ ] TODO: **Task 6D-2** — `src/models/json_database.py` — delete `_get_video_info_python()`, `_add_or_update_video_python()`, `_delete_video_python()`, `_get_all_videos_python()` and all helper methods only reachable from those paths; the public `get_video_info()`, `add_or_update_video()`, `delete_video()`, `get_all_videos()` should call Go and raise `RuntimeError` on Go failure. **Before editing**: run `grep -n "def _.*python\|def get_video\|def add_or\|def delete_video\|def get_all" src/models/json_database.py | head -30`. **Verify**: `python -m pytest tests/test_json_database.py tests/test_json_db_go_delegation.py -v --tb=short` — all tests must pass. `git diff HEAD -- src/models/json_database.py` must show substantial deletions (>400 lines).
- `pkg/**`
- `cmd/scanner/**`
- `src/services/go_api/**`
- `src/services/go_bridge.py`
- `src/services/go_runner.py`
- `src/models/go_accelerated_db.py`
- `src/models/go_accelerated_studio.py`
- `src/models/extractor.py`
- `src/models/studio.py`
- `src/models/incremental_json_database.py`
- `src/models/json_database.py`
- `src/utils/scanner.py`
- `src/utils/file_mover.py`
- `src/scrapers/cache_manager.py`
- `tests/**`
- `MIGRATION_STATUS.md` ← progress tracker (append completed task here when done)

# Forbidden scope
- Any file outside the allowed scope
- `src/ui/**`, `src/services/classifier_core.py`, `src/services/web_searcher.py`, `src/services/studio_classifier.py`
- `src/scrapers/**` except `src/scrapers/cache_manager.py`
- `.github/workflows/**`, `data/**`, `logs/**`
- Commits, pushes, PR creation, branch changes, or network access

# Safety rules
- **Phase 6 context**: Go CLI is proven stable (243 tests passing). Phase 6 tasks REMOVE Python fallback code — do NOT re-add fallbacks.
- For Phase 1-5 tasks (already done): always add Python fallback when delegating to Go.
- Keep GUI behavior, JSON output contracts, and public Python call sites compatible.
- Prefer one cohesive migration step only.
- If no clearly safe migration step is available, make no changes.

# Validation
- Run targeted tests for touched Go packages.
- Run `go test ./pkg/... -v` after changes.
- Run `python -m pytest tests/ -v` after any Python changes.
- All tests must pass before considering the task complete.

# Completion
- Stop once one task from the task list is complete and all tests pass.
- **CRITICAL: Before marking a task complete, you MUST verify the target source file was actually modified:**
  - Run `git diff HEAD -- <target_file>` and confirm it shows real code changes.
  - If the diff is empty, the task is NOT done — do the actual work first.
  - Never mark a task DONE based on assumptions or reading alone.
- When the task is verified complete:
  1. Move it from `## ⏳ Pending Tasks` to `## ✅ Completed Tasks` in `MIGRATION_STATUS.md`.
  2. Update the `## 🔄 Current Status` section in `MIGRATION_STATUS.md` to name the next task.
  3. Optionally append a brief run note to the `## 📝 Notes` section.
  4. **Do NOT modify `.github/prompts/refactor-python-to-go-migration.md`** — it is read-only.
- Do not modify files outside the allowed scope.
- Do not leave partial edits behind if validation fails.
