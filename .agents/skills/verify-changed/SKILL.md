---
name: verify-changed
description: Select and optionally run the narrowest relevant Go, wails-module, Rust db-tool, and Python checks for changed paths in PornActressDB-Golang-Migration. Use during implementation or review when a full four-toolchain gate would be unnecessarily slow; do not use it as a substitute for the required full gate before commit or release.
---

# Verify Changed

Generate a compact plan first. Pass explicit paths when the task scope is known;
otherwise it inspects the Git working tree (unstaged, staged, and untracked).

```bash
python3 .agents/skills/verify-changed/scripts/verify_changed.py --path pkg/database/sqlite_runtime.go --pretty
python3 .agents/skills/verify-changed/scripts/verify_changed.py --base HEAD~1 --pretty
python3 .agents/skills/verify-changed/scripts/verify_changed.py --execute
```

`--execute` runs the plan in order and stops at the first failure; exit code is
0 only if every command passed. Without it the script only prints the plan and
always exits 0.

## Why this exists

Four toolchains live in this repo and **none of them covers the others**:

| Change | What the obvious command misses |
| --- | --- |
| `pkg/**` | `go test ./...` at the root never builds `wails-app/`, a separate go module that consumes the same packages via `replace`. |
| `wails-app/**` | Root `go build ./...` does not reach it at all. |
| `tools-rs/**` | CI runs **three** gates — `cargo fmt --check`, `cargo clippy -- -D warnings`, `cargo test`. Running only `cargo test` skips two, and `fmt --check` reports the whole crate including files you never touched. |
| `cmd/scanner/**` | The argv/JSON contract is locked from the Python side in `tests/test_go_cli_contracts.py`; Go tests alone cannot catch a broken CLI contract. |
| `pkg/database/sqlite_schema.sql` | The schema is embedded by **both** Go (`//go:embed`) and Rust (`include_str!`), so a change has to clear four drift locks split across two languages. |

The plan encodes those couplings so they are not re-derived (or forgotten) on
every change.

## Notable behaviours

- **`gofmt -l` exits 0 even when it lists offending files.** The runner treats
  any output from it as a failure; exit code alone is not a verdict.
- **A workspace-wide Go run subsumes per-package runs.** Touching `go.mod`
  promotes the plan to `go test ./...` and drops the narrower `go-pkg-*` and
  `go-cmd-scanner` entries.
- **`data/db.sqlite` and `data/json_db/data.json` produce a warning, never a
  command.** They are protected data files; the verification flow must not
  touch them.
- **`wiki/**.md` produces a warning, not a check.** Editing wiki markdown
  requires the three-step ritual (edit → append `wiki/log.md` → run
  `gen_data.py`); skipping the last step leaves the viewer showing stale
  content, and no test catches it.
- **An unmapped code path warns rather than silently passing.** A green run with
  a `沒有窄驗證映射` warning means the tool found nothing to run, not that the
  change is verified.

## What it does not do

- It does not replace the full gate. `full_gate_required_before_commit` is
  always `true` in the payload for that reason.
- It does not know which *test function* is relevant — only which suite.
- Scraper-layer Python changes get a warning instead of precise coverage; the
  crawler tests are broad and slow, so the tool defers that call to you.
- It does not run `wails build` or produce any `.exe`. Those require explicit
  user authorisation (see `GEMINI.md` §驗證與完成聲明).

## Self-test

```bash
python3 .agents/skills/verify-changed/scripts/test_verify_changed.py
```

Plan selection only — the self-test never executes a build or a test suite.
