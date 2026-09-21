---
name: audit-claims
description: Mechanically audit an agent-written report before delivering it — resolve every file:line citation, check each cited symbol is actually defined where the report says, and flag "this is deliberate" / "this is already implemented" claims that carry no citation. Use on any investigation, analysis, review or handover report in PornActressDB-Golang-Migration before handing it to the user. It bounds sloppiness, not correctness; it never replaces reading the code.
---

# Audit Claims

Write the report to a file first, then audit it. Auditing is not optional for
investigation and analysis reports — see `GEMINI.md` §證據紀律.

```bash
python3 .agents/skills/audit-claims/scripts/audit_claims.py --report tmp/report.md
python3 .agents/skills/audit-claims/scripts/audit_claims.py --report tmp/report.md --json
python3 .agents/skills/audit-claims/scripts/audit_claims.py --report tmp/report.md --strict
```

Windows 上直譯器名稱是 `python`：

```powershell
python .agents\skills\audit-claims\scripts\audit_claims.py --report tmp\report.md
```

Exit code is 0 when there are no failures, 1 otherwise. Only unresolved
citations fail by default; `--strict` promotes every warning to a failure.

## What it checks

| Category | Meaning | Default severity |
| --- | --- | --- |
| `unresolved` | Cited file does not exist, or the line range runs past the end of the file | FAIL |
| `symbol_mismatch` | No backticked identifier from the same block appears in the cited range, and the cited line is not inside a definition of one | WARN |
| `definition_outside_range` | The block reads as a location claim, but the symbol is defined on a different line | WARN |
| `unsupported_claims` | A "deliberate" or "already implemented" claim with no citation in the same block | WARN |
| `unlocated_symbols` | The block names a backticked identifier that is *defined in* a cited file, but cites that file without a line number | WARN |

Citations are recognised in both `pkg/database/sqlite_runtime.go:530-563` and
`pkg/database/sqlite_runtime.go#L530-L563` form, including percent-encoded absolute paths.
A path that is not repo-relative is resolved by its longest existing suffix.

### Go-specific handling

- **Method receivers.** `func (s *SQLiteStore) Compact() error` puts the
  receiver between the keyword and the name, so the generic
  `keyword + space + name` pattern never matches a Go method. A dedicated
  `func\s*\([^)]*\)\s*Name` pattern covers it — without this,
  `definition_outside_range` would silently never fire for the majority of this
  repo's symbols.
- **Grouped declarations.** `const (` / `var (` blocks drop the keyword after
  the first line, so `ansiReset = "\033[0m"` inside a group is matched by an
  assignment pattern instead.
- **Qualified names.** Go qualifies with `.` (`database.NewStore`,
  `SQLiteStore.Compact`), Rust with `::`; both are split to the leaf name. The
  cost is that `data.json` and `main.go` also parse as qualified identifiers, so
  any token whose leaf is a source suffix is dropped as a filename.

## What it cannot check

- **Whether the cited code supports the argument.** A citation can resolve
  perfectly and still be irrelevant to the sentence around it.
- **Whether a finding is real.** Nothing here adjudicates defects.
- **Negative claims.** "這裡沒有檢查 X" cites nothing by construction, so no
  check fires. This is the single most expensive failure mode in practice — see
  the `colors.go` case in `GEMINI.md` §存在性宣稱必須先搜尋 — and the only
  defence is the discipline rule, not this tool.
- **Usage-site citations.** `symbol_mismatch` passes as long as the name occurs
  in the range, so a citation that lands on a call site instead of a definition
  survives it. `definition_outside_range` covers that, but only fires when the
  prose reads as a location claim (`位於`, `定義`, `宣告`, `實作於`, `證據`,
  `defined`, …).
- **Symbols written without backticks.** Identifiers are only collected from
  `` `backticked` `` tokens, so "函式 noColor 定義於 `cmd/scanner/colors.go:17`" carries no
  identifiers and every symbol check short-circuits. This is the cheapest
  complete bypass; adversarial testing found it, and no amount of tuning closes
  it without drowning in prose false positives.
- **Attribution errors within ±3 lines.** The symbol search runs over the cited
  range plus a `--window` (default 3) of slack, so a citation off by one or two
  lines is indistinguishable from a correct one. Lower `--window` to tighten it,
  at the cost of false positives on multi-line signatures.
- **Prose that avoids the marker words.** Rewording "刻意設計" as "這樣寫是有
  原因的" evades `unsupported_claims`. The check raises the cost of an uncited
  claim; it does not make one impossible.
- **Symbols a report names without citing their file.** `unlocated_symbols`
  deliberately only fires when the identifier is *defined in* one of the files
  cited in the same block, otherwise it drowns in noise from package names and
  tool names that happen to sit in backticks beside a path.

A clean run means the report is internally consistent with the tree, not that
it is right. Treat `OK` as a precondition for delivery, never as evidence.

## Handling results

- `unresolved` — fix the citation before delivering. Never ship a report that
  points at a line that does not exist. This category also catches the phantom
  file: `docs/ARCHITECTURE.md` cited `pkg/database/db_helpers.go` for over two
  months, and `git log --all` shows that path never existed in this repo.
- `definition_outside_range` — either correct the line number, or reword so the
  claim is explicitly about a usage site.
- `unsupported_claims` — apply `GEMINI.md` §判定「刻意」必須舉證: produce the
  comment, the test, or the `docs/ARCHITECTURE.md` / `implementation-notes.md`
  entry, or move the item to the 假說 section.
- `unlocated_symbols` — add the line range. Naming a symbol beside a bare file
  path is an attribution claim, and attribution is exactly what the other checks
  cannot test without a range. Searching for the name is not enough: the symbol
  usually does exist somewhere in the repo, which is why a wrong attribution
  reads as plausible. The case this port was built from cited
  `src/services/go_cli.py:590-592` for `history_list`; that range is
  `db_get_actress`, and `history_list` exists nowhere in the file — the real
  symbol is `list_operations` at `src/services/go_cli.py:791`.

## Self-test

```bash
python3 .agents/skills/audit-claims/scripts/test_audit_claims.py
```

The self-test builds a throwaway tree in a temp dir (not the live repo, whose
line numbers drift every commit), writes a report with one correct citation plus
one instance of each failure class, and asserts that the correct citation stays
clean while every other class fires. It also pins the two Go-specific patterns
and the "a correct citation must not mask a wrong one in the same block"
regression — mutation testing showed all three were previously unasserted.
