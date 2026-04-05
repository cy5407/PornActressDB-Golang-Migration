"""Go CLI 快取 API。"""

import base64
import logging
from typing import Optional

try:
    from ..go_runner import GoBridgeError, GoCommandRunner
except ImportError:
    from services.go_runner import GoBridgeError, GoCommandRunner

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


def cache_get(
    key: str,
    cache_dir: str = "cache",
    *,
    runner: GoCommandRunner | None = None,
) -> Optional[bytes]:
    """從 Go 快取讀取值，找不到或失敗時回傳 None。"""
    r = _get_runner(runner)
    cmd = ["cache", "get", "-cache-dir", cache_dir, key]

    try:
        result = r.run(cmd)
    except GoBridgeError as e:
        logger.error(f"❌ Go CLI 執行失敗 (cache get {key}): {e}")
        return None

    output = result.stdout.strip()
    if not output:
        return None

    try:
        data = r.parse_json(output)
    except GoBridgeError as e:
        logger.warning(f"⚠️ JSON 解析失敗 (cache get {key}): {e}")
        return None

    if not isinstance(data, dict) or not data.get("success"):
        return None

    encoded = data.get("value")
    if encoded is None:
        return None

    try:
        return base64.b64decode(encoded)
    except Exception as e:
        logger.warning(f"⚠️ base64 解碼失敗 (cache get {key}): {e}")
        return None


def cache_set(
    key: str,
    value: bytes,
    ttl_hours: int = 24,
    cache_dir: str = "cache",
    *,
    runner: GoCommandRunner | None = None,
) -> bool:
    """將值寫入 Go 快取，成功回傳 True，失敗回傳 False。"""
    r = _get_runner(runner)
    encoded = base64.b64encode(value).decode("ascii")
    cmd = [
        "cache", "set",
        "-cache-dir", cache_dir,
        "-ttl-hours", str(ttl_hours),
        key,
        encoded,
    ]

    try:
        result = r.run(cmd)
    except GoBridgeError as e:
        logger.error(f"❌ Go CLI 執行失敗 (cache set {key}): {e}")
        return False

    output = result.stdout.strip()
    if not output:
        return False

    try:
        data = r.parse_json(output)
    except GoBridgeError as e:
        logger.warning(f"⚠️ JSON 解析失敗 (cache set {key}): {e}")
        return False

    return isinstance(data, dict) and bool(data.get("success"))


def cache_delete(
    key: str,
    cache_dir: str = "cache",
    *,
    runner: GoCommandRunner | None = None,
) -> bool:
    """從 Go 快取刪除條目，成功回傳 True，失敗回傳 False。"""
    r = _get_runner(runner)
    cmd = ["cache", "delete", "-cache-dir", cache_dir, key]

    try:
        result = r.run(cmd)
    except GoBridgeError as e:
        logger.error(f"❌ Go CLI 執行失敗 (cache delete {key}): {e}")
        return False

    output = result.stdout.strip()
    if not output:
        return False

    try:
        data = r.parse_json(output)
    except GoBridgeError as e:
        logger.warning(f"⚠️ JSON 解析失敗 (cache delete {key}): {e}")
        return False

    return isinstance(data, dict) and bool(data.get("success"))
