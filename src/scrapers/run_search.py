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
import os
import sys
import threading

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path so src.* imports work correctly when
# this script is invoked from any working directory.
# ---------------------------------------------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", ".."))
_SRC_DIR = os.path.join(_PROJECT_ROOT, "src")

for _path in (_SRC_DIR, _PROJECT_ROOT):
    if _path not in sys.path:
        sys.path.insert(0, _path)


def _resolve_config_path() -> str:
    """尋找 config.ini：優先使用與腳本同層目錄的路徑，其次為 CWD。"""
    candidates = [
        os.path.join(_PROJECT_ROOT, "config.ini"),
        os.path.join(os.getcwd(), "config.ini"),
        "config.ini",
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    # 回傳預設路徑（即使不存在，ConfigManager 會使用內建預設值）
    return os.path.join(_PROJECT_ROOT, "config.ini")


def _error(code: str, message: str) -> None:
    """輸出 JSON 錯誤結果並以 exit 0 結束（非致命，前端顯示錯誤）。"""
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
        from models.config import ConfigManager
        from services.web_searcher import WebSearcher
    except ImportError as exc:
        _error(code, f"無法匯入搜尋模組: {exc}")

    try:
        config = ConfigManager(_resolve_config_path())
        searcher = WebSearcher(config)
        stop_event = threading.Event()
        raw = searcher.search_info(code, stop_event)
    except Exception as exc:  # noqa: BLE001
        _error(code, f"搜尋時發生例外: {exc}")

    if not raw:
        _error(code, "未找到結果")

    # 將回傳 dict 正規化為 SearchResult 欄位
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
