# Goal
Safely advance the Python-to-Go migration in this repository.

# Allowed scope
- `pkg/**`
- `cmd/scanner/**`
- `src/services/go_api/**`
- `src/services/go_bridge.py`
- `src/services/go_runner.py`
- `src/models/go_accelerated_db.py`
- `src/models/go_accelerated_studio.py`
- `src/utils/scanner.py`
- `src/utils/file_mover.py`
- `tests/**`

# Forbidden scope
- Any file outside the allowed scope
- `src/ui/**`, `src/scrapers/**`, `.github/**`, `data/**`, `logs/**`
- Commits, pushes, PR creation, branch changes, or network access

# Safety rules
- Prefer moving behavior from Python wrappers into existing Go services or CLI-facing APIs.
- Keep GUI behavior, JSON output contracts, and public Python call sites compatible.
- Preserve Python fallback behavior unless the Go path is already the established primary path.
- Prefer one cohesive migration step only.
- If no clearly safe migration step is available, make no changes.

# Preferred migration targets
- Thin Python wrappers that still duplicate Go-owned behavior.
- `src/services/go_api/move.py` splitting or simplification when it reduces Python orchestration.
- Removing redundant Python pre/post-processing around Go scan or move flows.
- Consolidating shared logic into `pkg/app/**`, `pkg/contracts/**`, or existing Go CLI paths.
- Adding or tightening tests that prove Python and Go paths stay behaviorally aligned.

# Validation
- Run targeted tests for touched Go packages.
- Run `go test ./pkg/... -v` after changes.
- Run affected Python tests when Python bridge or wrapper files change.

# Completion
- Stop once one safe migration-oriented refactor is complete and tests pass.
- Do not modify files outside the allowed scope.
- Do not leave partial edits behind if validation fails.
