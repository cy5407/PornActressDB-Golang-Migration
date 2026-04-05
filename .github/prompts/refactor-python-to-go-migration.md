# Goal
Safely advance the Python-to-Go migration in this repository.
Pick the **first incomplete task** from the task list below and complete it.
Do not attempt multiple tasks in one run.

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
- [ ] TODO: `src/models/go_accelerated_db.py` — audit for redundant methods already covered by `go_api/db.py`; remove duplication, keep public interface. **Before editing**: run `grep -n "def " src/models/go_accelerated_db.py` to list all methods, then `grep -rn "go_accelerated_db" src/ tests/` to find all call sites. Only remove methods with ZERO call sites outside the file itself. **Verify**: run `python -m pytest tests/ -v --tb=short` — all tests must pass. Run `git diff HEAD -- src/models/go_accelerated_db.py` — must show non-empty diff before marking DONE.
- [ ] TODO: `src/models/go_accelerated_studio.py` — audit for redundant methods already covered by `go_api/identify.py`; remove duplication, keep public interface. **Before editing**: run `grep -n "def " src/models/go_accelerated_studio.py` and `grep -rn "go_accelerated_studio" src/ tests/` to find call sites. Only remove methods with ZERO external call sites. **Verify**: run `python -m pytest tests/ -v --tb=short` — all tests must pass. Run `git diff HEAD -- src/models/go_accelerated_studio.py` — must show non-empty diff before marking DONE.

## Phase 4A — CacheManager Go core
> Detailed plan: `docs/superpowers/plans/2026-04-05-phase4-cache-and-incremental-db-go-migration.md`

- [ ] TODO: **Task 4A-1** — `pkg/cache/cache.go` + `pkg/cache/types.go` — add `CachePayload` struct and `Get(key string) ([]byte, bool, error)`, `Set(key string, value []byte, ttlHours int) error`, `Delete(key string) error`, `Exists(key string) bool` methods. Key is hashed with SHA256 (first 2 chars = subdir, `.json` extension). TTL: `ttlHours<=0` means immediately expired (never returned). Disk format mirrors Python: `{"version":1,"created_at":<unix>,"ttl_seconds":<n>,"compressed":false,"data":<base64>}`. Add tests in `pkg/cache/cache_test.go`. **Before coding**: run `grep -n "func " pkg/cache/cache.go` to see existing methods. **Build**: `go build ./pkg/cache`. **Verify**: `go test ./pkg/cache -v` — all tests must pass. `git diff HEAD -- pkg/cache/cache.go` must be non-empty.

- [ ] TODO: **Task 4A-2** — `cmd/scanner/cache_cmd.go` — add `get <key>`, `set <key> <value> [--ttl-hours N]`, `delete <key>` sub-commands to the `cache` command. Output must be JSON (`{"success":true,"value":"..."}` or `{"success":false,"error":"..."}`). Wire into `main.go` dispatch. **Before coding**: run `grep -n "case" cmd/scanner/main.go | head -20` to see dispatch pattern. **Build**: `go build -o classifier_test.exe ./cmd/scanner && rm -f classifier_test.exe`. **Verify**: `go test ./... -v` — all tests must pass. `git diff HEAD -- cmd/scanner/cache_cmd.go` must be non-empty.

- [ ] TODO: **Task 4A-3** — `src/services/go_api/cache.py` (create new file) — thin wrapper over `classifier.exe cache get/set/delete`. Functions: `cache_get(key, runner=None) -> Optional[bytes]`, `cache_set(key, value: bytes, ttl_hours: int = 24, runner=None) -> bool`, `cache_delete(key, runner=None) -> bool`. Follow runner-injection pattern from `go_api/db.py`. Create `tests/test_go_api_cache.py` with mock-runner tests. **Before coding**: read `src/services/go_api/db.py` lines 1-60 to see pattern. **Verify**: `python -m pytest tests/test_go_api_cache.py -v` — all tests must pass. `git diff HEAD -- src/services/go_api/cache.py` must be non-empty.

- [ ] TODO: **Task 4A-4** — `src/scrapers/cache_manager.py` — delegate `get()`, `set()`, `delete()` to `go_api/cache.py` with Python fallback. Rename existing body to `_get_python()`, `_set_python()`, `_delete_python()`. Add `_GO_CACHE_AVAILABLE = GoBridge().is_available` flag at class level. Keep public signature identical. **Before coding**: run `grep -n "def " src/scrapers/cache_manager.py | head -30` to list methods, then `grep -rn "cache_manager" src/ tests/ | head -20` to see call sites. **Verify**: `python -m pytest tests/ -v --tb=short` — all tests must pass. `git diff HEAD -- src/scrapers/cache_manager.py` must be non-empty.

## Phase 4B — IncrementalJSONDB Go delegation
> Detailed plan: `docs/superpowers/plans/2026-04-05-phase4-cache-and-incremental-db-go-migration.md`

- [ ] TODO: **Task 4B-1** — `src/models/incremental_json_database.py` — delegate `get_video(code)` and `update_video(code, data)` to `go_api/db.py` (`db_get_video` / `db_update_video`). Add `_GO_DB_AVAILABLE: bool` class attribute (set via `GoBridge().is_available`). Rename existing bodies to `_get_video_python()` / `_update_video_python()`. Keep public signature + return types identical. Create `tests/test_incremental_db_go_delegation.py` with mock-runner tests verifying delegation path and Python fallback. **Before coding**: run `grep -n "def " src/models/incremental_json_database.py` to list methods, then `grep -rn "incremental_json_database\|IncrementalJSONDB" src/ tests/ | head -20`. **Verify**: `python -m pytest tests/ -v --tb=short` — all tests must pass. `git diff HEAD -- src/models/incremental_json_database.py` must be non-empty.

# Allowed scope
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
- `src/utils/scanner.py`
- `src/utils/file_mover.py`
- `src/scrapers/cache_manager.py`
- `tests/**`
- `.github/prompts/refactor-python-to-go-migration.md` ← task list (update `[ ]` → `[x] DONE` when task is complete)

# Forbidden scope
- Any file outside the allowed scope
- `src/ui/**`, `src/services/classifier_core.py`, `src/services/web_searcher.py`, `src/services/studio_classifier.py`
- `src/scrapers/**` except `src/scrapers/cache_manager.py`
- `.github/workflows/**`, `data/**`, `logs/**`
- Commits, pushes, PR creation, branch changes, or network access

# Safety rules
- Prefer moving behavior from Python wrappers into existing Go services or CLI-facing APIs.
- Keep GUI behavior, JSON output contracts, and public Python call sites compatible.
- Always add Python fallback when delegating to Go (check `GoBridge().is_available`).
- Preserve Python fallback behavior unless the Go path is already the established primary path.
- Prefer one cohesive migration step only.
- If no clearly safe migration step is available, make no changes.

# Validation
- Run targeted tests for touched Go packages.
- Run `go test ./pkg/... -v` after changes.
- Run `python -m pytest tests/ -v` after any Python changes.
- All tests must pass before considering the task complete.

# Completion
- Stop once one task from the task list is complete and all tests pass.
- **CRITICAL: Before marking any task `[x] DONE`, you MUST verify the target source file was actually modified:**
  - Run `git diff HEAD -- <target_file>` and confirm it shows real code changes.
  - If the diff is empty, the task is NOT done — do the actual work first.
  - Never mark a task DONE based on assumptions or reading alone.
- Update the task list by marking the completed task as `[x] DONE` only after verification.
- Do not modify files outside the allowed scope.
- Do not leave partial edits behind if validation fails.
