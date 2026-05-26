"""
測試番號提取器模組
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from src.models.extractor import UnifiedCodeExtractor
from src.scrapers.sources.avwiki_scraper import AVWikiScraper


class TestUnifiedCodeExtractor:
    """測試統一番號提取器"""

    @pytest.fixture
    def extractor(self):
        return UnifiedCodeExtractor()

    def test_extract_standard_format(self, extractor):
        """測試標準格式 XXX-123"""
        assert extractor.extract_code("STARS-707.mp4") == "STARS-707"
        assert extractor.extract_code("SSIS-123.mkv") == "SSIS-123"
        assert extractor.extract_code("IPX-999.avi") == "IPX-999"

    def test_extract_no_dash_format(self, extractor):
        """測試無橫槓格式（會自動轉換為標準格式）"""
        assert extractor.extract_code("STARS707.mp4") == "STARS-707"
        assert extractor.extract_code("SSIS123.mkv") == "SSIS-123"

    def test_extract_with_special_chars(self, extractor):
        """測試特殊字元分隔（會標準化為橫槓）"""
        assert extractor.extract_code("STARS_707.mp4") == "STARS-707"
        assert extractor.extract_code("STARS.707.mp4") == "STARS-707"

    def test_extract_with_suffix(self, extractor):
        """測試帶後綴的番號"""
        assert extractor.extract_code("STARS-707CH.mp4") == "STARS-707"
        assert extractor.extract_code("SSIS-123C.mkv") == "SSIS-123"

    def test_extract_with_quality_tags(self, extractor):
        """測試帶品質標記的檔名"""
        assert extractor.extract_code("STARS-707-1080p.mp4") == "STARS-707"
        assert extractor.extract_code("SSIS-123[720p].mkv") == "SSIS-123"
        assert extractor.extract_code("IPX-999.H265.mp4") == "IPX-999"

    def test_extract_with_special_tech_suffixes(self, extractor):
        """測試尾端完整技術標籤不應併入番號"""
        assert extractor.extract_code("SONE-240-60FPS.mp4") == "SONE-240"
        assert extractor.extract_code("SONE-24060FPS.mp4") == "SONE-240"
        assert extractor.extract_code("SONE-240-2160P.mp4") == "SONE-240"
        assert extractor.extract_code("MIFD-0702160p.mp4") == "MIFD-070"
        assert extractor.extract_code("FWAY-03160FPS.mp4") == "FWAY-031"
        assert extractor.extract_code("SIRO-1234.mp4") == "SIRO-1234"

    def test_extract_with_brackets(self, extractor):
        """測試帶括號的檔名"""
        assert extractor.extract_code("[字幕組]STARS-707.mp4") == "STARS-707"
        assert extractor.extract_code("SSIS-123(1080p).mkv") == "SSIS-123"
        assert extractor.extract_code("{Uncensored}IPX-999.mp4") == "IPX-999"

    def test_extract_with_website_prefix(self, extractor):
        """測試帶網站前綴的檔名（通用 *.com[@-] 模式）"""
        assert extractor.extract_code("hhd800.com@STARS-707.mp4") == "STARS-707"
        assert extractor.extract_code("xxx.com-SSIS-123.mkv") == "SSIS-123"
        assert extractor.extract_code("489155.com@MIMK-273.mp4") == "MIMK-273"
        assert extractor.extract_code("123abc.com@IPX-999.mp4") == "IPX-999"

    def test_extract_site_prefix_489155_delegated(self, extractor):
        """489155.com@ 前綴通用化：Python 層應委派並正確回傳番號（mock Go CLI，commit da535ca）"""
        from unittest.mock import patch

        with patch.object(extractor, "_extract_code_via_go", return_value="MIMK-273") as mock_go:
            result = extractor.extract_code("489155.com@MIMK-273.mp4")

        mock_go.assert_called_once_with("489155.com@MIMK-273.mp4")
        assert result == "MIMK-273"

    def test_skip_fc2_files(self, extractor):
        """測試跳過 FC2 檔案"""
        assert extractor.extract_code("FC2-PPV-1234567.mp4") is None
        assert extractor.extract_code("FC2PPV-1234567.mp4") is None
        assert extractor.extract_code("FC2_PPV_1234567.mp4") is None

    def test_skip_ppv_files(self, extractor):
        """測試跳過 PPV 檔案"""
        assert extractor.extract_code("PPV-1234567.mp4") is None
        assert extractor.extract_code("PPV_1234567.mp4") is None

    def test_extract_various_prefixes(self, extractor):
        """測試各種片商前綴"""
        assert extractor.extract_code("MIDV-123.mp4") == "MIDV-123"
        assert extractor.extract_code("FSDSS-456.mp4") == "FSDSS-456"
        assert extractor.extract_code("CAWD-789.mp4") == "CAWD-789"
        assert extractor.extract_code("IPZZ-100.mp4") == "IPZZ-100"

    def test_extract_long_prefix(self, extractor):
        """測試長前綴"""
        assert extractor.extract_code("ABCDEF-123.mp4") == "ABCDEF-123"

    def test_extract_short_prefix(self, extractor):
        """測試短前綴"""
        assert extractor.extract_code("AB-123.mp4") == "AB-123"

    def test_extract_case_insensitive(self, extractor):
        """測試大小寫不敏感"""
        assert extractor.extract_code("stars-707.mp4") == "STARS-707"
        assert extractor.extract_code("SsIs-123.mp4") == "SSIS-123"

    def test_extract_with_multiple_hyphens(self, extractor):
        """測試多個連字符"""
        result = extractor.extract_code("STARS--707.mp4")
        assert result is not None

    def test_extract_complex_filename(self, extractor):
        """測試複雜檔名"""
        filename = "hhd800.com@[字幕組]STARS-707-C-1080p-HEVC-X265.mp4"
        assert extractor.extract_code(filename) == "STARS-707"

    def test_extract_no_code(self, extractor):
        """測試無法提取番號"""
        assert extractor.extract_code("random_video.mp4") is None
        assert extractor.extract_code("just_text.mp4") is None

    def test_extract_from_path(self, extractor):
        """測試從完整路徑提取"""
        path = "/path/to/video/STARS-707.mp4"
        assert extractor.extract_code(path) == "STARS-707"


class TestAVWikiScraperCompatibility:
    """測試 AV-WIKI scraper 命名相容層"""

    def test_search_batch_concurrent_delegates_to_batch_search_concurrent(self):
        """測試舊名稱會委派到新主名稱"""
        expected = {
            "STARS-707": {
                "video_code": "STARS-707",
                "actresses": ["範例女優"],
            }
        }
        async def run_test() -> tuple[AVWikiScraper, dict[str, dict[str, list[str] | str]]]:
            scraper = AVWikiScraper()
            scraper.batch_search_concurrent = AsyncMock(return_value=expected)
            result = await scraper.search_batch_concurrent(
                ["STARS-707"],
                max_concurrent=7,
                progress_callback=None,
            )
            return scraper, result

        scraper, result = asyncio.run(run_test())

        scraper.batch_search_concurrent.assert_awaited_once_with(
            ["STARS-707"],
            max_concurrent=7,
            progress_callback=None,
        )
        assert result == expected
