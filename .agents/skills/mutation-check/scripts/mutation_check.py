#!/usr/bin/env python3
"""Break the code on purpose and check that the tests notice.

A passing suite proves the tests ran, not that they are watching anything. The
only direct evidence that a guard is protected is that removing it turns the
suite red. This applies the mutation, runs the command, asserts it fails, and
puts the file back.

Spec is JSON so it lives beside the fix and can be re-run by anyone:

    {
      "baseline": "cargo test -p domain",
      "mutations": [
        {
          "name": "deserialize error branches swallowed",
          "file": "crates/domain/src/lib.rs",
          "find": "return Err(error);",
          "replace": "let _ = error;",
          "command": "cargo test -p domain"
        }
      ]
    }

`find` must occur exactly once in the file. An ambiguous match is an error, not
a guess -- mutating the wrong site would produce a confident, wrong answer.

Exit code is 0 only when the baseline passes and every mutation is caught. A
surviving mutation is the finding: that code can be broken silently.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Mutation:
    name: str
    file: Path
    find: str
    replace: str
    command: str


class SpecError(Exception):
    """The spec cannot be used as written."""


def load_spec(spec_path: Path, repo_root: Path) -> tuple[str, list[Mutation]]:
    try:
        raw = json.loads(spec_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SpecError(f"spec is not valid JSON: {error}") from error

    baseline = raw.get("baseline")
    if not baseline:
        raise SpecError("spec needs a `baseline` command that passes before mutating")

    entries = raw.get("mutations")
    if not entries:
        raise SpecError("spec needs at least one entry in `mutations`")

    mutations = []
    for index, entry in enumerate(entries):
        missing = [k for k in ("name", "file", "find", "replace") if k not in entry]
        if missing:
            raise SpecError(f"mutation #{index + 1} is missing: {', '.join(missing)}")
        if entry["find"] == entry["replace"]:
            raise SpecError(f"mutation #{index + 1} does not change anything")
        mutations.append(
            Mutation(
                name=entry["name"],
                file=repo_root / entry["file"],
                find=entry["find"],
                replace=entry["replace"],
                command=entry.get("command", baseline),
            )
        )
    return baseline, mutations


def run(command: str, cwd: Path) -> int:
    completed = subprocess.run(command, shell=True, cwd=cwd, capture_output=True, text=True)
    return completed.returncode


def apply_mutation(mutation: Mutation) -> str:
    """Write the mutated file and return the original text for restoration."""
    if not mutation.file.is_file():
        raise SpecError(f"file not found: {mutation.file}")
    original = mutation.file.read_text(encoding="utf-8")
    occurrences = original.count(mutation.find)
    if occurrences == 0:
        raise SpecError(f"`find` text not present in {mutation.file}")
    if occurrences > 1:
        raise SpecError(
            f"`find` text occurs {occurrences} times in {mutation.file}; "
            "make it unique so the intended site is the one that changes"
        )
    mutation.file.write_text(original.replace(mutation.find, mutation.replace), encoding="utf-8")
    return original


def check(mutation: Mutation, repo_root: Path) -> bool:
    """Return True when the mutation is caught (the command fails)."""
    original = apply_mutation(mutation)
    try:
        return run(mutation.command, repo_root) != 0
    finally:
        # Restoration must survive any failure above, including KeyboardInterrupt.
        mutation.file.write_text(original, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument(
        "--repo-root",
        type=Path,
        # scripts → mutation-check → skills → .agents → repo root
        default=Path(__file__).resolve().parents[4],
        help="commands run here; defaults to the repository root",
    )
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    try:
        baseline, mutations = load_spec(args.spec, repo_root)
    except SpecError as error:
        print(f"spec error: {error}", file=sys.stderr)
        return 2

    print(f"baseline: {baseline}")
    if run(baseline, repo_root) != 0:
        print(
            "baseline failed. A red suite cannot tell you whether a mutation was "
            "noticed, so fix that first.",
            file=sys.stderr,
        )
        return 2
    print("baseline passes\n")

    survivors = []
    for mutation in mutations:
        print(f"  mutating: {mutation.name}")
        try:
            caught = check(mutation, repo_root)
        except SpecError as error:
            print(f"    spec error: {error}", file=sys.stderr)
            return 2
        if caught:
            print("    caught\n")
        else:
            print("    SURVIVED — nothing failed with this broken\n")
            survivors.append(mutation)

    if survivors:
        print(f"{len(survivors)}/{len(mutations)} mutations survived:")
        for mutation in survivors:
            print(f"  - {mutation.name} ({mutation.file.name})")
        print("\nEach survivor is code that can be broken without any test noticing.")
        return 1

    print(f"all {len(mutations)} mutations caught")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
