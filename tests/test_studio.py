"""
測試片商識別器模組
"""

import tempfile
from pathlib import Path

import pytest

from src.models.studio import StudioIdentifier


class TestStudioIdentifier:
    """測試片商識別器"""

    @pytest.fixture
    def temp_studios_file(self):
        """建立臨時片商規則檔案"""
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".json"
        ) as f:
            f.write(
                """{
                "S1": ["SSIS", "SSNI", "SONE", "STARS"],
                "MOODYZ": ["MIRD", "MIDD", "MIDV", "MIDE"],
                "PREMIUM": ["IPX", "IPZ", "IPZZ"],
                "FALENO": ["FSDSS", "FSDSS2"],
                "KAWAII": ["CAWD", "KAWD"]
            }"""
            )
            temp_path = f.name

        yield temp_path
        Path(temp_path).unlink()

    @pytest.fixture
    def identifier(self, temp_studios_file):
        return StudioIdentifier(rules_file=temp_studios_file)

    def test_identify_s1_studio(self, identifier):
        """測試識別 S1 片商"""
        assert identifier.identify_studio("SSIS-123") == "S1"
        assert identifier.identify_studio("SSNI-456") == "S1"
        assert identifier.identify_studio("SONE-789") == "S1"
        assert identifier.identify_studio("STARS-707") == "S1"

    def test_identify_moodyz_studio(self, identifier):
        """測試識別 MOODYZ 片商"""
        assert identifier.identify_studio("MIDV-123") == "MOODYZ"
        assert identifier.identify_studio("MIDE-456") == "MOODYZ"
        assert identifier.identify_studio("MIRD-789") == "MOODYZ"

    def test_identify_premium_studio(self, identifier):
        """測試識別 PREMIUM 片商"""
        assert identifier.identify_studio("IPX-123") == "PREMIUM"
        assert identifier.identify_studio("IPZZ-456") == "PREMIUM"
        assert identifier.identify_studio("IPZ-789") == "PREMIUM"

    def test_identify_faleno_studio(self, identifier):
        """測試識別 FALENO 片商"""
        assert identifier.identify_studio("FSDSS-123") == "FALENO"

    def test_identify_kawaii_studio(self, identifier):
        """測試識別 KAWAII 片商"""
        assert identifier.identify_studio("CAWD-123") == "KAWAII"
        assert identifier.identify_studio("KAWD-456") == "KAWAII"

    def test_identify_unknown_studio(self, identifier):
        """測試未知片商"""
        assert identifier.identify_studio("UNKNOWN-123") == "UNKNOWN"
        assert identifier.identify_studio("XYZ-999") == "UNKNOWN"

    def test_identify_empty_code(self, identifier):
        """測試空番號"""
        assert identifier.identify_studio("") == "UNKNOWN"
        assert identifier.identify_studio("   ") == "UNKNOWN"

    def test_identify_case_insensitive(self, identifier):
        """測試大小寫不敏感"""
        assert identifier.identify_studio("ssis-123") == "S1"
        assert identifier.identify_studio("SSIS-123") == "S1"
        assert identifier.identify_studio("SsIs-123") == "S1"

    def test_normalize_studio_name_with_alias(self, identifier):
        """測試片商名稱標準化（別名）"""
        assert identifier.normalize_studio_name("MOODYZ DIVA") == "MOODYZ"
        assert identifier.normalize_studio_name("MOODYZ diva") == "MOODYZ"
        assert identifier.normalize_studio_name("S1 NO.1 STYLE") == "S1"
        assert identifier.normalize_studio_name("Premium") == "PREMIUM"

    def test_normalize_studio_name_japanese(self, identifier):
        """測試日文片商名稱標準化"""
        assert identifier.normalize_studio_name("エスワン") == "S1"
        assert identifier.normalize_studio_name("ファレノ") == "FALENO"
        assert identifier.normalize_studio_name("ムーディーズ") == "MOODYZ"
        assert identifier.normalize_studio_name("アタッカーズ") == "ATTACKERS"
        assert identifier.normalize_studio_name("マドンナ") == "MADONNA"
        assert identifier.normalize_studio_name("プレステージ") == "PRESTIGE"

    def test_normalize_studio_name_with_code(self, identifier):
        """測試使用番號推斷片商"""
        assert identifier.normalize_studio_name("Unknown Studio", "SSIS-123") == "S1"
        assert (
            identifier.normalize_studio_name("Wrong Name", "MIDV-456") == "MOODYZ"
        )

    def test_normalize_studio_name_code_only(self, identifier):
        """測試只有番號代碼的情況"""
        assert identifier.normalize_studio_name("SSIS") == "S1"
        assert identifier.normalize_studio_name("MIDV") == "MOODYZ"

    def test_normalize_studio_name_empty(self, identifier):
        """測試空片商名稱"""
        assert identifier.normalize_studio_name("") == "UNKNOWN"
        assert identifier.normalize_studio_name("   ") == "UNKNOWN"

    def test_normalize_studio_name_whitespace(self, identifier):
        """測試去除前後空白"""
        assert identifier.normalize_studio_name("  S1  ") == "S1"
        assert identifier.normalize_studio_name("\tMOODYZ\n") == "MOODYZ"

    def test_normalize_studio_name_keep_original(self, identifier):
        """測試保持原名（非別名）"""
        assert identifier.normalize_studio_name("CustomStudio") == "CustomStudio"

    def test_studio_patterns(self, identifier):
        """測試片商模式"""
        assert "S1" in identifier.studio_patterns
        assert "MOODYZ" in identifier.studio_patterns
        assert "PREMIUM" in identifier.studio_patterns
        assert "FALENO" in identifier.studio_patterns
        assert "KAWAII" in identifier.studio_patterns

    def test_studio_prefixes(self, identifier):
        """測試片商前綴對映"""
        assert "SSIS" in identifier.studio_patterns["S1"]
        assert "SSNI" in identifier.studio_patterns["S1"]
        assert "MIDV" in identifier.studio_patterns["MOODYZ"]
        assert "IPX" in identifier.studio_patterns["PREMIUM"]

    def test_load_rules_missing_file(self):
        """測試載入不存在的規則檔案"""
        with tempfile.TemporaryDirectory() as tmpdir:
            non_existent = Path(tmpdir) / "non_existent.json"
            identifier = StudioIdentifier(rules_file=str(non_existent))
            # 應該建立預設檔案
            assert non_existent.exists()

    def test_code_to_studio_map(self, identifier):
        """測試番號代碼到片商的對映"""
        assert identifier.code_to_studio.get("SSIS") == "S1"
        assert identifier.code_to_studio.get("MIDV") == "MOODYZ"
        assert identifier.code_to_studio.get("IPX") == "PREMIUM"
