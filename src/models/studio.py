"""
片商識別器模組
"""

import logging
import sys
from pathlib import Path

try:
    from utils.json_utils import dump as json_dump
    from utils.json_utils import load as json_load
except ImportError:  # pragma: no cover
    from src.utils.json_utils import dump as json_dump
    from src.utils.json_utils import load as json_load

logger = logging.getLogger(__name__)

_DEFAULT_RULES_FILE = "studios.json"


def _resolve_resource_path(relative_path: str) -> Path:
    """解析資源檔路徑，相容 PyInstaller 打包環境與一般執行環境。"""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / relative_path
    return Path(relative_path)


class StudioIdentifier:
    """片商識別器"""

    def __init__(self, rules_file: str = _DEFAULT_RULES_FILE):
        # 預設規則檔支援 PyInstaller 打包路徑；自訂路徑直接使用
        self.rules_file = (
            _resolve_resource_path(rules_file)
            if rules_file == _DEFAULT_RULES_FILE
            else Path(rules_file)
        )
        self.studio_patterns = self._load_rules()
        self.code_to_studio = self._build_code_to_studio_map()

        # 片商名稱標準化對照表
        self.studio_aliases = {
            "MOODYZ DIVA": "MOODYZ",
            "MOODYZ diva": "MOODYZ",
            "moodyz diva": "MOODYZ",
            "S1 NO.1 STYLE": "S1",
            "エスワン": "S1",  # S1 的日文名稱
            "ムーディーズ": "MOODYZ",
            "アタッカーズ": "ATTACKERS",
            "マドンナ": "MADONNA",
            "プレステージ": "PRESTIGE",
            "アイデアポケット": "IDEA POCKET",
            "アイポケ": "IDEA POCKET",
            "エービーオディー": "E-BODY",
            "イーボディ": "E-BODY",
            "カワイイ": "KAWAII",
            "ワンズファクトリー": "WANZ",
            "エスオーディー": "SOD",
            "ソフト・オン・デマンド": "SOD",
            "SODクリエイト": "SOD",
            "FALENO star": "FALENO",
            "ファレノ": "FALENO",  # FALENO 的日文名稱
            "FALENO TUBE": "FALENO",
            "Premium": "PREMIUM",
        }
        # 建立不區分大小寫的別名索引
        self._alias_lookup = {
            alias.lower(): canonical for alias, canonical in self.studio_aliases.items()
        }

    def normalize_studio_name(self, studio_name: str, video_code: str = None) -> str:
        """標準化片商名稱

        Args:
            studio_name: 原始片商名稱
            video_code: 番號（可用來推斷片商）

        Returns:
            標準化後的片商名稱
        """
        go_result = self._normalize_studio_name_via_go(studio_name, video_code)
        if go_result is not None:
            return go_result

        # 優先使用番號判斷，確保核心大片商優先套用
        if video_code:
            studio_from_code = self.identify_studio(video_code)
            if studio_from_code != "UNKNOWN":
                return studio_from_code

        if not studio_name:
            return "UNKNOWN"

        # 移除前後空白
        studio_name = studio_name.strip()
        if not studio_name:
            return "UNKNOWN"

        # 檢查是否在別名對照表中
        alias_key = studio_name.lower()
        if alias_key in self._alias_lookup:
            normalized = self._alias_lookup[alias_key]
            logger.debug(f"片商名稱標準化: {studio_name} -> {normalized}")
            return normalized

        # 若名稱本身就是片商代碼，嘗試轉換
        studio_upper = studio_name.upper()
        if studio_upper in self.code_to_studio:
            return self.code_to_studio[studio_upper]

        return studio_name

    def _load_rules(self) -> dict:
        if not self.rules_file.exists():
            logger.warning(f"片商規則檔案 {self.rules_file} 不存在，將使用預設規則。")
            default_rules = {
                "S1": ["SSIS", "SSNI", "STARS"],
                "MOODYZ": ["MIRD", "MIDD", "MIDV"],
                "PREMIUM": ["IPX", "IPZ", "IPZZ"],
                "WANZ": ["WANZ"],
                "FALENO": ["FSDSS"],
            }
            # 打包環境下不嘗試寫入（sys._MEIPASS 為唯讀）
            if not hasattr(sys, "_MEIPASS"):
                try:
                    with self.rules_file.open("w", encoding="utf-8") as f:
                        json_dump(default_rules, f, ensure_ascii=False, indent=4)
                except OSError as e:
                    logger.error(f"無法建立預設片商規則檔案: {e}")
            return default_rules
        try:
            with self.rules_file.open("r", encoding="utf-8") as f:
                return json_load(f)
        except (OSError, ValueError) as e:
            logger.error(f"讀取片商規則檔案失敗: {e}, 將使用空規則。")
            return {}

    def _build_code_to_studio_map(self) -> dict[str, str]:
        """建立番號前綴 → 片商名稱的對照表"""
        mapping: dict[str, str] = {}
        for studio, prefixes in self.studio_patterns.items():
            for prefix in prefixes:
                mapping[prefix.upper()] = studio
        return mapping

    def identify_studio(self, code: str) -> str:
        """識別番號所屬片商。

        優先委派給 Go CLI；自訂規則檔（非 studios.json）使用本機前綴對照表；
        Go 不可用且為預設規則檔時回傳 UNKNOWN。
        """
        go_result = self._identify_studio_via_go(code)
        if go_result is not None:
            return go_result
        # 自訂規則檔：Go 不處理，從本機 code_to_studio 查詢前綴
        if code and self.rules_file.name != _DEFAULT_RULES_FILE:
            prefix = code.upper().split('-')[0]
            return self.code_to_studio.get(prefix, "UNKNOWN")
        return "UNKNOWN"

    def _identify_studio_via_go(self, code: str) -> str | None:
        """嘗試透過 Go CLI 識別片商；若 Go 不可用或使用自訂規則檔則回傳 None。"""
        # 若使用自訂規則檔（非預設 studios.json），Go CLI 規則可能不一致，直接用 Python
        if self.rules_file.name != _DEFAULT_RULES_FILE:
            return None

        try:
            try:
                from services.go_cli import identify_studio as go_identify
            except ImportError:
                from src.services.go_cli import identify_studio as go_identify
            return go_identify(code)
        except Exception as e:
            logger.debug(f"Go 片商識別失敗，降級至 Python: {e}")
            return None

    def _normalize_studio_name_via_go(
        self, studio_name: str, video_code: str | None = None
    ) -> str | None:
        """嘗試透過 Go CLI 標準化片商名稱；若 Go 不可用或使用自訂規則檔則回傳 None。"""
        if self.rules_file.name != _DEFAULT_RULES_FILE:
            return None

        try:
            try:
                from services.go_cli import normalize_studio_name as go_normalize
            except ImportError:
                from src.services.go_cli import normalize_studio_name as go_normalize
            return go_normalize(
                studio_name,
                video_code=video_code,
                rules_file=self.rules_file.name,
            )
        except Exception as e:
            logger.debug(f"Go 片商標準化失敗，降級至 Python: {e}")
            return None

