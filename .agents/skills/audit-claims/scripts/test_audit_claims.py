#!/usr/bin/env python3
"""Self-test for audit_claims.py.

Builds a throwaway tree instead of auditing the live repository: the live tree's
line numbers drift with every commit, and a self-test that goes red because an
unrelated function moved teaches nobody anything.

Each case below is a failure this repository actually shipped, reduced to the
smallest file that reproduces it.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_claims import audit  # noqa: E402

GO_SOURCE = """// Package database — NewStore is the entry point; see also GetActressPrimaryStudio and ansiReset.
package database

import "errors"

// ErrNotFound 資料不存在錯誤
var ErrNotFound = errors.New("video not found")

const (
	ansiReset = "\\033[0m"
)

// GetActressPrimaryStudio returns the studio hosting the most videos.
func (s *SQLiteStore) GetActressPrimaryStudio(name string) string {
	return ""
}

func NewStore(cfg StoreConfig) (*SQLiteStore, error) {
	return nil, nil
}
"""
# Line map for GO_SOURCE (1-based):
#   1  package doc comment; MENTIONS NewStore / GetActressPrimaryStudio /
#      ansiReset without defining any of them. Citing line 1 as a location
#      claim is what drives the definition_outside_range assertions below.
#   7  var ErrNotFound
#  10  ansiReset (inside a const group — no keyword on the line itself, so only
#      the grouped-declaration pattern can find it)
#  14  func (s *SQLiteStore) GetActressPrimaryStudio  <- method receiver form,
#      so only the Go-method pattern can find it (`func\\s+Name` never matches)
#  18  func NewStore  <- plain keyword form

FAILURES: list[tuple[str, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}{(' — ' + detail) if detail else ''}")
        FAILURES.append((name, detail))


def main() -> int:
    with tempfile.TemporaryDirectory() as raw_root:
        root = Path(raw_root)
        (root / "pkg" / "database").mkdir(parents=True)
        (root / "pkg" / "database" / "store.go").write_text(GO_SOURCE, encoding="utf-8")

        report = "\n\n".join(
            [
                "# fixture",
                # clean: the method really is defined at line 14
                "- `GetActressPrimaryStudio` 定義於 `pkg/database/store.go:14`。",
                # unresolved: file absent from the tree (the db_helpers.go phantom)
                "- `pkg/database/db_helpers.go:10` 的 helper 被依賴。",
                # unresolved: line past end of file
                "- `pkg/database/store.go:9999` 有 `ErrNotFound`。",
                # symbol_mismatch: name occurs nowhere in the cited range (+/-3)
                "- 依據 `pkg/database/store.go:19-20` 的 `ErrNotFound` 判斷。",
                # definition_outside_range: the name appears at line 1 (a doc
                # comment) so the symbol check passes, but the definition is at
                # line 18 -- this is the gap the location check exists to close.
                "- `NewStore` 定義於 `pkg/database/store.go:1`。",
                # Same shape, but only reachable through the Go method-receiver
                # pattern: `func (s *SQLiteStore) GetActressPrimaryStudio`.
                # Delete that pattern and defined_at goes empty, this finding
                # disappears, and the check silently stops covering most of
                # this repo's symbols.
                "- `GetActressPrimaryStudio` 定義於 `pkg/database/store.go:1`。",
                # Same shape again, but only reachable through the grouped
                # `const (` / `var (` pattern -- the line carries no keyword.
                "- `ansiReset` 宣告於 `pkg/database/store.go:1`。",
                # Regression guard. A union-based coverage rule once let one
                # correct citation silence every wrong citation beside it in
                # the same block -- including a name that exists nowhere in
                # the file, which is the exact failure this tool was built
                # for. The first citation here is correct; the second is not,
                # and it must still be reported.
                "- `GetActressPrimaryStudio` 定義於 `pkg/database/store.go:14`；"
                "`BogusHelper` 則在 `pkg/database/store.go:19`。",
                # unlocated_symbols: symbol named beside a bare path
                "- pkg/database/store.go 裡的 `ErrNotFound` 是哨兵錯誤。",
                # unsupported_claims: 刻意 with no citation in the block
                "- 這個 no-op 是刻意設計的。",
            ]
        )

        findings = audit(root, report, window=3)

    print("audit_claims self-test")

    unresolved = {item["path"] for item in findings.unresolved}
    check(
        "unresolved catches a file that does not exist",
        any("db_helpers.go" in path for path in unresolved),
        f"unresolved={sorted(unresolved)}",
    )
    check(
        "unresolved catches a line past end of file",
        any("outside file" in item["reason"] for item in findings.unresolved),
        f"reasons={[i['reason'] for i in findings.unresolved]}",
    )

    mismatched = {item["citation"] for item in findings.symbol_mismatch}
    check(
        "symbol_mismatch catches a wrong attribution",
        any("store.go:19-20" in citation for citation in mismatched),
        f"symbol_mismatch={sorted(mismatched)}",
    )

    check(
        "a correct citation does NOT mask a wrong one in the same block",
        any("store.go:19" in citation for citation in mismatched),
        f"symbol_mismatch={sorted(mismatched)}",
    )

    outside = {item["identifier"] for item in findings.definition_outside_range}
    check(
        "definition_outside_range catches a Go func cited off by one line",
        "NewStore" in outside,
        f"definition_outside_range={sorted(outside)}",
    )
    # These two lock the Go-specific patterns SKILL.md advertises. Mutation
    # testing found that deleting either pattern left the suite green, i.e. the
    # single most important behaviour was unasserted.
    check(
        "definition_outside_range works for a Go METHOD (receiver form)",
        "GetActressPrimaryStudio" in outside,
        f"definition_outside_range={sorted(outside)}",
    )
    check(
        "definition_outside_range works for a GROUPED const declaration",
        "ansiReset" in outside,
        f"definition_outside_range={sorted(outside)}",
    )

    unlocated = {
        identifier
        for item in findings.unlocated_symbols
        for identifier in item["identifiers"]
    }
    check(
        "unlocated_symbols catches a symbol beside a bare path",
        "ErrNotFound" in unlocated,
        f"unlocated_symbols={sorted(unlocated)}",
    )

    check(
        "unsupported_claims catches an uncited 刻意 claim",
        any(item["kind"] == "deliberate" for item in findings.unsupported_claims),
        f"unsupported_claims={findings.unsupported_claims}",
    )

    # The clean citation must not appear in any bucket. A checker that flags
    # correct citations gets switched off within a week.
    dirty = (
        [item["citation"] for item in findings.symbol_mismatch]
        + [item["citation"] for item in findings.definition_outside_range]
        + [item["citation"] for item in findings.unresolved]
    )
    check(
        "a correct citation stays clean",
        not any(citation.endswith("store.go:14") for citation in dirty),
        f"flagged={dirty}",
    )

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) failed")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
