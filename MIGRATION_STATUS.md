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

---

## 🔄 Current Status

**Next task:** Phase 3 — `src/models/go_accelerated_studio.py` thin wrapper cleanup

---

## ⏳ Pending Tasks

### Phase 3 — Thin wrapper cleanup
- [x] `src/models/go_accelerated_db.py` — removed dead `_go_bridge` attr; moved Go API imports to module level; simplified `_check_go_availability`
- [ ] `src/models/go_accelerated_studio.py` — remove redundant methods already covered by `go_api/identify.py`

### Phase 4A — CacheManager Go core
- [ ] Task 4A-1: `pkg/cache/cache.go` — add `Get`/`Set`/`Delete`/`Exists` methods
- [ ] Task 4A-2: `cmd/scanner/cache_cmd.go` — add `get`/`set`/`delete` sub-commands
- [ ] Task 4A-3: `src/services/go_api/cache.py` — create thin wrapper (new file)
- [ ] Task 4A-4: `src/scrapers/cache_manager.py` — delegate `get()`/`set()`/`delete()` to Go

### Phase 4B — IncrementalJSONDB Go delegation
- [ ] Task 4B-1: `src/models/incremental_json_database.py` — delegate `get_video`/`update_video` to `go_api/db.py`

---

## 📝 Notes

- Phase 3 / go_accelerated_db.py (2026-04-05): Removed dead `_go_bridge` instance variable; moved 5 Go API function imports + `GoBridgeError` to module level (replacing repeated inline imports in 6 methods); simplified `_check_go_availability` to skip bridge storage. All 191 tests pass.
