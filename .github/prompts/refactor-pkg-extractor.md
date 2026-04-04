# Goal
Safely refactor only the Go extractor package in this repository.

# Allowed scope
- `pkg/extractor/extractor.go`
- `pkg/extractor/extractor_test.go`

# Forbidden scope
- Any file outside `pkg/extractor/**`
- `src/**`, `cmd/**`, `.github/**`, `go.mod`, `go.sum`, or workflow files
- Commits, pushes, PR creation, branch changes, or network access

# Safety rules
- Keep public behavior unchanged.
- Keep exported names and signatures compatible.
- Do not change CLI behavior, JSON output, Python bridge behavior, or repository configuration.
- Prefer one or two conservative refactors only.
- If no clearly safe cleanup is available, make no changes.

# Preferred refactor types
- Reduce duplication inside the extractor package.
- Extract small private helpers if this improves readability.
- Clarify local variable names or control flow.
- Keep regex handling behavior compatible with the current tests.
- Update tests in the same package only when needed to support a safe internal refactor.

# Validation
- Run `go test ./pkg/extractor -v` after changes.
- If you touch behavior-sensitive logic, also run `go test ./pkg/... -v`.

# Completion
- Stop once the scoped refactor is complete and tests pass.
- Do not modify files outside the allowed scope.
- Do not leave partial edits behind if validation fails.
