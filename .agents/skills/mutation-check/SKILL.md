---
name: mutation-check
description: Break a guard on purpose and confirm the tests notice. Use after fixing a defect, after adding a test that is meant to protect something, and when a report claims code is uncovered — a green suite proves the tests ran, not that they are watching. Records the mutations beside the fix so anyone can re-run them.
---

# Mutation Check

A passing test suite tells you the tests ran. It does not tell you they would
notice if the code stopped working. The only direct evidence is to break the
code and watch the suite go red.

```bash
python3 .agents/skills/mutation-check/scripts/mutation_check.py --spec <spec.json>
```

Exit 0 means the baseline passed and every mutation was caught. Exit 1 means at
least one mutation **survived** — that code can be broken without any test
noticing, which is the finding. Exit 2 means the spec or the baseline is
unusable.

Language- and toolchain-agnostic: the spec supplies the commands, so anything
runnable from a shell works.

## Spec

```json
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
```

`command` defaults to `baseline`. Paths in `file` are relative to `--repo-root`
(default: the repository root four levels above the script). Unknown keys are
ignored, so `"_comment"` is a safe place to note where a spec came from.

`find` must occur **exactly once** in the file; an ambiguous match is a hard
error rather than a guess, because mutating the wrong site produces a confident
wrong answer. Add surrounding lines to disambiguate — see
`examples/python-encoding-guards.json`, where the same statement appears in both
a `try` and its `except` fallback.

The baseline must pass before anything is mutated. A red suite cannot tell you
whether a mutation was noticed.

## When to reach for it

- **After fixing a defect.** The fix and the test that protects it are two
  claims; the second is unproven until a mutation confirms it.
- **After writing a test that is supposed to cover something.** A test can pass
  without ever reaching the code it names — see below.
- **When a report claims code is uncovered.** "No test covers this" is a
  checkable claim, and this is how you check it.

## What it caught in practice

The examples below are **facts about the project this skill was extracted
from**, not about whatever repository you have installed it into. They are here
to show the shape of the failure, not to be cited as your own evidence.

`examples/python-encoding-guards.json` holds the five real mutations from a
2026-08-16 encoding fix. Two findings from that session came from this technique
and would not have surfaced otherwise:

- **A fix that reproduced the defect it was fixing.** The bug was a fallback
  chain whose last link always succeeded, making everything below it dead. The
  first fix moved that link one layer down — still always succeeding, still
  making the layer below dead. Nothing failed; a probe showed the new layer was
  unreachable.
- **A test that passed without testing anything.** A test meant to prove a
  persist failure propagates made the persist fail by dropping the table. It
  passed. But the code reads before it writes, so the read failed first and the
  batch aborted before any persist ran. The test never reached the path in its
  own name.

## Writing mutations that find things

### Mutate in both directions

The reflex is to disable the guard. Do that, then also make it **over-fire**.
The two find different holes, and the second is the one usually left uncovered:
a suite full of "the bad input is rejected" cases says nothing about the good
input still getting through.

A guard matching "asterisks only" got both:

| Mutation | Result |
|---|---|
| stop rejecting asterisk-only names | caught |
| reject **any** name containing an asterisk | **survived** |

Nothing covered "a real name carrying an asterisk is kept", so the guard could
have been widened into discarding real data with the suite still green.

### One rule in two places needs two mutations

When the same rule is enforced on both sides of a boundary — two functions, two
languages, backend and frontend — mutate each site separately. Coverage on one
side reads as coverage of the rule and is not.

This landed twice in one sweep: a generation guard added to two handlers with
only one tested, and a placeholder rule where the Rust side had the
keep-a-real-name case and the TypeScript side did not.

### Make Red fail for the stated reason

Before the fix, check *why* the new test fails. A test that goes red because a
fixture never rendered, or a table was missing, is not evidence about the
defect — and once it passes you will not know which change did it.

Read the failure message and confirm it names the defect. If it names anything
else, the test is wrong, not the code.

## What it cannot do

- **It does not find defects.** You supply the mutation, so it only checks the
  guards you already thought of. It measures your test suite, not your code.
- **A caught mutation proves one thing only:** *that* break is noticed. A
  different break at the same site may not be.
- **It runs your command with `shell=True`** in the repository root. Specs are
  code; read one before running it.
- **It edits real source files in place** and restores them in a `finally`
  block. That survives exceptions and Ctrl-C, but not `SIGKILL` or a power cut —
  run it on a clean working tree so `git diff` can tell you if something was
  left behind.
- **It cannot see damage outside the mutated file.** Restoration is by exact
  content, and the tests cover it, but a command that writes elsewhere is
  outside its scope.

## Self-test

```bash
python3 .agents/skills/mutation-check/scripts/test_mutation_check.py
```

13 tests. The restoration cases matter most: a mutation tool that leaves a file
broken is worse than none, because the damage lands in a working tree looking
like someone's own edit.
