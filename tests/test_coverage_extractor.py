"""
補充 extractor.py 覆蓋率：測試 _extract_code_via_go fallback 路徑
"""
import sys
from unittest.mock import patch

import pytest

from src.models.extractor import UnifiedCodeExtractor


@pytest.fixture
def extractor():
    return UnifiedCodeExtractor()


class TestExtractorFallbackPaths:
    """確保 _extract_code_via_go 的備用匯入路徑被覆蓋"""

    def test_fallback_both_imports_fail_raises_runtime_error(self, extractor):
        """當兩個匯入路徑都失敗時，應明確拋錯而非靜默回傳 None。"""
        # 將兩個模組路徑都設為 None，使 import 引發 ImportError
        with patch.dict(
            sys.modules,
            {"services": None, "services.go_cli": None, "src.services.go_cli": None},
        ):
            with pytest.raises(RuntimeError, match="Go 番號提取不可用"):
                extractor._extract_code_via_go("STARS-707.mp4")

    def test_fallback_first_import_fails_second_succeeds(self, extractor):
        """當第一個匯入失敗、第二個成功時，應透過 src 路徑回傳結果（覆蓋 lines 22-27）"""
        # 移除 services.go_cli（保留 src.services.go_cli），並 mock extract_code
        with patch.dict(sys.modules, {"services": None, "services.go_cli": None}):
            # src.services.go_cli 已存在，無需特別 mock — 直接呼叫即可
            # 但為了不實際執行 Go CLI，以 mock 取代 extract_code
            import src.services.go_cli as real_go_cli

            original_extract = getattr(real_go_cli, "extract_code", None)
            try:
                real_go_cli.extract_code = lambda filename: "STARS-707"
                result = extractor._extract_code_via_go("STARS-707.mp4")
            finally:
                if original_extract is not None:
                    real_go_cli.extract_code = original_extract

        assert result == "STARS-707"
