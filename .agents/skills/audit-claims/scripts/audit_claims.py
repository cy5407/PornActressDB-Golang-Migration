#!/usr/bin/env python3
"""Mechanically audit an agent report's citations and unsupported claims.

Dependency-free. Reads a markdown report and checks four things that agent
reports in this repository have got wrong. The concrete case this port was
built from (2026-08-16) cited `src/services/go_cli.py:590-592` for a function
named `history_list`; that range holds `db_get_actress`, and `history_list`
does not exist anywhere in the file -- the real symbol is `list_operations` at
`src/services/go_cli.py:791`. Every number in the surrounding report was right,
which is exactly why a human reviewer waves it through.

Checks:

1. Every `path:line` / `path#Lline-Lline` citation resolves to a file that
   exists and to a line range inside that file.
2. Every citation is supported: the cited symbol appears inside the cited
   range, or the cited line sits inside that symbol's definition body (so the
   "defined at X, used at Y" form is not punished).
3. A block that claims to give a symbol's *location* points at the line where
   that symbol is defined, not merely at a line that mentions it.
4. Every "this is deliberate" or "this is already implemented" claim carries a
   citation in the same block.

Check 2 only proves the name is nearby or encloses the line, so a citation that
lands on a usage site instead of the definition still passes it -- check 3
exists to cover that gap, and only fires when the prose reads as a location
claim. Check 2 is scoped to the single citation plus its enclosing definition,
never to "some other citation in the same block": a block-wide rule lets one
correct citation silence every wrong one beside it. Neither check can tell
whether the cited code supports the surrounding argument; they bound
sloppiness, not correctness.

Exit code 0 when there are no failures, 1 otherwise. Warnings never fail the
run unless --strict is passed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

SOURCE_SUFFIXES = (
    "go",
    "rs",
    "py",
    "ts",
    "tsx",
    "js",
    "jsx",
    "mjs",
    "toml",
    "md",
    "sql",
    "json",
    "yaml",
    "yml",
    "ps1",
    "sh",
    "mod",
    "sum",
    "ini",
)

# Matches `pkg/database/sqlite_runtime.go:530-563`, `main.go:347`, and the
# `#L530-L563` fragment form that file:/// links in these reports use.
CITATION_RE = re.compile(
    r"(?P<path>[A-Za-z0-9_][A-Za-z0-9_./%\-]*\.(?:" + "|".join(SOURCE_SUFFIXES) + r"))"
    r"[:#]L?(?P<start>\d+)"
    r"(?:\s*[-–—]\s*L?(?P<end>\d+))?"
)

# A source path with no line number after it. `CITATION_RE` requires `:123`,
# so a block naming only the file slips past every symbol check below -- which
# is how a wrong function name reaches a reader unchallenged even though the
# surrounding facts are right.
BARE_PATH_RE = re.compile(
    r"(?<![:\w])(?P<path>[A-Za-z0-9_][A-Za-z0-9_./%\-]*\.(?:"
    + "|".join(SOURCE_SUFFIXES)
    + r"))(?![:#\w])"
)

BACKTICK_RE = re.compile(r"`([^`\n]+)`")
# Go qualifies with `.` (`database.NewStore`, `SQLiteStore.Compact`), Rust with
# `::`. Accept both so the leaf name can be extracted either way.
IDENTIFIER_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:(?:::|\.)[A-Za-z_][A-Za-z0-9_]*)*$"
)
QUALIFIER_SPLIT_RE = re.compile(r"::|\.")
# `data.json` / `main.go` also satisfy IDENTIFIER_RE once `.` is a valid
# separator, and their leaf ("json", "go") is pure noise. Drop any token whose
# leaf is a file suffix -- a real symbol never ends in one.
FILENAME_LEAVES = frozenset(SOURCE_SUFFIXES)

DELIBERATE_MARKERS = (
    "刻意",
    "故意",
    "有意為之",
    "既定取捨",
    "設計如此",
    "本來就是這樣設計",
    "by design",
    "deliberate",
    "intentional",
    "on purpose",
)

LOCATION_MARKERS = (
    "位於",
    "位在",
    "定義",
    "宣告",
    "註冊於",
    "實作於",
    "實作在",
    "常數",
    "證據",
    "defined",
    "declared",
    "located",
    "lives at",
    "implemented at",
)

DEFINITION_KEYWORDS = (
    "const",
    "static",
    "func",
    "fn",
    "struct",
    "enum",
    "type",
    "trait",
    "def",
    "class",
    "function",
    "let",
    "var",
    "interface",
    "package",
)

EXISTENCE_MARKERS = (
    "已實作",
    "已經實作",
    "已完整實作",
    "目前使用",
    "現行使用",
    "現行實作",
    "已經在程式碼",
    "已在程式碼",
    "already implemented",
    "currently uses",
    "is implemented",
)

# Words that look like identifiers but carry no locating power.
IDENTIFIER_STOPLIST = {
    # Rust / general
    "Some",
    "None",
    "Ok",
    "Err",
    "true",
    "false",
    "null",
    "self",
    "return",
    "String",
    "Vec",
    "Option",
    "Result",
    # Go builtins, conventional names and stdlib types that appear everywhere
    "err",
    "nil",
    "ctx",
    "int",
    "int64",
    "bool",
    "byte",
    "rune",
    "error",
    "string",
    "make",
    "len",
    "cap",
    "append",
    "defer",
    "range",
    "struct",
    "interface",
    "context",
    "Context",
    "Error",
    "Close",
    "main",
    "test",
    # Python
    "None_",
    "dict",
    "list",
    "None",
    "self",
}


@dataclass
class Citation:
    path: str
    start: int
    end: int
    block_index: int
    raw: str


@dataclass
class Block:
    index: int
    start_line: int
    text: str


@dataclass
class Findings:
    unresolved: list[dict] = field(default_factory=list)
    symbol_mismatch: list[dict] = field(default_factory=list)
    definition_outside_range: list[dict] = field(default_factory=list)
    unsupported_claims: list[dict] = field(default_factory=list)
    unlocated_symbols: list[dict] = field(default_factory=list)
    citation_count: int = 0
    block_count: int = 0

    def as_dict(self) -> dict:
        return {
            "citation_count": self.citation_count,
            "block_count": self.block_count,
            "unresolved": self.unresolved,
            "symbol_mismatch": self.symbol_mismatch,
            "definition_outside_range": self.definition_outside_range,
            "unsupported_claims": self.unsupported_claims,
            "unlocated_symbols": self.unlocated_symbols,
        }


def split_blocks(text: str) -> list[Block]:
    """Split markdown into logical blocks.

    A block starts at a heading, bullet, numbered item, or table row, and
    absorbs following continuation lines. A blank line closes the block.
    """
    starter = re.compile(r"^\s*(?:[-*+]\s|\d+[.)]\s|#{1,6}\s|\|)")
    blocks: list[Block] = []
    current: list[str] = []
    current_start = 1

    def flush() -> None:
        nonlocal current, current_start
        if current and any(line.strip() for line in current):
            blocks.append(
                Block(index=len(blocks), start_line=current_start, text="\n".join(current))
            )
        current = []

    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            flush()
            continue
        if starter.match(line) and current:
            flush()
        if not current:
            current_start = lineno
        current.append(line)
    flush()
    return blocks


def extract_citations(blocks: list[Block]) -> list[Citation]:
    citations: list[Citation] = []
    for block in blocks:
        for match in CITATION_RE.finditer(block.text):
            raw_path = unquote(match.group("path"))
            start = int(match.group("start"))
            end = int(match.group("end") or match.group("start"))
            if end < start:
                start, end = end, start
            citations.append(
                Citation(
                    path=raw_path,
                    start=start,
                    end=end,
                    block_index=block.index,
                    raw=match.group(0),
                )
            )
    return citations


def resolve_path(repo_root: Path, cited: str) -> Path | None:
    """Resolve a cited path against the repository root.

    Accepts repo-relative paths directly. For an absolute or partial path,
    falls back to the longest suffix that exists under the repo root.
    """
    cited = cited.replace("\\", "/").lstrip("/")
    direct = repo_root / cited
    if direct.is_file():
        return direct

    parts = cited.split("/")
    for skip in range(1, len(parts)):
        candidate = repo_root / "/".join(parts[skip:])
        if candidate.is_file():
            return candidate
    return None


def block_identifiers(block: Block) -> list[str]:
    identifiers: list[str] = []
    for token in BACKTICK_RE.findall(block.text):
        token = token.strip()
        if not IDENTIFIER_RE.match(token):
            continue
        leaf = QUALIFIER_SPLIT_RE.split(token)[-1]
        if leaf in FILENAME_LEAVES:
            continue
        if len(leaf) < 3 or leaf in IDENTIFIER_STOPLIST:
            continue
        identifiers.append(leaf)
    return identifiers


def has_citation(block: Block) -> bool:
    return CITATION_RE.search(block.text) is not None


def is_location_claim(block: Block) -> bool:
    lowered = block.text.lower()
    return any(
        marker in block.text or marker in lowered for marker in LOCATION_MARKERS
    )


# Any line that starts a top-level definition, regardless of which symbol it
# names. Used to find which definition a cited line sits inside.
GENERIC_DEFINITION_RE = re.compile(
    r"^\s*(?:pub\s+(?:\(crate\)\s+)?)?"
    r"(?:async\s+)?"
    r"(?:export\s+(?:default\s+)?)?"
    r"(?:func|fn|def|class|type|struct|enum|trait|impl|interface|function)\b"
)


def enclosing_definition_line(lines: list[str], position: int) -> int | None:
    """Line number of the definition that `position` sits inside, if any."""
    best: int | None = None
    for number, line in enumerate(lines, start=1):
        if number > position:
            break
        if GENERIC_DEFINITION_RE.match(line):
            best = number
    return best


def definition_lines(lines: list[str], identifier: str) -> list[int]:
    """Line numbers (1-based) where `identifier` looks like it is defined."""
    escaped = re.escape(identifier)
    keyword_pattern = re.compile(
        r"\b(?:" + "|".join(DEFINITION_KEYWORDS) + r")\s+" + escaped + r"\b"
    )
    # Go methods put the receiver between `func` and the name, so the keyword
    # pattern above never matches them: `func (s *SQLiteStore) Compact() error`.
    go_method_pattern = re.compile(r"\bfunc\s*\([^)]*\)\s*" + escaped + r"\b")
    # Grouped Go/Rust declarations drop the keyword entirely after the first
    # line: `const (\n\tansiReset = "..."\n)` and `var (\n\tErrNotFound = ...`.
    grouped_pattern = re.compile(r"^\s*" + escaped + r"\s*(?:[,:]\s*[\w*\[\]. ]+)?\s*=[^=]")
    return [
        number
        for number, line in enumerate(lines, start=1)
        if keyword_pattern.search(line)
        or go_method_pattern.search(line)
        or grouped_pattern.search(line)
    ]


def audit(repo_root: Path, text: str, window: int) -> Findings:
    blocks = split_blocks(text)
    citations = extract_citations(blocks)
    findings = Findings(citation_count=len(citations), block_count=len(blocks))
    by_index = {block.index: block for block in blocks}

    # Resolve every citation first. The symbol checks below are then decided
    # against the UNION of a block's cited ranges, not each range in isolation.
    # A block routinely carries two citations -- the definition line and the
    # use site -- and judging the use-site citation on its own flags the
    # recommended "defined at X, used at Y" form as a mismatch. A checker that
    # fires on its own documented good example gets switched off.
    resolved_citations: list[tuple[Citation, str, list[str], int, int]] = []
    for citation in citations:
        resolved = resolve_path(repo_root, citation.path)
        if resolved is None:
            findings.unresolved.append(
                {
                    "citation": citation.raw,
                    "path": citation.path,
                    "reason": "file not found under repository root",
                }
            )
            continue

        lines = resolved.read_text(encoding="utf-8", errors="replace").splitlines()
        if citation.start < 1 or citation.end > len(lines):
            findings.unresolved.append(
                {
                    "citation": citation.raw,
                    "path": str(resolved.relative_to(repo_root)).replace("\\", "/"),
                    "reason": f"line range {citation.start}-{citation.end} outside file "
                    f"({len(lines)} lines)",
                }
            )
            continue

        relative = str(resolved.relative_to(repo_root)).replace("\\", "/")
        low = max(1, citation.start - window)
        high = min(len(lines), citation.end + window)
        resolved_citations.append((citation, relative, lines, low, high))

    def citation_covered(
        identifiers: list[str], lines: list[str], low: int, high: int, start: int
    ) -> bool:
        """True if this ONE citation is supported by the block's identifiers.

        Two ways to qualify:

        1. The name appears inside the cited range (the ordinary case).
        2. The cited line sits inside the *body* of a definition of one of
           those names. This is what makes the recommended "defined at X,
           used at Y" form work: the use site legitimately does not repeat
           the function's own name.

        Rule 2 is deliberately scoped to the enclosing definition rather than
        "any other citation in this block". An earlier union-based version
        asked only whether some identifier appeared in *some* cited range of
        the block, which let one correct citation silence every wrong one
        beside it -- including, in this repo's own regression corpus, a
        citation naming a function that exists nowhere in the file.
        """
        excerpt = "\n".join(lines[low - 1 : high])
        if any(identifier in excerpt for identifier in identifiers):
            return True
        enclosing = enclosing_definition_line(lines, start)
        if enclosing is None:
            return False
        return any(
            enclosing in definition_lines(lines, identifier)
            for identifier in identifiers
        )

    def block_defines(block_index: int, path: str, defined_at: list[int]) -> bool:
        """True if any definition line falls inside a cited range of this block."""
        for other, other_path, _, other_low, other_high in resolved_citations:
            if other.block_index != block_index or other_path != path:
                continue
            if any(other_low <= number <= other_high for number in defined_at):
                return True
        return False

    # A block with two citations into the same file would otherwise report the
    # same misplaced definition once per citation.
    reported_definitions: set[tuple[int, str, str]] = set()

    for citation, relative, lines, low, high in resolved_citations:
        block = by_index[citation.block_index]
        identifiers = block_identifiers(block)
        if not identifiers:
            continue
        if not citation_covered(identifiers, lines, low, high, citation.start):
            findings.symbol_mismatch.append(
                {
                    "citation": citation.raw,
                    "path": relative,
                    "identifiers": sorted(set(identifiers)),
                    "reason": "no cited identifier appears within the cited range "
                    f"(+/-{window} lines), and the cited line is not inside a "
                    "definition of any of them",
                }
            )
            continue

        if not is_location_claim(block):
            continue
        for identifier in sorted(set(identifiers)):
            defined_at = definition_lines(lines, identifier)
            if not defined_at:
                continue
            if block_defines(citation.block_index, relative, defined_at):
                continue
            key = (citation.block_index, relative, identifier)
            if key in reported_definitions:
                continue
            reported_definitions.add(key)
            findings.definition_outside_range.append(
                {
                    "citation": citation.raw,
                    "path": relative,
                    "identifier": identifier,
                    "defined_at": defined_at,
                    "reason": "block reads as a location claim, but the definition is "
                    f"at line(s) {defined_at}, outside every cited range in the block",
                }
            )

    # Naming a symbol next to a bare file path is unverifiable: the identifier
    # may well exist somewhere in the repo, so an existence search says nothing
    # about whether it is at the place being described. Attribution is the claim
    # here, and only a line range lets the checks above test it.
    for block in blocks:
        if has_citation(block):
            continue
        bare_paths = [match.group("path") for match in BARE_PATH_RE.finditer(block.text)]
        if not bare_paths:
            continue
        identifiers = block_identifiers(block)
        if not identifiers:
            continue

        # Only an identifier that is actually *defined* in one of the cited
        # files is an attribution claim worth a line number. Without this the
        # check fires on crate names, tool names and commit hashes that happen
        # to sit in backticks next to a path, and chasing that noise costs more
        # than the wrong attributions it would catch.
        attributed: dict[str, str] = {}
        for bare in sorted(set(bare_paths)):
            resolved = resolve_path(repo_root, bare)
            if resolved is None:
                continue
            file_lines = resolved.read_text(encoding="utf-8", errors="replace").splitlines()
            for identifier in identifiers:
                if identifier in attributed:
                    continue
                if definition_lines(file_lines, identifier):
                    attributed[identifier] = bare
        if not attributed:
            continue

        findings.unlocated_symbols.append(
            {
                "line": block.start_line,
                "paths": sorted(set(attributed.values())),
                "identifiers": sorted(attributed),
                "excerpt": block.text.strip()[:200],
            }
        )

    for block in blocks:
        if has_citation(block):
            continue
        lowered = block.text.lower()
        for marker in DELIBERATE_MARKERS:
            if marker in block.text or marker in lowered:
                findings.unsupported_claims.append(
                    {
                        "line": block.start_line,
                        "marker": marker,
                        "kind": "deliberate",
                        "excerpt": block.text.strip()[:200],
                    }
                )
                break
        else:
            for marker in EXISTENCE_MARKERS:
                if marker in block.text or marker in lowered:
                    findings.unsupported_claims.append(
                        {
                            "line": block.start_line,
                            "marker": marker,
                            "kind": "existence",
                            "excerpt": block.text.strip()[:200],
                        }
                    )
                    break

    return findings


def render_human(findings: Findings, strict: bool) -> str:
    lines = [
        f"citations checked: {findings.citation_count}",
        f"blocks scanned:    {findings.block_count}",
        "",
    ]
    if findings.unresolved:
        lines.append(f"FAIL  unresolved citations ({len(findings.unresolved)}):")
        for item in findings.unresolved:
            lines.append(f"  - {item['citation']}: {item['reason']}")
        lines.append("")
    if findings.symbol_mismatch:
        label = "FAIL" if strict else "WARN"
        lines.append(f"{label}  cited symbol not in cited range ({len(findings.symbol_mismatch)}):")
        for item in findings.symbol_mismatch:
            lines.append(f"  - {item['citation']}: expected one of {item['identifiers']}")
        lines.append("")
    if findings.definition_outside_range:
        label = "FAIL" if strict else "WARN"
        lines.append(
            f"{label}  definition outside cited range ({len(findings.definition_outside_range)}):"
        )
        for item in findings.definition_outside_range:
            lines.append(
                f"  - {item['citation']}: `{item['identifier']}` is defined at "
                f"{item['defined_at']}"
            )
        lines.append("")
    if findings.unsupported_claims:
        label = "FAIL" if strict else "WARN"
        lines.append(f"{label}  claims without a citation ({len(findings.unsupported_claims)}):")
        for item in findings.unsupported_claims:
            lines.append(
                f"  - line {item['line']} [{item['kind']}: {item['marker']}] "
                f"{item['excerpt'].splitlines()[0]}"
            )
        lines.append("")
    if findings.unlocated_symbols:
        label = "FAIL" if strict else "WARN"
        lines.append(
            f"{label}  named symbols with no line range ({len(findings.unlocated_symbols)}):"
        )
        for item in findings.unlocated_symbols:
            lines.append(
                f"  - line {item['line']}: {', '.join(item['paths'])} cited without a line "
                f"range while naming {', '.join('`' + i + '`' for i in item['identifiers'])}"
            )
        lines.append("")
    if not (
        findings.unresolved
        or findings.symbol_mismatch
        or findings.definition_outside_range
        or findings.unsupported_claims
        or findings.unlocated_symbols
    ):
        lines.append("OK    no unresolved citations and no uncited claims")
    return "\n".join(lines)


def has_failures(findings: Findings, strict: bool) -> bool:
    if findings.unresolved:
        return True
    if strict and (
        findings.symbol_mismatch
        or findings.definition_outside_range
        or findings.unsupported_claims
        or findings.unlocated_symbols
    ):
        return True
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, help="path to the markdown report to audit")
    parser.add_argument(
        "--repo-root",
        default=None,
        help="repository root used to resolve citations (default: inferred from this script)",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=3,
        help="lines of slack around a cited range when looking for the cited symbol",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="treat symbol mismatches and uncited claims as failures too",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    repo_root = (
        Path(args.repo_root).resolve()
        if args.repo_root
        else Path(__file__).resolve().parents[4]
    )
    report_path = Path(args.report)
    if not report_path.is_file():
        print(f"report not found: {report_path}", file=sys.stderr)
        return 2

    text = report_path.read_text(encoding="utf-8", errors="replace")
    findings = audit(repo_root, text, args.window)

    if args.json:
        print(json.dumps(findings.as_dict(), ensure_ascii=False, indent=2))
    else:
        print(render_human(findings, args.strict))

    return 1 if has_failures(findings, args.strict) else 0


if __name__ == "__main__":
    raise SystemExit(main())
