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
- [ ] TODO: `src/services/go_api/move.py` — add `runner` keyword injection to all public functions (mirror db.py pattern)
- [ ] TODO: `src/services/go_api/scan.py` — add `runner` keyword injection to all public functions

## Phase 2 — Replace Python reimplementations with Go delegation
- [ ] TODO: `src/models/extractor.py` — `UnifiedCodeExtractor.extract_code()` currently does Python regex; delegate to `go_api/scan.py` identify logic (with Python fallback if Go unavailable)
- [ ] TODO: `src/models/studio.py` — `StudioIdentifier.identify()` currently reads studios.json in Python; delegate to `go_api/identify.py` (with Python fallback)

## Phase 3 — Thin wrapper cleanup
- [ ] TODO: `src/models/go_accelerated_db.py` — audit for redundant methods already covered by `go_api/db.py`; remove duplication, keep public interface
- [ ] TODO: `src/models/go_accelerated_studio.py` — audit for redundant methods already covered by `go_api/identify.py`; remove duplication, keep public interface

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
- Update the task list by marking the completed task as `[x] DONE`.
- Do not modify files outside the allowed scope.
- Do not leave partial edits behind if validation fails.
