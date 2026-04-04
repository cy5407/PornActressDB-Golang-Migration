"""Go CLI 資料庫 API。"""

import json
import logging
import tempfile
from typing import Optional

try:
    from src.services.go_runner import GoBridgeError
except ImportError:
    from services.go_runner import GoBridgeError

logger = logging.getLogger(__name__)


def _cleanup_temp_file(path: str | None, context: str) -> None:
    """延遲匯入清理 helper，避免循環依賴。"""
    try:
        from src.services.go_bridge import _cleanup_temp_file as cleanup_temp_file
    except ImportError:
        from services.go_bridge import _cleanup_temp_file as cleanup_temp_file

    cleanup_temp_file(path, context)


def _get_bridge():
    """延遲匯入 bridge，避免循環依賴。"""
    try:
        from src.services.go_bridge import get_bridge
    except ImportError:
        from services.go_bridge import get_bridge

    return get_bridge()


def db_get_video(code: str, data_dir: str = "data/json_db") -> Optional[dict]:
    """取得影片資訊。"""
    bridge = _get_bridge()
    cmd = ["db", "get"]
    if data_dir != "data/json_db":
        cmd.extend(["-data-dir", data_dir])
    cmd.append(code)

    try:
        result = bridge._run_command(cmd)
    except GoBridgeError as e:
        logger.error(f"❌ Go CLI 執行失敗 (影片 {code}): {e}")
        raise

    output = result.stdout.strip()
    if not output or output == "null":
        return None

    try:
        data = bridge._parse_json(output)
    except GoBridgeError as e:
        logger.warning(f"⚠️ JSON 解析失敗 (影片 {code}): {e}")
        raise

    return data if isinstance(data, dict) else None


def db_update_video(code: str, video: dict, data_dir: str = "data/json_db") -> bool:
    """更新影片資訊。"""
    bridge = _get_bridge()
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

            result = bridge._run_command(cmd)
            data = bridge._parse_json(result.stdout)
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


def db_delete_video(code: str, data_dir: str = "data/json_db") -> bool:
    """刪除影片。"""
    bridge = _get_bridge()
    try:
        cmd = ["db", "delete"]
        if data_dir != "data/json_db":
            cmd.extend(["-data-dir", data_dir])
        cmd.append("-json")
        cmd.append(code)

        result = bridge._run_command(cmd)
        data = bridge._parse_json(result.stdout)
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


def db_list_videos(data_dir: str = "data/json_db") -> list[str]:
    """列出所有影片番號。"""
    bridge = _get_bridge()
    try:
        cmd = ["db", "list"]
        if data_dir != "data/json_db":
            cmd.extend(["-data-dir", data_dir])

        result = bridge._run_command(cmd)
        data = bridge._parse_json(result.stdout)
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


def db_get_stats(data_dir: str = "data/json_db") -> dict:
    """取得資料庫統計資訊。"""
    bridge = _get_bridge()
    try:
        cmd = ["db", "stats"]
        if data_dir != "data/json_db":
            cmd.extend(["-data-dir", data_dir])

        result = bridge._run_command(cmd)
        data = bridge._parse_json(result.stdout)
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


def db_compact_journal(data_dir: str = "data/json_db") -> bool:
    """合併 journal 到主資料庫。"""
    bridge = _get_bridge()
    try:
        cmd = ["db", "compact"]
        if data_dir != "data/json_db":
            cmd.extend(["-data-dir", data_dir])
        cmd.append("-json")

        result = bridge._run_command(cmd)
        data = bridge._parse_json(result.stdout)
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
