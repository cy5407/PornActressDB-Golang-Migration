"""Go CLI 片商識別 API。"""

import logging
import tempfile

logger = logging.getLogger(__name__)


def _cleanup_temp_file(path: str | None, context: str) -> None:
    try:
        from ..go_bridge import _cleanup_temp_file as cleanup_temp_file
    except ImportError:
        from services.go_bridge import _cleanup_temp_file as cleanup_temp_file

    cleanup_temp_file(path, context)


def _get_bridge():
    try:
        from ..go_bridge import get_bridge
    except ImportError:
        from services.go_bridge import get_bridge

    return get_bridge()


def identify_studio(code: str, check_major: bool = False) -> dict:
    """識別番號所屬片商。"""
    bridge = _get_bridge()
    try:
        cmd = ["identify", code]
        if check_major:
            cmd.insert(1, "-major")

        result = bridge._run_command(cmd)
        return bridge._parse_json(result.stdout)
    except Exception as e:
        logger.error(f"❌ 識別片商失敗: {e}")
        return {"code": code, "studio": "UNKNOWN"}


def identify_studios_batch(codes: list[str], check_major: bool = False) -> list[dict]:
    """批次識別番號所屬片商。"""
    bridge = _get_bridge()
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write("\n".join(codes))
            temp_file = f.name

        try:
            cmd = ["identify", "-batch", temp_file]
            if check_major:
                cmd.insert(1, "-major")

            result = bridge._run_command(cmd)
            return bridge._parse_json(result.stdout)
        finally:
            _cleanup_temp_file(temp_file, "identify_studios_batch")
    except Exception as e:
        logger.error(f"❌ 批次識別片商失敗: {e}")
        return []


def list_studios() -> list[str]:
    """列出所有片商。"""
    bridge = _get_bridge()
    try:
        result = bridge._run_command(["identify", "-list", "-json"])
        data = bridge._parse_json(result.stdout)
        if not isinstance(data, list):
            return []
        return [
            item["studio"]
            for item in data
            if isinstance(item, dict) and isinstance(item.get("studio"), str)
        ]
    except Exception as e:
        logger.error(f"❌ 列出片商失敗: {e}")
        return []


def get_studio_prefixes(studio_name: str) -> list[str]:
    """取得指定片商的所有前綴。"""
    bridge = _get_bridge()
    try:
        result = bridge._run_command(["identify", "-prefixes", "-json", studio_name])
        data = bridge._parse_json(result.stdout)
        if not isinstance(data, dict):
            return []
        prefixes = data.get("prefixes", [])
        if not isinstance(prefixes, list):
            return []
        return [p for p in prefixes if isinstance(p, str)]
    except Exception as e:
        logger.error(f"❌ 取得片商前綴失敗: {e}")
        return []
