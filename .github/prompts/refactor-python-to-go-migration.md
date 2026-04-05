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
- `src/utils/scanner.py`
- `src/utils/file_mover.py`
- `tests/**`
- `.github/prompts/refactor-python-to-go-migration.md` ← task list (update `[ ]` → `[x] DONE` when task is complete)

# Forbidden scope
- Any file outside the allowed scope
- `src/ui/**`, `src/scrapers/**`, `src/services/classifier_core.py`, `src/services/web_searcher.py`, `src/services/studio_classifier.py`
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
