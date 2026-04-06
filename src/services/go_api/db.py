"""Go CLI 資料庫 API。"""

import json
import logging
import tempfile
from typing import Optional

try:
    from ..go_runner import GoBridgeError, GoCommandRunner, _cleanup_temp_file
except ImportError:
    from services.go_runner import GoBridgeError, GoCommandRunner, _cleanup_temp_file

logger = logging.getLogger(__name__)


def _get_runner(runner: GoCommandRunner | None) -> GoCommandRunner:
    """取得 GoCommandRunner 實例，若未提供則使用全域橋接層的 runner。"""
    if runner is not None:
        return runner
    try:
        from ..go_bridge import get_bridge
    except ImportError:
        from services.go_bridge import get_bridge
    return get_bridge()._runner


def db_get_video(
    code: str,
    data_dir: str = "data/json_db",
    *,
    runner: GoCommandRunner | None = None,
) -> Optional[dict]:
    """取得影片資訊。"""
    r = _get_runner(runner)
    cmd = ["db", "get"]
    if data_dir != "data/json_db":
        cmd.extend(["-data-dir", data_dir])
    cmd.append(code)

    try:
        result = r.run(cmd)
    except GoBridgeError as e:
        # "video not found" 是正常情況（DB 無此番號），直接回傳 None，不噴 ERROR
        if "video not found" in str(e).lower() or "not found" in str(e).lower():
            logger.debug(f"📭 影片不在 DB 中（預期行為）: {code}")
            return None
        logger.error(f"❌ Go CLI 執行失敗 (影片 {code}): {e}")
        raise

    output = result.stdout.strip()
    if not output or output == "null":
        return None

    try:
        data = r.parse_json(output)
    except GoBridgeError as e:
        logger.warning(f"⚠️ JSON 解析失敗 (影片 {code}): {e}")
        raise

    return data if isinstance(data, dict) else None


def db_update_video(
    code: str,
    video: dict,
    data_dir: str = "data/json_db",
    *,
    runner: GoCommandRunner | None = None,
) -> bool:
    """更新影片資訊。"""
    r = _get_runner(runner)
    temp_file = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(video, f, ensure_ascii=False, indent=2)
            temp_file = f.name

        try:
            cmd = ["db", "update"]
            if data_dir != "data/json_db":
                cmd.extend(["-data-dir", data_dir])
            cmd.append("-json")
            cmd.extend([code, temp_file])

            result = r.run(cmd)
            data = r.parse_json(result.stdout)
            if not isinstance(data, dict) or not data.get("success"):
                raise GoBridgeError(f"db update 回傳非預期結果: {result.stdout[:200]}")
            logger.info(f"✅ 影片 {code} 更新成功")
            return True
        except GoBridgeError as e:
            logger.error(f"❌ Go CLI 執行失敗，影片 {code} 更新失敗: {e}")
            return False
        finally:
            _cleanup_temp_file(temp_file, "db_update_video")
    except Exception as e:
        logger.error(f"❌ 更新影片失敗 {code}: {e}")
        return False


def db_delete_video(
    code: str,
    data_dir: str = "data/json_db",
    *,
    runner: GoCommandRunner | None = None,
) -> bool:
    """刪除影片。"""
    r = _get_runner(runner)
    try:
        cmd = ["db", "delete"]
        if data_dir != "data/json_db":
            cmd.extend(["-data-dir", data_dir])
        cmd.append("-json")
        cmd.append(code)

        result = r.run(cmd)
        data = r.parse_json(result.stdout)
        if not isinstance(data, dict) or not data.get("success"):
            raise GoBridgeError(f"db delete 回傳非預期結果: {result.stdout[:200]}")
        logger.info(f"✅ 影片 {code} 刪除成功")
        return True
    except GoBridgeError as e:
        logger.error(f"❌ Go CLI 執行失敗，影片 {code} 刪除失敗: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ 刪除影片失敗 {code}: {e}")
        return False


def db_list_videos(
    data_dir: str = "data/json_db",
    *,
    runner: GoCommandRunner | None = None,
) -> list[str]:
    """列出所有影片番號。"""
    r = _get_runner(runner)
    try:
        cmd = ["db", "list"]
        if data_dir != "data/json_db":
            cmd.extend(["-data-dir", data_dir])

        result = r.run(cmd)
        data = r.parse_json(result.stdout)
        return data if isinstance(data, list) else []
    except GoBridgeError as e:
        error_msg = str(e)
        if "JSON" in error_msg:
            logger.warning(f"⚠️ JSON 解析失敗: {error_msg}")
        else:
            logger.error(f"❌ Go CLI 執行失敗，列出影片失敗: {error_msg}")
        return []
    except Exception as e:
        logger.error(f"❌ 列出影片失敗: {e}")
        return []


def db_get_stats(
    data_dir: str = "data/json_db",
    *,
    runner: GoCommandRunner | None = None,
) -> dict:
    """取得資料庫統計資訊。"""
    r = _get_runner(runner)
    try:
        cmd = ["db", "stats"]
        if data_dir != "data/json_db":
            cmd.extend(["-data-dir", data_dir])

        result = r.run(cmd)
        data = r.parse_json(result.stdout)
        return data if isinstance(data, dict) else {}
    except GoBridgeError as e:
        error_msg = str(e)
        if "JSON" in error_msg:
            logger.warning(f"⚠️ JSON 解析失敗: {error_msg}")
        else:
            logger.error(f"❌ Go CLI 執行失敗，取得統計失敗: {error_msg}")
        return {}
    except Exception as e:
        logger.error(f"❌ 取得統計失敗: {e}")
        return {}


def db_get_all_videos(
    data_dir: str = "data/json_db",
    *,
    runner: GoCommandRunner | None = None,
) -> list[dict]:
    """取得所有影片完整資料。"""
    r = _get_runner(runner)
    try:
        cmd = ["db", "list", "--full"]
        if data_dir != "data/json_db":
            cmd.extend(["-data-dir", data_dir])

        result = r.run(cmd)
        data = r.parse_json(result.stdout)
        return data if isinstance(data, list) else []
    except GoBridgeError as e:
        error_msg = str(e)
        if "JSON" in error_msg:
            logger.warning(f"⚠️ JSON 解析失敗: {error_msg}")
        else:
            logger.error(f"❌ Go CLI 執行失敗，取得所有影片失敗: {error_msg}")
        return []
    except Exception as e:
        logger.error(f"❌ 取得所有影片失敗: {e}")
        return []


def db_compact_journal(
    data_dir: str = "data/json_db",
    *,
    runner: GoCommandRunner | None = None,
) -> bool:
    """合併 journal 到主資料庫。"""
    r = _get_runner(runner)
    try:
        cmd = ["db", "compact"]
        if data_dir != "data/json_db":
            cmd.extend(["-data-dir", data_dir])
        cmd.append("-json")

        result = r.run(cmd)
        data = r.parse_json(result.stdout)
        if not isinstance(data, dict) or not data.get("success"):
            raise GoBridgeError(f"db compact 回傳非預期結果: {result.stdout[:200]}")
        logger.info("✅ Journal 合併成功")
        return True
    except GoBridgeError as e:
        logger.error(f"❌ Go CLI 執行失敗，合併 journal 失敗: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ 合併 journal 失敗: {e}")
        return False


def db_fix_studios(
    data_dir: str = "data/json_db",
    studios_file: str = "studios.json",
    force: bool = False,
    *,
    runner: GoCommandRunner | None = None,
) -> dict:
    """批次修正資料庫內的片商資料，對 UNKNOWN 或空白片商自動識別並更新。"""
    r = _get_runner(runner)
    try:
        cmd = ["db", "fix-studios", "--data-dir", data_dir, "--studios", studios_file, "--json"]
        if force:
            cmd.append("--force")
        result = r.run(cmd, timeout=120)
        data = r.parse_json(result.stdout)
        if not isinstance(data, dict) or not data.get("success"):
            raise GoBridgeError(f"fix-studios 回傳非預期結果: {result.stdout[:200]}")
        logger.info(f"✅ 片商批次修正完成，更新 {data.get('updated', 0)} 筆")
        return data
    except GoBridgeError as e:
        logger.error(f"❌ Go CLI 片商批次修正失敗: {e}")
        return {"success": False, "updated": 0, "error": str(e)}
    except Exception as e:
        logger.error(f"❌ 片商批次修正失敗: {e}")
        return {"success": False, "updated": 0, "error": str(e)}


def db_get_actress(
    actress_id: str,
    data_dir: str = "data/json_db",
    *,
    runner: GoCommandRunner | None = None,
) -> Optional[dict]:
    """取得女優資訊。"""
    r = _get_runner(runner)
    cmd = ["db", "actress-get"]
    if data_dir != "data/json_db":
        cmd.extend(["-data-dir", data_dir])
    cmd.append(actress_id)
    try:
        result = r.run(cmd)
    except GoBridgeError as e:
        if "not found" in str(e).lower():
            return None
        logger.error(f"❌ Go CLI 執行失敗 (女優 {actress_id}): {e}")
        raise
    output = result.stdout.strip()
    if not output or output == "null":
        return None
    try:
        data = r.parse_json(output)
    except GoBridgeError as e:
        logger.warning(f"⚠️ JSON 解析失敗 (女優 {actress_id}): {e}")
        raise
    return data if isinstance(data, dict) else None


def db_update_actress(
    actress_id: str,
    actress: dict,
    data_dir: str = "data/json_db",
    *,
    runner: GoCommandRunner | None = None,
) -> bool:
    """新增或更新女優資訊。"""
    r = _get_runner(runner)
    temp_file = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(actress, f, ensure_ascii=False, indent=2)
            temp_file = f.name
        cmd = ["db", "actress-update"]
        if data_dir != "data/json_db":
            cmd.extend(["-data-dir", data_dir])
        cmd.extend(["-json", actress_id, temp_file])
        result = r.run(cmd)
        data = r.parse_json(result.stdout)
        if not isinstance(data, dict) or not data.get("success"):
            raise GoBridgeError(f"actress-update 回傳非預期結果: {result.stdout[:200]}")
        logger.info(f"✅ 女優 {actress_id} 更新成功")
        return True
    except GoBridgeError as e:
        logger.error(f"❌ Go CLI 執行失敗，女優 {actress_id} 更新失敗: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ 更新女優失敗 {actress_id}: {e}")
        return False
    finally:
        _cleanup_temp_file(temp_file, "db_update_actress")


def db_delete_actress(
    actress_id: str,
    data_dir: str = "data/json_db",
    *,
    runner: GoCommandRunner | None = None,
) -> bool:
    """刪除女優。"""
    r = _get_runner(runner)
    try:
        cmd = ["db", "actress-delete"]
        if data_dir != "data/json_db":
            cmd.extend(["-data-dir", data_dir])
        cmd.extend(["-json", actress_id])
        result = r.run(cmd)
        data = r.parse_json(result.stdout)
        if not isinstance(data, dict) or not data.get("success"):
            raise GoBridgeError(f"actress-delete 回傳非預期結果: {result.stdout[:200]}")
        logger.info(f"✅ 女優 {actress_id} 刪除成功")
        return True
    except GoBridgeError as e:
        logger.error(f"❌ Go CLI 執行失敗，女優 {actress_id} 刪除失敗: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ 刪除女優失敗 {actress_id}: {e}")
        return False


def db_list_actresses(
    data_dir: str = "data/json_db",
    *,
    runner: GoCommandRunner | None = None,
) -> list[str]:
    """列出所有女優 ID。"""
    r = _get_runner(runner)
    try:
        cmd = ["db", "actress-list"]
        if data_dir != "data/json_db":
            cmd.extend(["-data-dir", data_dir])
        result = r.run(cmd)
        data = r.parse_json(result.stdout)
        return data if isinstance(data, list) else []
    except GoBridgeError as e:
        logger.error(f"❌ Go CLI 執行失敗，列出女優失敗: {e}")
        return []
    except Exception as e:
        logger.error(f"❌ 列出女優失敗: {e}")
        return []


def db_get_actress_stats(
    data_dir: str = "data/json_db",
    *,
    runner: GoCommandRunner | None = None,
) -> list[dict]:
    """取得女優統計資訊（按影片數排序）。"""
    r = _get_runner(runner)
    try:
        cmd = ["db", "stats", "--actress"]
        if data_dir != "data/json_db":
            cmd.extend(["-data-dir", data_dir])
        result = r.run(cmd)
        data = r.parse_json(result.stdout)
        return data if isinstance(data, list) else []
    except GoBridgeError as e:
        logger.error(f"❌ Go CLI 女優統計失敗: {e}")
        return []
    except Exception as e:
        logger.error(f"❌ 女優統計失敗: {e}")
        return []


def db_get_studio_stats(
    data_dir: str = "data/json_db",
    *,
    runner: GoCommandRunner | None = None,
) -> list[dict]:
    """取得片商統計資訊（按影片數排序）。"""
    r = _get_runner(runner)
    try:
        cmd = ["db", "stats", "--studio"]
        if data_dir != "data/json_db":
            cmd.extend(["-data-dir", data_dir])
        result = r.run(cmd)
        data = r.parse_json(result.stdout)
        return data if isinstance(data, list) else []
    except GoBridgeError as e:
        logger.error(f"❌ Go CLI 片商統計失敗: {e}")
        return []
    except Exception as e:
        logger.error(f"❌ 片商統計失敗: {e}")
        return []
