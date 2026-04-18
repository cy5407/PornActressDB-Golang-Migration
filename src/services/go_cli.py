"""
輕量級 Go CLI 呼叫器。

直接透過 subprocess 呼叫 classifier 執行檔，無需中介橋接層。
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from typing import Any, Optional

logger = logging.getLogger(__name__)

_CLASSIFIER_EXE = "classifier.exe"
_DEFAULT_DATA_DIR = "data/json_db"
_JSON_SUFFIX = ".json"

_EXE_SEARCH_DONE = False
_EXE_PATH: Optional[str] = None


def _is_executable_file(path: str) -> bool:
    return os.path.isfile(path) and os.access(path, os.X_OK)


def _find_exe_in_dir(base_dir: str) -> Optional[str]:
    for name in (_CLASSIFIER_EXE, "classifier"):
        candidate = os.path.join(base_dir, name)
        if _is_executable_file(candidate):
            return candidate
    return None


def _find_exe_from_path() -> Optional[str]:
    for name in (_CLASSIFIER_EXE, "classifier"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _resolve_exe(exe_path: str | None = None) -> Optional[str]:
    """尋找 classifier 執行檔路徑（快取結果）。"""
    global _EXE_SEARCH_DONE, _EXE_PATH
    if exe_path:
        if _is_executable_file(exe_path):
            return exe_path
        return None

    if _EXE_SEARCH_DONE:
        return _EXE_PATH

    _EXE_SEARCH_DONE = True
    # 1. 優先從此檔案往上找專案根目錄
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    _EXE_PATH = _find_exe_in_dir(root)
    if _EXE_PATH:
        return _EXE_PATH

    # 2. 目前工作目錄
    _EXE_PATH = _find_exe_in_dir(os.getcwd())
    if _EXE_PATH:
        return _EXE_PATH

    # 3. PATH
    _EXE_PATH = _find_exe_from_path()
    if _EXE_PATH:
        return _EXE_PATH

    return None


def is_available(exe_path: str | None = None) -> bool:
    """回傳 classifier 是否可用。"""
    return _resolve_exe(exe_path) is not None


class GoError(Exception):
    """Go CLI 執行錯誤。"""


class GoNotFoundError(GoError):
    """classifier 執行檔不存在。"""


def run(
    args: list[str], *, timeout: int = 30, exe_path: str | None = None
) -> dict[str, Any]:
    """
    執行 classifier 指令，回傳解析後的 JSON 輸出。

    Raises:
        GoNotFoundError: 找不到 classifier。
        GoError: 執行失敗或 JSON 解析錯誤。
    """
    exe = _resolve_exe(exe_path)
    if not exe:
        raise GoNotFoundError("找不到 classifier 執行檔")

    cmd = [exe] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
        )
    except FileNotFoundError as e:
        raise GoNotFoundError(f"classifier 執行失敗: {e}") from e
    except subprocess.TimeoutExpired as e:
        raise GoError(f"classifier 執行逾時 (>{timeout}s): {args}") from e

    stdout = result.stdout.strip()
    stderr = result.stderr.strip()

    if result.returncode != 0:
        msg = stderr or stdout or f"exit code {result.returncode}"
        raise GoError(f"classifier 回傳錯誤 (exit {result.returncode}): {msg}")

    if not stdout:
        return {}

    try:
        return json.loads(stdout)
    except json.JSONDecodeError as e:
        raise GoError(f"JSON 解析失敗: {e}\n輸出: {stdout[:200]}") from e


# ---------------------------------------------------------------------------
# 掃描 / 番號提取
# ---------------------------------------------------------------------------

def extract_code(filename: str) -> Optional[str]:
    """從檔案名稱提取番號，失敗回傳 None。"""
    try:
        data = run(["scan", "-extract", filename])
        return data.get("code") or None
    except GoError as e:
        logger.debug(f"Go 番號提取失敗: {e}")
        return None


# ---------------------------------------------------------------------------
# 片商識別
# ---------------------------------------------------------------------------

def identify_studio(code: str) -> Optional[str]:
    """識別番號所屬片商，失敗回傳 None。"""
    try:
        data = run(["identify", code])
        studio = data.get("studio", "UNKNOWN")
        return studio if studio and studio != "UNKNOWN" else None
    except GoError as e:
        logger.debug(f"Go 片商識別失敗: {e}")
        return None


def normalize_studio_name(
    studio_name: str,
    video_code: str | None = None,
    rules_file: str = "studios.json",
    *,
    exe_path: str | None = None,
) -> Optional[str]:
    """透過 Go CLI 標準化片商名稱；失敗回傳 None。"""
    args = ["identify", "-normalize"]
    if studio_name:
        args.extend(["-studio", studio_name])
    if video_code:
        args.extend(["-code", video_code])
    if rules_file and rules_file != "studios.json":
        args.extend(["-rules", rules_file])
    try:
        data = run(args, exe_path=exe_path)
        studio = data.get("studio", "UNKNOWN")
        return studio if studio and studio != "UNKNOWN" else None
    except GoError as e:
        logger.debug(f"Go 片商標準化失敗: {e}")
        return None


# ---------------------------------------------------------------------------
# 資料庫操作
# ---------------------------------------------------------------------------

def db_get_video(code: str, data_dir: str = _DEFAULT_DATA_DIR) -> Optional[dict]:
    """取得影片資訊，找不到回傳 None。"""
    try:
        cmd = ["db", "get"]
        if data_dir != _DEFAULT_DATA_DIR:
            cmd.extend(["-data-dir", data_dir])
        cmd.append(code)
        return run(cmd)
    except GoError as e:
        if "not found" in str(e).lower():
            return None
        logger.error(f"db_get_video 失敗: {e}")
        raise


def db_update_video(code: str, video: dict, data_dir: str = _DEFAULT_DATA_DIR) -> bool:
    """更新影片資訊，成功回傳 True。"""
    temp_file = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=_JSON_SUFFIX, delete=False, encoding="utf-8"
        ) as f:
            json.dump(video, f, ensure_ascii=False, indent=2)
            temp_file = f.name

        cmd = ["db", "update"]
        if data_dir != _DEFAULT_DATA_DIR:
            cmd.extend(["-data-dir", data_dir])
        cmd.extend([code, temp_file])
        run(cmd)
        return True
    except GoError as e:
        logger.error(f"db_update_video 失敗: {e}")
        return False
    finally:
        if temp_file and os.path.exists(temp_file):
            os.unlink(temp_file)


def db_delete_video(code: str, data_dir: str = _DEFAULT_DATA_DIR) -> bool:
    """刪除影片，成功回傳 True。"""
    try:
        cmd = ["db", "delete"]
        if data_dir != _DEFAULT_DATA_DIR:
            cmd.extend(["-data-dir", data_dir])
        cmd.append(code)
        run(cmd)
        return True
    except GoError as e:
        logger.error(f"db_delete_video 失敗: {e}")
        return False


def db_get_all_videos(data_dir: str = _DEFAULT_DATA_DIR) -> list[dict]:
    """取得所有影片清單。"""
    try:
        cmd = ["db", "list", "--full"]
        if data_dir != _DEFAULT_DATA_DIR:
            cmd.extend(["-data-dir", data_dir])
        data = run(cmd)
        if isinstance(data, list):
            return data
        return data.get("videos", []) if isinstance(data, dict) else []
    except GoError as e:
        logger.error(f"db_get_all_videos 失敗: {e}")
        return []


def db_compact_journal(data_dir: str = _DEFAULT_DATA_DIR) -> bool:
    """合併 journal 到主資料庫。"""
    try:
        cmd = ["db", "compact", "-json"]
        if data_dir != _DEFAULT_DATA_DIR:
            cmd.extend(["-data-dir", data_dir])
        data = run(cmd)
        return bool(data.get("success", True)) if isinstance(data, dict) else True
    except GoError as e:
        logger.error(f"db_compact_journal 失敗: {e}")
        return False


# ---------------------------------------------------------------------------
# 快取操作
# ---------------------------------------------------------------------------

def cache_get(key: str, cache_dir: str = "cache") -> Optional[bytes]:
    """從 Go 快取讀取值，找不到或失敗時回傳 None。"""
    import base64
    try:
        data = run(["cache", "get", "-cache-dir", cache_dir, key])
        if not data.get("success"):
            return None
        encoded = data.get("value")
        if encoded is None:
            return None
        return base64.b64decode(encoded)
    except Exception as e:
        logger.debug(f"cache_get 失敗: {e}")
        return None


def cache_set(key: str, value: bytes, ttl_hours: int = 24, cache_dir: str = "cache") -> bool:
    """將值寫入 Go 快取，成功回傳 True。"""
    import base64
    try:
        encoded = base64.b64encode(value).decode("ascii")
        data = run([
            "cache", "set",
            "-cache-dir", cache_dir,
            "-ttl-hours", str(ttl_hours),
            key, encoded,
        ])
        return bool(data.get("success"))
    except GoError as e:
        logger.debug(f"cache_set 失敗: {e}")
        return False


def cache_delete(key: str, cache_dir: str = "cache") -> bool:
    """從 Go 快取刪除條目，成功回傳 True。"""
    try:
        data = run(["cache", "delete", "-cache-dir", cache_dir, key])
        return bool(data.get("success"))
    except GoError as e:
        logger.debug(f"cache_delete 失敗: {e}")
        return False


def cache_get_stats(cache_dir: str = "cache") -> dict:
    """取得快取統計資訊。"""
    try:
        data = run(["cache", "stats", "-cache-dir", cache_dir])
        return data if isinstance(data, dict) else {}
    except GoError as e:
        logger.debug(f"cache_get_stats 失敗: {e}")
        return {}


def cache_prune(
    cache_dir: str = "cache",
    ttl_days: int = 7,
    max_size_mb: int = 500,
    min_keep: int = 100,
    dry_run: bool = False,
) -> dict:
    """清理過期或超大的快取。"""
    try:
        cmd = [
            "cache", "prune",
            "-cache-dir", cache_dir,
            "-ttl-days", str(ttl_days),
            "-max-size", str(max_size_mb),
            "-min-keep", str(min_keep),
        ]
        if dry_run:
            cmd.append("-dry-run")
        data = run(cmd)
        return data if isinstance(data, dict) else {}
    except GoError as e:
        logger.debug(f"cache_prune 失敗: {e}")
        return {}


def cache_clear(cache_dir: str = "cache", dry_run: bool = False) -> dict:
    """清空所有快取。"""
    try:
        cmd = ["cache", "clear", "-cache-dir", cache_dir]
        if dry_run:
            cmd.append("-dry-run")
        else:
            cmd.append("-confirm")
        data = run(cmd)
        return data if isinstance(data, dict) else {}
    except GoError as e:
        logger.debug(f"cache_clear 失敗: {e}")
        return {}



def db_backup_create(data_dir: str = _DEFAULT_DATA_DIR) -> dict:
    try:
        cmd = ["db", "backup-create"]
        if data_dir != _DEFAULT_DATA_DIR:
            cmd.extend(["-data-dir", data_dir])
        return run(cmd)
    except GoError as e:
        logger.error(f"db_backup_create 失敗: {e}")
        return {}


def db_backup_list(data_dir: str = _DEFAULT_DATA_DIR) -> list:
    try:
        cmd = ["db", "backup-list"]
        if data_dir != _DEFAULT_DATA_DIR:
            cmd.extend(["-data-dir", data_dir])
        data = run(cmd)
        if isinstance(data, dict):
            backups = data.get("backups")
            return backups if isinstance(backups, list) else []
        return data if isinstance(data, list) else []
    except GoError as e:
        logger.error(f"db_backup_list 失敗: {e}")
        return []


def db_backup_restore(backup_file: str, data_dir: str = _DEFAULT_DATA_DIR) -> dict:
    try:
        cmd = ["db", "backup-restore", "-backup-path", backup_file]
        if data_dir != _DEFAULT_DATA_DIR:
            cmd.extend(["-data-dir", data_dir])
        return run(cmd)
    except GoError as e:
        logger.error(f"db_backup_restore 失敗: {e}")
        return {}


def db_backup_cleanup(data_dir: str = _DEFAULT_DATA_DIR, **kwargs) -> int:
    try:
        cmd = ["db", "backup-cleanup"]
        if data_dir != _DEFAULT_DATA_DIR:
            cmd.extend(["-data-dir", data_dir])
        if "days" in kwargs:
            cmd.extend(["-days", str(kwargs["days"])])
        if "max_count" in kwargs:
            cmd.extend(["-max-count", str(kwargs["max_count"])])
        data = run(cmd)
        return int(data.get("deleted", 0)) if isinstance(data, dict) else 0
    except GoError as e:
        logger.error(f"db_backup_cleanup 失敗: {e}")
        return 0


def db_get_actress(name: str, data_dir: str = _DEFAULT_DATA_DIR) -> Optional[dict]:
    try:
        cmd = ["db", "actress-get", name]
        if data_dir != _DEFAULT_DATA_DIR:
            cmd.extend(["-data-dir", data_dir])
        return run(cmd)
    except GoError as e:
        if "not found" in str(e).lower():
            return None
        logger.error(f"db_get_actress 失敗: {e}")
        return None


def db_update_actress(name: str, data: dict, data_dir: str = _DEFAULT_DATA_DIR) -> bool:
    temp_file = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=_JSON_SUFFIX, delete=False, encoding="utf-8"
        ) as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            temp_file = f.name

        cmd = ["db", "actress-update", name, temp_file]
        if data_dir != _DEFAULT_DATA_DIR:
            cmd.extend(["-data-dir", data_dir])
        run(cmd)
        return True
    except GoError as e:
        logger.error(f"db_update_actress 失敗: {e}")
        return False
    finally:
        if temp_file and os.path.exists(temp_file):
            os.unlink(temp_file)


def db_delete_actress(name: str, data_dir: str = _DEFAULT_DATA_DIR) -> bool:
    try:
        cmd = ["db", "actress-delete", name]
        if data_dir != _DEFAULT_DATA_DIR:
            cmd.extend(["-data-dir", data_dir])
        run(cmd)
        return True
    except GoError as e:
        logger.error(f"db_delete_actress 失敗: {e}")
        return False


# ---------------------------------------------------------------------------
# 檔案移動操作
# ---------------------------------------------------------------------------

def move_file(
    source: str,
    destination: str,
    strategy: str = "skip",
    exe_path: str | None = None,
) -> dict:
    """移動單個檔案，回傳操作結果 dict。"""
    try:
        data = run(
            ["move", "-src", source, "-dst", destination, "-strategy", strategy],
            exe_path=exe_path,
        )
        if isinstance(data, dict):
            return data
        return {"success": True, "source": source, "destination": destination, "error": None, "skipped": False, "renamed": None}
    except GoError as e:
        return {"success": False, "source": source, "destination": destination, "error": str(e), "skipped": False, "renamed": None}


def move_dir(
    source: str,
    destination: str,
    strategy: str = "skip",
    exe_path: str | None = None,
) -> dict:
    """移動整個目錄，回傳操作結果 dict。"""
    try:
        data = run(
            ["move", "-src", source, "-dst", destination, "-strategy", strategy, "-dir"],
            exe_path=exe_path,
        )
        if isinstance(data, dict):
            return data
        return {"success": True, "source": source, "destination": destination, "error": None, "skipped": False}
    except GoError as e:
        return {"success": False, "source": source, "destination": destination, "error": str(e), "skipped": False}


def batch_move(
    items: list[dict],
    strategy: str = "skip",
    log_dir: str = "logs",
    exe_path: str | None = None,
) -> dict:
    """批次移動檔案，items 為 [{"source": ..., "destination": ...}, ...]。"""
    temp_file = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=_JSON_SUFFIX, delete=False, encoding="utf-8"
        ) as f:
            json.dump(items, f, ensure_ascii=False)
            temp_file = f.name
        data = run(
            ["move", "-batch", temp_file, "-strategy", strategy, "-log-dir", log_dir],
            exe_path=exe_path,
        )
        if isinstance(data, dict):
            return data
        return {"total": len(items), "success": 0, "failed": len(items), "skipped": 0, "results": []}
    except GoError as e:
        return {"total": len(items), "success": 0, "failed": len(items), "skipped": 0, "error": str(e), "results": []}
    finally:
        if temp_file and os.path.exists(temp_file):
            os.unlink(temp_file)


def rollback(
    operation_id: str, log_dir: str = "logs", exe_path: str | None = None
) -> dict:
    """回滾指定操作 ID。"""
    try:
        data = run(
            ["history", "rollback", operation_id, "-log-dir", log_dir],
            exe_path=exe_path,
        )
        return data if isinstance(data, dict) else {}
    except GoError as e:
        return {"success": False, "error": str(e)}


def rollback_last(log_dir: str = "logs", exe_path: str | None = None) -> dict:
    """回滾最近一次操作。"""
    try:
        data = run(
            ["history", "rollback", "--last", "-log-dir", log_dir],
            exe_path=exe_path,
        )
        return data if isinstance(data, dict) else {}
    except GoError as e:
        return {"success": False, "error": str(e)}


def list_operations(
    limit: int = 10, log_dir: str = "logs", exe_path: str | None = None
) -> list[dict]:
    """列出最近操作記錄。"""
    try:
        data = run(
            ["history", "list", "-log-dir", log_dir, "-limit", str(limit)],
            exe_path=exe_path,
        )
        return data if isinstance(data, list) else []
    except GoError as e:
        logger.debug(f"list_operations 失敗: {e}")
        return []
