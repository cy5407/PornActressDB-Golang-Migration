#!/usr/bin/env python3
"""
run_search.py - Wails backend subprocess wrapper for video metadata search.

Usage:
    python run_search.py <video_code>

Output:
    JSON object printed to stdout, compatible with backend.SearchResult:
    {
        "code": "STARS-707",
        "title": "...",
        "studio": "...",
        "release_date": "2023-01-01",
        "url": "https://...",
        "actresses": ["...", "..."],
        "method": "AV-WIKI",
        "error": ""          <- present only on failure
    }

Exit codes:
    0  Search succeeded (result may still contain "error" if not found)
    1  Fatal error (malformed arguments, import failure, etc.)
"""

from __future__ import annotations

import json
import sys
import os

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path so src.* imports work correctly when
# this script is invoked from any working directory.
# ---------------------------------------------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def _error(code: str, message: str) -> None:
    """Print a JSON error result and exit with code 0 (non-fatal, frontend shows the error)."""
    result = {
        "code": code,
        "title": "",
        "studio": "",
        "release_date": "",
        "url": "",
        "actresses": [],
        "method": "",
        "error": message,
    }
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0)


def main() -> None:
    if len(sys.argv) < 2:
        print(
            json.dumps({"code": "", "error": "Usage: run_search.py <video_code>"}),
            file=sys.stdout,
        )
        sys.exit(1)

    code = sys.argv[1].strip()
    if not code:
        _error("", "番號不得為空")

    try:
        from src.services.web_searcher import WebSearcher
    except ImportError as exc:
        _error(code, f"無法匯入 WebSearcher: {exc}")

    try:
        searcher = WebSearcher()
        raw = searcher.search(code)
    except Exception as exc:  # noqa: BLE001
        _error(code, f"搜尋時發生例外: {exc}")

    if not raw:
        _error(code, "未找到結果")

    # Normalise the result dict into SearchResult fields
    actresses: list[str] = raw.get("actresses") or []
    if isinstance(actresses, str):
        actresses = [a.strip() for a in actresses.split(",") if a.strip()]

    result = {
        "code": raw.get("code") or code,
        "title": raw.get("title") or "",
        "studio": raw.get("studio") or "",
        "release_date": raw.get("release_date") or raw.get("releaseDate") or "",
        "url": raw.get("url") or "",
        "actresses": actresses,
        "method": raw.get("search_method") or raw.get("method") or "",
        "error": "",
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
