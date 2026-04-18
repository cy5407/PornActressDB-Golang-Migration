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
from datetime import UTC, datetime

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


DEFAULT_SOURCE_MODE = "cascade"
DEFAULT_CONFIG_FILE = "config.ini"
SOURCE_MODE_ALIASES = {
    "": DEFAULT_SOURCE_MODE,
    DEFAULT_SOURCE_MODE: DEFAULT_SOURCE_MODE,
    "all": DEFAULT_SOURCE_MODE,
    "default": DEFAULT_SOURCE_MODE,
    "avwiki": "avwiki",
    "av-wiki": "avwiki",
    "avwiki_only": "avwiki",
    "javdb": "javdb",
    "javdb_only": "javdb",
}


def _resolve_config_path() -> str:
    """尋找 config.ini：優先使用與腳本同層目錄的路徑，其次為 CWD。"""
    candidates = [
        os.path.join(_PROJECT_ROOT, DEFAULT_CONFIG_FILE),
        os.path.join(os.getcwd(), DEFAULT_CONFIG_FILE),
        DEFAULT_CONFIG_FILE,
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    # 回傳預設路徑（即使不存在，ConfigManager 會使用內建預設值）
    return os.path.join(_PROJECT_ROOT, DEFAULT_CONFIG_FILE)


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


def _normalize_source_mode(source_mode: str | None) -> str:
    normalized = SOURCE_MODE_ALIASES.get((source_mode or "").strip().lower())
    if normalized is None:
        raise ValueError(f"不支援的搜尋來源模式: {source_mode}")
    return normalized


def _search_with_mode(searcher, code: str, stop_event: threading.Event, source_mode: str):
    normalized = _normalize_source_mode(source_mode)
    if normalized == "avwiki":
        return searcher.search_avwiki_only(code, stop_event)
    if normalized == "javdb":
        return searcher.search_javdb_only(code, stop_event)
    return searcher.search_info(code, stop_event)


def _resolve_source_status_fields(source_mode: str) -> tuple[str, str] | None:
    normalized = _normalize_source_mode(source_mode)
    if normalized == "avwiki":
        return "avwiki_actress_status", "avwiki_last_search_date"
    if normalized == "javdb":
        return "javdb_actress_status", "javdb_last_search_date"
    return None


def _determine_source_status(raw: dict | None) -> str:
    if raw and raw.get("search_status") == "search_error":
        return "error"

    actresses = []
    if raw:
        actresses = raw.get("actresses") or []
        if isinstance(actresses, str):
            actresses = [a.strip() for a in actresses.split(",") if a.strip()]

    return "found" if actresses else "not_found"


def _update_source_search_status(
    code: str,
    raw: dict | None,
    source_mode: str,
    db=None,
    now: str | None = None,
) -> None:
    try:
        field_names = _resolve_source_status_fields(source_mode)
        if field_names is None:
            return

        status_field, date_field = field_names
        timestamp = now or datetime.now(UTC).isoformat()

        if db is None:
            from models.incremental_json_database import IncrementalJSONDB

            db = IncrementalJSONDB(os.path.join(_PROJECT_ROOT, "data", "json_db"))

        existing = db.get_video_info(code)
        if not existing:
            from models.json_types import get_empty_video

            minimal_video = get_empty_video()
            minimal_video["code"] = code
            minimal_video["created_at"] = timestamp
            minimal_video["updated_at"] = timestamp
            db.add_or_update_video(code, minimal_video)

        db.update_video(
            code,
            {
                status_field: _determine_source_status(raw),
                date_field: timestamp,
                "updated_at": timestamp,
            },
        )
    except Exception:
        return


def main() -> None:
    if len(sys.argv) < 2:
        print(
            json.dumps(
                {"code": "", "error": "Usage: run_search.py <video_code> [source_mode]"}
            ),
            file=sys.stdout,
        )
        sys.exit(1)

    code = sys.argv[1].strip()
    source_mode = sys.argv[2].strip() if len(sys.argv) >= 3 else DEFAULT_SOURCE_MODE
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
        raw = _search_with_mode(searcher, code, stop_event, source_mode)
        _update_source_search_status(code, raw, source_mode)
    except Exception as exc:  # noqa: BLE001
        _update_source_search_status(
            code,
            {
                "actresses": [],
                "search_status": "search_error",
                "search_error_reason": str(exc),
            },
            source_mode,
        )
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
