#!/usr/bin/env python3
"""Self-test for verify_changed.py — plan selection only, nothing is executed."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from verify_changed import command_plan  # noqa: E402

FAILURES: list[str] = []


def plan(paths: list[str]) -> tuple[set[str], list[str], list[str]]:
    commands, warnings, skipped = command_plan(paths, "python3")
    return {str(command["id"]) for command in commands}, warnings, skipped


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}{(' — ' + detail) if detail else ''}")
        FAILURES.append(name)


def main() -> int:
    print("verify_changed self-test")

    ids, _, _ = plan(["pkg/database/sqlite_runtime.go"])
    check(
        "a pkg/ change also builds the separate wails module",
        {"go-pkg-database", "wails-build", "gofmt"} <= ids,
        f"ids={sorted(ids)}",
    )

    # types.go holds the json tags that are the CLI's stdout shape, so it needs
    # the Python contract lock even though it lives under pkg/.
    ids, _, _ = plan(["pkg/mover/types.go"])
    check(
        "pkg/mover/types.go plans the cross-language contract lock",
        {"go-pkg-mover", "go-cmd-scanner", "pytest-go-cli-contracts"} <= ids,
        f"ids={sorted(ids)}",
    )

    ids, _, _ = plan(["pkg/mover/batch.go"])
    check(
        "a plain pkg/mover file does NOT drag in the contract lock",
        "pytest-go-cli-contracts" not in ids,
        f"ids={sorted(ids)}",
    )

    ids, _, _ = plan(["tools-rs/src/verify.rs"])
    check(
        "a Rust change plans all three CI steps, not just cargo test",
        {"cargo-fmt", "cargo-clippy", "cargo-test"} <= ids,
        f"ids={sorted(ids)}",
    )

    ids, _, _ = plan(["pkg/database/sqlite_schema.sql"])
    check(
        "a schema change plans both the Go and the Rust drift locks",
        {"go-pkg-database", "cargo-fmt", "cargo-clippy", "cargo-test"} <= ids,
        f"ids={sorted(ids)}",
    )

    ids, _, _ = plan(["cmd/scanner/db_cmd.go"])
    check(
        "a CLI change plans the Python contract lock",
        {"go-cmd-scanner", "pytest-go-cli-contracts"} <= ids,
        f"ids={sorted(ids)}",
    )

    ids, _, _ = plan(["wails-app/backend/app.go"])
    check(
        "a wails backend change runs in the wails module",
        {"wails-build", "wails-test"} <= ids,
        f"ids={sorted(ids)}",
    )

    ids, _, _ = plan(["go.mod", "pkg/mover/batch.go"])
    check(
        "a workspace-wide run subsumes per-package runs",
        "go-workspace" in ids and not any(i.startswith("go-pkg-") for i in ids),
        f"ids={sorted(ids)}",
    )

    _, warnings, _ = plan(["wiki/architecture/database.md"])
    check(
        "a wiki edit warns about gen_data.py",
        any("gen_data.py" in warning for warning in warnings),
        f"warnings={warnings}",
    )

    _, warnings, _ = plan(["data/db.sqlite"])
    check(
        "touching the runtime DB raises a warning instead of a test",
        any("受保護" in warning for warning in warnings),
        f"warnings={warnings}",
    )

    _, warnings, _ = plan(["pkg/unknown_thing/foo.go"])
    check(
        "an unmapped code path warns rather than silently passing",
        any("沒有窄驗證映射" in warning for warning in warnings),
        f"warnings={warnings}",
    )

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) failed")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
