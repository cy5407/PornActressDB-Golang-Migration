"""
番號提取器模組
"""

import logging

logger = logging.getLogger(__name__)


class UnifiedCodeExtractor:
    """統一程式碼提取器"""

    def extract_code(self, filename: str) -> str | None:
        """從檔案名稱提取番號（委託 Go CLI）。找不到番號回傳 None；Go 不可用時明確拋錯。"""
        return self._extract_code_via_go(filename)

    def _extract_code_via_go(self, filename: str) -> str | None:
        """透過 Go CLI 提取番號；找不到番號回傳 None，Go 不可用時拋出 RuntimeError。"""
        errors: list[str] = []

        try:
            from services.go_cli import extract_code as go_extract_code
            return go_extract_code(filename)
        except Exception as exc:
            errors.append(str(exc))

        try:
            from src.services.go_cli import extract_code as go_extract_code
            return go_extract_code(filename)
        except Exception as exc:
            errors.append(str(exc))
            detail = "; ".join(error for error in errors if error)
            logger.debug(f"Go 番號提取不可用: {detail}")
            raise RuntimeError(
                f"Go 番號提取不可用: {detail}" if detail else "Go 番號提取不可用"
            ) from exc

