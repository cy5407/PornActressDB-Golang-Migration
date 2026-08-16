#!/usr/bin/env python3
"""Dependency-free unittest gate for mutation_check.py.

The restoration tests matter most. A mutation tool that leaves a file broken
after a crash is worse than no tool, because the damage lands in someone's
working tree and looks like their own edit.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mutation_check import (  # noqa: E402
    Mutation,
    SpecError,
    apply_mutation,
    check,
    load_spec,
)


class Workspace:
    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def write(self, relative: str, text: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def close(self) -> None:
        self._tmp.cleanup()


class SpecLoadingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = Workspace()
        self.addCleanup(self.workspace.close)

    def load(self, payload: dict) -> tuple:
        spec = self.workspace.write("spec.json", json.dumps(payload))
        return load_spec(spec, self.workspace.root)

    def test_missing_baseline_is_rejected(self) -> None:
        with self.assertRaises(SpecError):
            self.load({"mutations": [{"name": "a", "file": "f", "find": "x", "replace": "y"}]})

    def test_empty_mutation_list_is_rejected(self) -> None:
        with self.assertRaises(SpecError):
            self.load({"baseline": "true", "mutations": []})

    def test_missing_field_names_the_field(self) -> None:
        with self.assertRaises(SpecError) as caught:
            self.load({"baseline": "true", "mutations": [{"name": "a", "file": "f"}]})
        self.assertIn("find", str(caught.exception))

    def test_a_no_op_mutation_is_rejected(self) -> None:
        with self.assertRaises(SpecError):
            self.load(
                {
                    "baseline": "true",
                    "mutations": [{"name": "a", "file": "f", "find": "x", "replace": "x"}],
                }
            )

    def test_command_defaults_to_the_baseline(self) -> None:
        baseline, mutations = self.load(
            {
                "baseline": "run-the-suite",
                "mutations": [{"name": "a", "file": "f", "find": "x", "replace": "y"}],
            }
        )
        self.assertEqual(baseline, "run-the-suite")
        self.assertEqual(mutations[0].command, "run-the-suite")


class ApplyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = Workspace()
        self.addCleanup(self.workspace.close)

    def mutation(self, body: str, find: str, replace: str) -> Mutation:
        path = self.workspace.write("src.py", body)
        return Mutation("m", path, find, replace, "true")

    def test_ambiguous_match_is_an_error_not_a_guess(self) -> None:
        mutation = self.mutation("return None\nreturn None\n", "return None", "pass")
        with self.assertRaises(SpecError) as caught:
            apply_mutation(mutation)
        self.assertIn("2 times", str(caught.exception))

    def test_absent_match_is_an_error(self) -> None:
        mutation = self.mutation("a = 1\n", "return None", "pass")
        with self.assertRaises(SpecError):
            apply_mutation(mutation)

    def test_missing_file_is_an_error(self) -> None:
        mutation = Mutation("m", self.workspace.root / "ghost.py", "a", "b", "true")
        with self.assertRaises(SpecError):
            apply_mutation(mutation)


class RestorationTests(unittest.TestCase):
    """A broken file left behind is the worst outcome this tool can produce."""

    def setUp(self) -> None:
        self.workspace = Workspace()
        self.addCleanup(self.workspace.close)
        self.body = "guard = True\n"
        self.path = self.workspace.write("src.py", self.body)

    def test_file_is_restored_after_a_caught_mutation(self) -> None:
        mutation = Mutation("m", self.path, "True", "False", "false")
        self.assertTrue(check(mutation, self.workspace.root))
        self.assertEqual(self.path.read_text(encoding="utf-8"), self.body)

    def test_file_is_restored_after_a_surviving_mutation(self) -> None:
        mutation = Mutation("m", self.path, "True", "False", "true")
        self.assertFalse(check(mutation, self.workspace.root))
        self.assertEqual(self.path.read_text(encoding="utf-8"), self.body)

    def test_file_is_restored_when_the_command_raises(self) -> None:
        mutation = Mutation("m", self.path, "True", "False", "exit 1")
        check(mutation, self.workspace.root)
        self.assertEqual(self.path.read_text(encoding="utf-8"), self.body)


class VerdictTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = Workspace()
        self.addCleanup(self.workspace.close)
        self.path = self.workspace.write("src.py", "guard = True\n")

    def test_a_failing_command_means_the_mutation_was_caught(self) -> None:
        self.assertTrue(check(Mutation("m", self.path, "True", "False", "false"), self.workspace.root))

    def test_a_passing_command_means_the_mutation_survived(self) -> None:
        self.assertFalse(check(Mutation("m", self.path, "True", "False", "true"), self.workspace.root))


if __name__ == "__main__":
    unittest.main(verbosity=2)
