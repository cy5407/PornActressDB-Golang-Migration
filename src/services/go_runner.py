"""Go CLI 執行與 JSON 解析共用 helper。"""

import json
import logging
import os
import subprocess  # nosec B404

logger = logging.getLogger(__name__)


def _cleanup_temp_file(path: str | None, context: str) -> None:
    """清理暫存檔，避免清理失敗覆蓋主流程結果。"""
    if not path:
        return
    try:
        os.unlink(path)
    except FileNotFoundError:
        return
    except Exception as e:
        logger.warning(f"⚠️ 無法清理 {context} 暫存檔 {path}: {e}")


class GoBridgeError(Exception):
    """Go 橋接層錯誤。"""


class GoBridgeExecError(GoBridgeError):
    """Go CLI 執行失敗（returncode != 0）。"""

    def __init__(self, message: str, returncode: int = -1):
        super().__init__(message)
        self.returncode = returncode


class GoBridgeNotFoundError(GoBridgeError):
    """資料不存在（Go CLI 正常執行但回傳 not found）。"""


class GoBridgeJSONError(GoBridgeError):
    """Go CLI stdout 不是合法 JSON。"""


def run_subprocess(cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
    """以受控參數列表執行本機 CLI，不經 shell。"""
    return subprocess.run(  # nosec B603
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )


class GoCommandRunner:
    """封裝 Go CLI 的 subprocess 執行與 JSON 解析。"""

    def __init__(self, exe_path: str):
        self.exe_path = exe_path

    def run(
        self,
        args: list[str],
        timeout: int = 60,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        """執行 Go CLI 命令。"""
        cmd = [self.exe_path] + args
        logger.debug(f"執行命令: {' '.join(cmd)}")

        try:
            result = run_subprocess(cmd, timeout=timeout)

            if check and result.returncode != 0:
                error_msg = result.stderr.strip() or f"命令失敗，返回碼: {result.returncode}"
                not_found_keywords = ("not found", "no such", "does not exist", "找不到")
                if any(kw in error_msg.lower() for kw in not_found_keywords):
                    raise GoBridgeNotFoundError(error_msg)
                raise GoBridgeExecError(error_msg, returncode=result.returncode)

            return result

        except subprocess.TimeoutExpired:
            raise GoBridgeError(f"命令執行超時 ({timeout}s)")
        except FileNotFoundError:
            raise GoBridgeError(f"找不到執行檔: {self.exe_path}")

    def parse_json(self, output: str) -> dict | list:
        """解析 JSON 輸出。"""
        try:
            return json.loads(output)
        except json.JSONDecodeError as e:
            raise GoBridgeJSONError(f"JSON 解析失敗: {e}\n輸出: {output[:200]}")

    def run_json(
        self,
        args: list[str],
        timeout: int = 60,
        check: bool = True,
    ) -> dict | list:
        """執行命令並直接回傳解析後的 JSON。"""
        result = self.run(args, timeout=timeout, check=check)
        return self.parse_json(result.stdout)
