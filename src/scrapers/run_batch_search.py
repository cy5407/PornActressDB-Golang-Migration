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


def _resolve_config_path() -> str:
    candidates = [
        os.path.join(_PROJECT_ROOT, "config.ini"),
        os.path.join(os.getcwd(), "config.ini"),
        "config.ini",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return os.path.join(_PROJECT_ROOT, "config.ini")


# ---------------------------------------------------------------------------
# Thread-local WebSearcher：每個 thread 只建立一次，後續重用
# ---------------------------------------------------------------------------
_thread_local = threading.local()


def _get_searcher():
    if not hasattr(_thread_local, "searcher"):
        from models.config import ConfigManager
        from services.web_searcher import WebSearcher
        _thread_local.searcher = WebSearcher(ConfigManager(_resolve_config_path()))
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
    }


def search_one(code: str) -> dict:
    try:
        searcher = _get_searcher()
        stop_event = threading.Event()
        raw = searcher.search_info(code, stop_event)
        if not raw:
            return {"code": code, "title": "", "studio": "", "release_date": "",
                    "url": "", "actresses": [], "method": "", "error": "未找到結果"}
        return _normalize(raw, code)
    except Exception as exc:  # noqa: BLE001
        return {"code": code, "title": "", "studio": "", "release_date": "",
                "url": "", "actresses": [], "method": "", "error": str(exc)}


def main() -> None:
    raw_input = sys.stdin.read()
    try:
        data = json.loads(raw_input)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"JSON 輸入解析失敗: {e}\n")
        sys.exit(1)

    codes: list[str] = data.get("codes", [])
    workers: int = max(1, int(data.get("workers", 15)))

    if not codes:
        sys.exit(0)

    # 串流輸出：每筆完成即立即 print，Go 端逐行讀取並發送 Wails 事件
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(search_one, c): c for c in codes}
        for future in as_completed(futures):
            result = future.result()
            print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
