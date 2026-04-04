"""
Go 加速片商識別器 (GoAcceleratedStudioIdentifier)

此模組提供 Go CLI 加速的片商識別功能，在 Go 不可用時自動 fallback 到 Python 實作。

設計理念：
- 優先使用 Go CLI 進行片商識別（效能提升 10x）
- 當 Go CLI 不可用時自動切換到 Python StudioIdentifier
- 保持與 StudioIdentifier 完全相同的 API
- 透明的 fallback 機制，調用者無需感知

效能差異：
- Go 識別: ~0.1ms/次
- Python 識別: ~1ms/次
- 批次識別效能差距更大（Go 支援並發）

使用範例：
    from src.models.go_accelerated_studio import GoAcceleratedStudioIdentifier

    # 優先使用 Go，不可用時 fallback 到 Python
    identifier = GoAcceleratedStudioIdentifier()

    # 與 StudioIdentifier 完全相同的 API
    studio = identifier.identify_studio('SONE-001')
    normalized = identifier.normalize_studio_name('S1 NO.1 STYLE', 'SSIS-123')
"""

import logging
from typing import Optional

from src.models.studio import StudioIdentifier

logger = logging.getLogger(__name__)


class GoAcceleratedStudioIdentifier:
    """
    Go 加速片商識別器

    提供與 StudioIdentifier 相同的介面，但優先使用 Go CLI 加速。
    當 Go CLI 不可用時自動 fallback 到 Python 實作。

    屬性：
        use_go (bool): 是否使用 Go 加速
        fallback_count (int): fallback 到 Python 的次數
    """

    def __init__(self, rules_file: str = "studios.json", use_go: bool = True):
        """
        初始化 Go 加速片商識別器

        Args:
            rules_file: 片商規則檔案路徑
            use_go: 是否嘗試使用 Go 加速（預設 True）
        """
        self.rules_file = rules_file
        self._use_go = use_go
        self._go_bridge = None
        self._go_available = None
        self.fallback_count = 0

        # 始終初始化 Python 實作作為 fallback
        self._python_identifier = StudioIdentifier(rules_file)

        # 延遲檢查 Go 可用性
        if use_go:
            self._check_go_availability()

        mode = "Go 加速" if self.use_go else "Python"
        logger.info(f"✅ GoAcceleratedStudioIdentifier 初始化完成 (模式: {mode})")

    def _check_go_availability(self):
        """檢查 Go CLI 是否可用"""
        if self._go_available is not None:
            return self._go_available

        try:
            from src.services.go_bridge import GoBridge

            self._go_bridge = GoBridge()
            self._go_available = self._go_bridge.is_available

            if self._go_available:
                logger.info("🚀 Go CLI 可用，啟用片商識別加速模式")
            else:
                logger.warning("⚠️ Go CLI 不可用，使用 Python fallback")
        except ImportError as e:
            logger.warning(f"⚠️ 無法載入 Go 橋接層: {e}")
            self._go_available = False

        return self._go_available

    @property
    def use_go(self) -> bool:
        """是否正在使用 Go 加速"""
        return self._use_go and (self._go_available or False)

    # ========================================================================
    # 核心識別功能（Go 加速 + Python fallback）
    # ========================================================================

    def identify_studio(self, code: str) -> str:
        """
        識別番號所屬片商

        優先使用 Go CLI，失敗時 fallback 到 Python。

        Args:
            code: 番號

        Returns:
            片商名稱，識別失敗返回 "UNKNOWN"
        """
        if not code:
            return "UNKNOWN"

        if self.use_go:
            try:
                from src.services.go_api.identify import identify_studio as go_identify

                result = go_identify(code, check_major=False)
                if result and "studio" in result:
                    studio = result["studio"]
                    if studio and studio != "":
                        return studio
                # Go 返回空結果，fallback 到 Python
            except Exception as e:
                logger.debug(f"Go 片商識別失敗，fallback 到 Python: {e}")
                self.fallback_count += 1

        return self._python_identifier.identify_studio(code)

    def identify_studios_batch(self, codes: list[str]) -> dict[str, str]:
        """
        批次識別番號所屬片商

        優先使用 Go CLI 批次處理，失敗時 fallback 到 Python。

        Args:
            codes: 番號列表

        Returns:
            {code: studio} 字典
        """
        if not codes:
            return {}

        if self.use_go:
            try:
                from src.services.go_api.identify import identify_studios_batch as go_batch

                results = go_batch(codes, check_major=False)
                if results:
                    return {
                        r["code"]: r["studio"]
                        for r in results
                        if r.get("studio")
                    }
            except Exception as e:
                logger.debug(f"Go 批次識別失敗，fallback 到 Python: {e}")
                self.fallback_count += 1

        # Python fallback - 逐一識別
        return {code: self._python_identifier.identify_studio(code) for code in codes}

    def normalize_studio_name(
        self, studio_name: str, video_code: Optional[str] = None
    ) -> str:
        """
        標準化片商名稱

        優先使用 Go CLI 進行番號判斷，失敗時 fallback 到 Python。

        Args:
            studio_name: 原始片商名稱
            video_code: 番號（可用來推斷片商）

        Returns:
            標準化後的片商名稱
        """
        # 優先使用番號判斷
        if video_code and self.use_go:
            try:
                from src.services.go_api.identify import identify_studio as go_identify

                result = go_identify(video_code, check_major=False)
                if result and result.get("studio") and result["studio"] != "UNKNOWN":
                    return result["studio"]
            except Exception as e:
                logger.debug(f"Go 番號識別失敗: {e}")
                self.fallback_count += 1

        # 使用 Python 處理（包含別名解析）
        return self._python_identifier.normalize_studio_name(studio_name, video_code)

    def is_major_studio(self, code: str) -> bool:
        """
        判斷是否為大片商

        Args:
            code: 番號

        Returns:
            是否為大片商
        """
        if self.use_go:
            try:
                from src.services.go_api.identify import identify_studio as go_identify

                result = go_identify(code, check_major=True)
                if result and "is_major" in result:
                    return result["is_major"]
            except Exception as e:
                logger.debug(f"Go 大片商判斷失敗，fallback 到 Python: {e}")
                self.fallback_count += 1

        # Python fallback - 使用規則判斷
        studio = self._python_identifier.identify_studio(code)
        # 定義大片商列表
        major_studios = {"S1", "MOODYZ", "PREMIUM", "FALENO", "KAWAII"}
        return studio in major_studios

    # ========================================================================
    # 委派屬性和方法（直接使用 Python 實作）
    # ========================================================================

    @property
    def studio_patterns(self) -> dict:
        """取得片商模式字典"""
        return self._python_identifier.studio_patterns

    @property
    def code_to_studio(self) -> dict:
        """取得番號前綴到片商的映射"""
        return self._python_identifier.code_to_studio

    @property
    def studio_aliases(self) -> dict:
        """取得片商別名對照表"""
        return self._python_identifier.studio_aliases

    def get_stats(self) -> dict:
        """
        取得統計資訊

        Returns:
            統計資訊字典
        """
        return {
            "use_go": self.use_go,
            "fallback_count": self.fallback_count,
            "studio_count": len(self._python_identifier.studio_patterns),
            "prefix_count": len(self._python_identifier.code_to_studio),
            "alias_count": len(self._python_identifier.studio_aliases),
        }


def get_studio_identifier(
    rules_file: str = "studios.json", use_go: bool = True
) -> GoAcceleratedStudioIdentifier:
    """
    工廠函式：取得片商識別器實例

    Args:
        rules_file: 片商規則檔案路徑
        use_go: 是否使用 Go 加速

    Returns:
        GoAcceleratedStudioIdentifier 實例
    """
    return GoAcceleratedStudioIdentifier(rules_file, use_go)
