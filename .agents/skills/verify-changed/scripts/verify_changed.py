#!/usr/bin/env python3
"""Pick the narrowest relevant checks for the changed paths in this repo.

Four toolchains live here and none of them covers the others:

  * root Go module      -> go build/vet/test ./...
  * wails-app/          -> a separate go module; `go test ./...` at the root
                           does NOT reach it
  * tools-rs/           -> Rust, and the CI gate is three steps
                           (fmt --check, clippy -D warnings, test). Running
                           only `cargo test` silently skips two of them.
  * tests/ (Python)     -> pytest over the Go CLI contract locks

Emits a JSON plan by default; `--execute` runs it and stops at the first
failure. This never replaces the full gate before commit or release --
`full_gate_required_before_commit` is always true in the payload.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess  # nosec B404
import sys
import time
from pathlib import Path
from typing import Iterable

GO_PACKAGES = {
    "app",
    "cache",
    "database",
    "extractor",
    "mover",
    "pathutil",
    "safefile",
    "studio",
}
DOC_SUFFIXES = {".md", ".txt", ".html"}
CODE_SUFFIXES = {
    ".go",
    ".rs",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".mjs",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".ps1",
    ".sh",
    ".sql",
}

# Lower sorts first. Cheap static checks before test suites, root Go before the
# separate wails module, Rust's three steps in CI order.
COMMAND_ORDER = {
    "skill-audit-claims-tests": 1,
    "skill-verify-changed-tests": 2,
    "gofmt": 5,
    "go-vet": 6,
    "go-build": 7,
    "go-workspace": 10,
    "go-pkg-app": 20,
    "go-pkg-cache": 21,
    "go-pkg-database": 22,
    "go-pkg-extractor": 23,
    "go-pkg-mover": 24,
    "go-pkg-pathutil": 25,
    "go-pkg-safefile": 26,
    "go-pkg-studio": 27,
    "go-cmd-scanner": 30,
    "wails-build": 35,
    "wails-test": 36,
    "frontend-guard": 40,
    "cargo-fmt": 50,
    "cargo-clippy": 51,
    "cargo-test": 52,
    "pytest-go-cli-contracts": 60,
    "pytest-ci-workflows": 61,
    "pytest-all": 70,
}

NPM = "npm.cmd" if os.name == "nt" else "npm"


def configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def normalize_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def find_repo_root(explicit: str | None) -> Path:
    starts = (
        [Path(explicit).expanduser().resolve()]
        if explicit
        else [Path.cwd().resolve(), Path(__file__).resolve()]
    )
    for start in starts:
        for candidate in (start, *start.parents):
            if (candidate / "go.mod").is_file() and (candidate / "AGENTS.md").is_file():
                return candidate
    raise FileNotFoundError("找不到 PornActressDB-Golang-Migration 專案根目錄")


def normalize_paths(paths: Iterable[str]) -> list[str]:
    return sorted({normalize_path(path) for path in paths if path.strip()})


def git_names(root: Path, arguments: list[str]) -> list[str]:
    command = ["git", "-c", f"safe.directory={root.as_posix()}", *arguments, "-z"]
    result = subprocess.run(command, cwd=root, check=True, capture_output=True)  # nosec B603, B607
    return [
        part.decode("utf-8", errors="replace")
        for part in result.stdout.split(b"\0")
        if part
    ]


def discover_git_paths(root: Path, base: str | None) -> list[str]:
    paths: list[str] = []
    if base:
        paths.extend(git_names(root, ["diff", "--name-only", f"{base}...HEAD"]))
    paths.extend(git_names(root, ["diff", "--name-only"]))
    paths.extend(git_names(root, ["diff", "--cached", "--name-only"]))
    paths.extend(git_names(root, ["ls-files", "--others", "--exclude-standard"]))
    return normalize_paths(paths)


def command_plan(
    paths: list[str], python_executable: str
) -> tuple[list[dict[str, object]], list[str], list[str]]:
    commands: dict[str, dict[str, object]] = {}
    warnings: list[str] = []
    skipped: list[str] = []

    def add(command_id: str, cwd: str, argv: list[str], reason: str) -> None:
        if command_id not in commands:
            commands[command_id] = {
                "id": command_id,
                "cwd": cwd,
                "argv": argv,
                "reasons": [],
            }
        reasons = commands[command_id]["reasons"]
        if reason not in reasons:
            reasons.append(reason)

    def add_pytest(command_id: str, target: str, reason: str) -> None:
        add(
            command_id,
            ".",
            [python_executable, "-m", "pytest", target, "-q", "-p", "no:cacheprovider"],
            reason,
        )

    def add_rust_three_steps(reason: str) -> None:
        # All three, always. CI runs fmt --check and clippy -D warnings as
        # separate gates, and `cargo fmt --check` reports the whole crate --
        # including pre-existing violations in files this change never touched.
        add("cargo-fmt", ".", ["cargo", "fmt", "--manifest-path", "tools-rs/Cargo.toml", "--check"], reason)
        add("cargo-clippy", ".", ["cargo", "clippy", "--manifest-path", "tools-rs/Cargo.toml", "--", "-D", "warnings"], reason)
        add("cargo-test", ".", ["cargo", "test", "--manifest-path", "tools-rs/Cargo.toml"], reason)

    for path in paths:
        lower = path.casefold()
        suffix = Path(path).suffix.casefold()

        if lower in {"data/db.sqlite", "data/json_db/data.json"}:
            warnings.append(
                f"{path} 是受保護的資料檔，不得由驗證流程修改；請確認這個變更是有意的。"
            )
            continue

        if lower in {"go.mod", "go.sum"}:
            add("go-build", ".", ["go", "build", "./..."], path)
            add("go-workspace", ".", ["go", "test", "./...", "-count=1"], path)
            continue

        # The canonical schema is embedded by BOTH toolchains, so a change here
        # has to clear all four drift locks: one in Go, three on the Rust side.
        if lower == "pkg/database/sqlite_schema.sql":
            add("go-pkg-database", ".", ["go", "test", "./pkg/database/...", "-count=1"], path)
            add_rust_three_steps(path)
            continue

        # `pkg/mover/types.go` carries the json tags that ARE the CLI's stdout
        # shape for move/history, so editing it can break the cross-language
        # contract without touching cmd/scanner at all. The Python argv/shape
        # lock is the only thing that catches that.
        if lower == "pkg/mover/types.go":
            add("gofmt", ".", ["gofmt", "-l", "."], path)
            add("go-pkg-mover", ".", ["go", "test", "./pkg/mover/...", "-count=1"], path)
            add("go-cmd-scanner", ".", ["go", "test", "./cmd/scanner", "-count=1"], path)
            add_pytest("pytest-go-cli-contracts", "tests/test_go_cli_contracts.py", path)
            add("wails-build", "wails-app", ["go", "build", "./..."], path)
            continue

        if lower.startswith("pkg/"):
            parts = lower.split("/")
            package = parts[1] if len(parts) > 1 else ""
            if package in GO_PACKAGES:
                add("gofmt", ".", ["gofmt", "-l", "."], path)
                add(
                    f"go-pkg-{package}",
                    ".",
                    ["go", "test", f"./pkg/{package}/...", "-count=1"],
                    path,
                )
                # pkg/ is shared with the wails module; a change here can break
                # a binary that the root test run never builds.
                add("wails-build", "wails-app", ["go", "build", "./..."], path)
                continue

        if lower.startswith("cmd/scanner/"):
            add("gofmt", ".", ["gofmt", "-l", "."], path)
            add("go-cmd-scanner", ".", ["go", "test", "./cmd/scanner", "-count=1"], path)
            add_pytest("pytest-go-cli-contracts", "tests/test_go_cli_contracts.py", path)
            continue

        if lower.startswith("wails-app/frontend/"):
            add("frontend-guard", "wails-app/frontend", [NPM, "run", "test:guard"], path)
            continue

        if lower.startswith("wails-app/"):
            add("gofmt", ".", ["gofmt", "-l", "."], path)
            add("wails-build", "wails-app", ["go", "build", "./..."], path)
            add("wails-test", "wails-app", ["go", "test", "./backend/...", "-count=1"], path)
            continue

        if lower.startswith("tools-rs/"):
            add_rust_three_steps(path)
            continue

        if lower.startswith(".agents/skills/audit-claims/"):
            add(
                "skill-audit-claims-tests",
                ".",
                [python_executable, ".agents/skills/audit-claims/scripts/test_audit_claims.py"],
                path,
            )
            continue

        if lower.startswith(".agents/skills/verify-changed/"):
            add(
                "skill-verify-changed-tests",
                ".",
                [python_executable, ".agents/skills/verify-changed/scripts/test_verify_changed.py"],
                path,
            )
            continue

        if lower.startswith("tests/") and suffix == ".py":
            add_pytest(f"pytest-{lower.removeprefix('tests/').removesuffix('.py').replace('/', '-')}", path, path)
            continue

        if lower.startswith("src/") and suffix == ".py":
            add_pytest("pytest-go-cli-contracts", "tests/test_go_cli_contracts.py", path)
            if "go_cli" in lower:
                add_pytest("pytest-coverage-go-cli", "tests/test_coverage_go_cli.py", path)
            if any(token in lower for token in ("scraper", "searcher", "cache_manager")):
                warnings.append(
                    f"{path} 屬爬蟲層：窄測試涵蓋不完整，建議另跑 python -m pytest tests/ -q。"
                )
            continue

        if lower.startswith(".github/workflows/"):
            add_pytest("pytest-ci-workflows", "tests/test_ci_workflows.py", path)
            continue

        if lower in {"studios.json", "major_studios.json"}:
            add("go-pkg-studio", ".", ["go", "test", "./pkg/studio/...", "-count=1"], path)
            continue

        if lower.startswith("scripts/") or lower in {"setup.ps1", "setup.sh"}:
            skipped.append(path)
            continue

        if lower.startswith("wiki/") and suffix == ".md":
            warnings.append(
                "改過 wiki/**.md：必須同時追加 wiki/log.md 並執行 "
                "`PYTHONIOENCODING=utf-8 python3 wiki/gen_data.py`，否則 viewer 顯示舊內容。"
            )
            skipped.append(path)
            continue

        if suffix in DOC_SUFFIXES:
            skipped.append(path)
            continue

        if suffix in CODE_SUFFIXES:
            warnings.append(f"沒有窄驗證映射：{path}；請人工選擇測試或執行完整 gate。")
        else:
            skipped.append(path)

    # A workspace-wide Go run subsumes every per-package run.
    if "go-workspace" in commands:
        commands = {
            command_id: command
            for command_id, command in commands.items()
            if not command_id.startswith("go-pkg-") and command_id != "go-cmd-scanner"
        }

    ordered = sorted(
        commands.values(),
        key=lambda item: (COMMAND_ORDER.get(str(item["id"]), 65), str(item["id"])),
    )
    return ordered, sorted(set(warnings)), sorted(set(skipped))


def tail(text: str, line_count: int = 30) -> str:
    return "\n".join(text.splitlines()[-line_count:])


def execute_plan(
    root: Path, commands: list[dict[str, object]]
) -> tuple[list[dict[str, object]], bool]:
    results: list[dict[str, object]] = []
    passed = True
    for command in commands:
        started = time.monotonic()
        try:
            result = subprocess.run(  # nosec B603
                command["argv"],
                cwd=root / str(command["cwd"]),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            combined = "\n".join(
                part for part in (result.stdout, result.stderr) if part
            )
            item: dict[str, object] = {
                "id": command["id"],
                "exit_code": result.returncode,
                "duration_seconds": round(time.monotonic() - started, 3),
            }
            # `gofmt -l` exits 0 even when it lists offending files, so exit
            # code alone is not a verdict for it.
            if command["id"] == "gofmt" and result.stdout.strip():
                item["exit_code"] = 1
                item["output_tail"] = tail(combined)
                results.append(item)
                passed = False
                break
            if result.returncode != 0:
                item["output_tail"] = tail(combined)
                passed = False
            results.append(item)
            if not passed:
                break
        except OSError as error:
            results.append(
                {
                    "id": command["id"],
                    "exit_code": None,
                    "duration_seconds": round(time.monotonic() - started, 3),
                    "output_tail": str(error),
                }
            )
            passed = False
            break
    return results, passed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="依變更路徑選擇 PornActressDB-Golang-Migration 的最窄驗證"
    )
    parser.add_argument("--repo", help="專案根目錄；預設由目前目錄往上尋找")
    parser.add_argument(
        "--path", action="append", default=[], metavar="PATH", help="明確變更路徑；可重複"
    )
    parser.add_argument("--base", help="另外納入 base...HEAD 的 Git 變更")
    parser.add_argument(
        "--execute", action="store_true", help="實際執行計畫；預設只輸出 JSON 計畫"
    )
    parser.add_argument(
        "--pretty", action="store_true", help="縮排 JSON；預設輸出 compact JSON"
    )
    return parser


def main() -> int:
    configure_utf8_stdio()
    args = build_parser().parse_args()
    try:
        root = find_repo_root(args.repo)
        if args.path:
            discovered = discover_git_paths(root, args.base) if args.base else []
            paths = normalize_paths([*args.path, *discovered])
        else:
            paths = discover_git_paths(root, args.base)
        commands, warnings, skipped = command_plan(paths, sys.executable)
        payload: dict[str, object] = {
            "repo_root": str(root),
            "paths": paths,
            "commands": commands,
            "warnings": warnings,
            "skipped": skipped,
            "executed": args.execute,
            "full_gate_required_before_commit": True,
        }
        exit_code = 0
        if args.execute:
            results, passed = execute_plan(root, commands)
            payload["results"] = results
            payload["passed"] = passed
            exit_code = 0 if passed else 1
        print(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2 if args.pretty else None,
                separators=None if args.pretty else (",", ":"),
            )
        )
        return exit_code
    except (FileNotFoundError, subprocess.CalledProcessError) as error:
        print(
            json.dumps({"error": str(error)}, ensure_ascii=False, separators=(",", ":")),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
