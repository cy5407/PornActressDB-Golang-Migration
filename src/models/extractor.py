"""
番號提取器模組
"""

import logging

logger = logging.getLogger(__name__)


class UnifiedCodeExtractor:
    """統一程式碼提取器"""

    def extract_code(self, filename: str) -> str | None:
        """從檔案名稱提取番號（委託 Go CLI）。若 Go 不可用則回傳 None。"""
        return self._extract_code_via_go(filename)

    def _extract_code_via_go(self, filename: str) -> str | None:
        """嘗試透過 Go CLI 提取番號；若 Go 不可用則回傳 None。"""
        try:
            from services.go_cli import extract_code as go_extract_code
            return go_extract_code(filename)
        except Exception:
            pass

        try:
            from src.services.go_cli import extract_code as go_extract_code
            return go_extract_code(filename)
        except Exception as e:
            logger.debug(f"Go 番號提取失敗: {e}")
            return None

