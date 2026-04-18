#!/usr/bin/env python3
"""
run_batch_search.py - 批次搜尋版本，大幅降低 Python 啟動次數。

Input (stdin):  JSON {"codes": ["ABC-123", ...], "workers": 15}
Output (stdout): JSON Lines - 每筆結果立即輸出一行，格式與 SearchResult 相同：
                 {"code":"...", "title":"...", ...}\n

設計原則：
- 啟動一次 Python，内部用 ThreadPoolExecutor 並發
- 每個 thread 有自己的 WebSearcher（避免 rate limiter 跨 thread 串行化）
- 結果串流輸出（as_completed），讓 Go 端即時發 Wails 事件
"""

from __future__ import annotations

import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------------------------------------------------------------------------
# sys.path 設定
# ---------------------------------------------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", ".."))
_SRC_DIR = os.path.join(_PROJECT_ROOT, "src")

for _path in (_SRC_DIR, _PROJECT_ROOT):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from scrapers.run_search import (  # noqa: E402
    DEFAULT_CONFIG_FILE,
    DEFAULT_SOURCE_MODE,
    _normalize_source_mode,
    _search_with_mode,
)


def _resolve_config_path() -> str:
    candidates = [
        os.path.join(_PROJECT_ROOT, DEFAULT_CONFIG_FILE),
        os.path.join(os.getcwd(), DEFAULT_CONFIG_FILE),
        DEFAULT_CONFIG_FILE,
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return os.path.join(_PROJECT_ROOT, DEFAULT_CONFIG_FILE)


# ---------------------------------------------------------------------------
# Thread-local WebSearcher：每個 thread 只建立一次，後續重用
# ---------------------------------------------------------------------------
_thread_local = threading.local()


def _get_searcher():
    """每個 thread 只建立一次 WebSearcher，並停用人工 rate limit。

    批次模式的設計原則：
    - 每個 thread 有獨立 SafeSearcher，各自的 last_request_time 互不干擾
    - SafeSearcher 的 rate limiter 是為了防止「同一 session 高頻請求」
    - 批次模式下每個 thread 處理 ≤5 個 code，自然的 HTTP 往返時間已足夠緩衝
    - 停用後不影響其他 thread；AV-WIKI 自然 TCP back-pressure 仍有保護
    """
    if not hasattr(_thread_local, "searcher"):
        from models.config import ConfigManager
        from services.web_searcher import WebSearcher
        searcher = WebSearcher(ConfigManager(_resolve_config_path()))
        # 停用 rate limiter：批次模式各 thread 獨立，人工 sleep 只會浪費時間
        searcher.japanese_searcher.config.min_interval = 0.0
        searcher.japanese_searcher.config.max_interval = 0.0
        searcher.safe_searcher.config.min_interval = 0.0
        searcher.safe_searcher.config.max_interval = 0.0
        _thread_local.searcher = searcher
    return _thread_local.searcher


def _normalize(raw: dict, code: str) -> dict:
    actresses: list[str] = raw.get("actresses") or []
    if isinstance(actresses, str):
        actresses = [a.strip() for a in actresses.split(",") if a.strip()]
    return {
        "code": raw.get("code") or code,
        "title": raw.get("title") or "",
        "studio": raw.get("studio") or "",
        "release_date": raw.get("release_date") or raw.get("releaseDate") or "",
        "url": raw.get("url") or "",
        "actresses": actresses,
        "method": raw.get("search_method") or raw.get("method") or "",
        "error": "",
        "error_kind": raw.get("error_kind") or "",
    }


def _build_error_result(code: str, message: str, error_kind: str) -> dict:
    return {
        "code": code,
        "title": "",
        "studio": "",
        "release_date": "",
        "url": "",
        "actresses": [],
        "method": "",
        "error": message,
        "error_kind": error_kind,
    }


def search_one(code: str, source_mode: str = DEFAULT_SOURCE_MODE) -> dict:
    try:
        searcher = _get_searcher()
        stop_event = threading.Event()
        raw = _search_with_mode(searcher, code, stop_event, source_mode)
        if not raw:
            return _build_error_result(code, "未找到結果", "not_found")
        if raw.get("search_status") == "search_error":
            return _build_error_result(
                code,
                raw.get("search_error_reason") or "搜尋來源發生錯誤",
                "error",
            )
        return _normalize(raw, code)
    except Exception as exc:  # noqa: BLE001
        return _build_error_result(code, str(exc), "error")


def main() -> None:
    raw_input = sys.stdin.read()
    try:
        data = json.loads(raw_input)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"JSON 輸入解析失敗: {e}\n")
        sys.exit(1)

    codes: list[str] = data.get("codes", [])
    workers: int = max(1, int(data.get("workers", 20)))
    try:
        source_mode = _normalize_source_mode(data.get("source_mode"))
    except ValueError as e:
        sys.stderr.write(f"{e}\n")
        sys.exit(1)

    if not codes:
        sys.exit(0)

    actual_workers = min(workers, len(codes))

    # 串流輸出：每筆完成即立即 print，Go 端逐行讀取並發送 Wails 事件
    # thread-local _get_searcher() 讓各 thread 並行初始化（GIL 在 I/O 段自動讓步）
    with ThreadPoolExecutor(max_workers=actual_workers) as executor:
        futures = {
            executor.submit(search_one, c, source_mode): c for c in codes
        }
        for future in as_completed(futures):
            result = future.result()
            print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
