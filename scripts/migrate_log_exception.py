#!/usr/bin/env python3
"""Migrate logger.error / logging.error → logger.exception inside except blocks.

Mechanical transformer that touches a `logger.error(...)` or `logging.error(...)`
call only when the enclosing scope is an `except` block AND at least one of
these conditions holds:

- The call has an `exc_info=True` keyword argument → drop the kwarg.
- The first positional argument is an f-string containing a `{e}` / `{exc}` /
  `{err}` formatted expression (a bare Name) → drop that interpolation segment.

When either condition triggers, `.error` is renamed to `.exception`. Both
transformations may apply to the same call; the rename happens once.

Patterns that this script intentionally does NOT touch:

- Exception-variable spellings other than `e` / `exc` / `err` (e.g. `{error}`,
  `{ex}`, `{exception}`).
- `%`-formatting or `.format(...)` style interpolation.
- `.error` calls outside any `except` block.
- Receivers other than `logger` / `logging` (e.g. `self.log.error(...)`).

Anything left over should be migrated by hand; we list it in
`implementation-notes.md` rather than guessing.

Usage:
    python scripts/migrate_log_exception.py src/
    python scripts/migrate_log_exception.py --check src/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import libcst as cst

EXCEPTION_NAMES = {"e", "exc", "err"}
TARGET_RECEIVERS = {"logger", "logging"}


class LogExceptionTransformer(cst.CSTTransformer):
    def __init__(self) -> None:
        self._except_depth = 0
        self.changes = 0

    def visit_ExceptHandler(self, node: cst.ExceptHandler) -> None:
        self._except_depth += 1

    def leave_ExceptHandler(
        self, original_node: cst.ExceptHandler, updated_node: cst.ExceptHandler
    ) -> cst.ExceptHandler:
        self._except_depth -= 1
        return updated_node

    def leave_Call(
        self, original_node: cst.Call, updated_node: cst.Call
    ) -> cst.BaseExpression:
        if self._except_depth <= 0:
            return updated_node

        func = updated_node.func
        if not isinstance(func, cst.Attribute) or func.attr.value != "error":
            return updated_node
        receiver = func.value
        if not isinstance(receiver, cst.Name) or receiver.value not in TARGET_RECEIVERS:
            return updated_node

        new_args = list(updated_node.args)

        removed_exc_info = False
        filtered: list[cst.Arg] = []
        for arg in new_args:
            if arg.keyword is not None and arg.keyword.value == "exc_info":
                value = arg.value
                if isinstance(value, cst.Name) and value.value == "True":
                    removed_exc_info = True
                    continue
            filtered.append(arg)
        new_args = filtered

        removed_interp = False
        if new_args and isinstance(new_args[0].value, cst.FormattedString):
            fs = new_args[0].value
            new_parts: list[cst.BaseFormattedStringContent] = []
            for part in fs.parts:
                if isinstance(part, cst.FormattedStringExpression):
                    expr = part.expression
                    if isinstance(expr, cst.Name) and expr.value in EXCEPTION_NAMES:
                        removed_interp = True
                        continue
                new_parts.append(part)
            if removed_interp:
                new_fs = fs.with_changes(parts=tuple(new_parts))
                new_args[0] = new_args[0].with_changes(value=new_fs)

        if not (removed_exc_info or removed_interp):
            return updated_node

        if new_args:
            new_args[-1] = new_args[-1].with_changes(comma=cst.MaybeSentinel.DEFAULT)

        new_func = func.with_changes(attr=cst.Name("exception"))
        self.changes += 1
        return updated_node.with_changes(func=new_func, args=tuple(new_args))


def migrate_file(path: Path, *, write: bool) -> int:
    src = path.read_text(encoding="utf-8")
    try:
        module = cst.parse_module(src)
    except cst.ParserSyntaxError as exc:
        print(f"parse error {path}: {exc}", file=sys.stderr)
        return 0
    transformer = LogExceptionTransformer()
    new_module = module.visit(transformer)
    if transformer.changes == 0:
        return 0
    if write:
        path.write_text(new_module.code, encoding="utf-8")
    return transformer.changes


def iter_targets(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            out.extend(sorted(p.rglob("*.py")))
        elif p.is_file():
            out.append(p)
        else:
            print(f"warn: {raw} not found", file=sys.stderr)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate logger.error → logger.exception in except blocks.")
    parser.add_argument("paths", nargs="+", help="Files or directories to scan")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report changes without writing back",
    )
    args = parser.parse_args()

    total = 0
    files_touched = 0
    for path in iter_targets(args.paths):
        n = migrate_file(path, write=not args.check)
        if n:
            files_touched += 1
            total += n
            verb = "would change" if args.check else "changed"
            print(f"{verb} {path}: {n}")

    print(f"\n{total} call sites across {files_touched} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
