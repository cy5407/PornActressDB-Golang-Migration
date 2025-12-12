"""
片商識別器模組
"""

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


class StudioIdentifier:
    """片商識別器"""

    def __init__(self, rules_file: str = "studios.json"):
        self.rules_file = Path(rules_file)
        self.studio_patterns = self._load_rules()
        self.code_to_studio = self._build_code_to_studio_map()

        # 片商名稱標準化對照表
        self.studio_aliases = {
            "MOODYZ DIVA": "MOODYZ",
            "MOODYZ diva": "MOODYZ",
            "moodyz diva": "MOODYZ",
            "S1 NO.1 STYLE": "S1",
            "エスワン": "S1",  # S1 的日文名稱
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
            logger.warning(f"片商規則檔案 {self.rules_file} 不存在，將建立預設檔案。")
            default_rules = {
                "S1": ["SSIS", "SSNI", "STARS"],
                "MOODYZ": ["MIRD", "MIDD", "MIDV"],
                "PREMIUM": ["IPX", "IPZ", "IPZZ"],
                "WANZ": ["WANZ"],
                "FALENO": ["FSDSS"],
            }
            try:
                with self.rules_file.open("w", encoding="utf-8") as f:
                    json.dump(default_rules, f, ensure_ascii=False, indent=4)
                return default_rules
            except OSError as e:
                logger.error(f"無法建立預設片商規則檔案: {e}")
                return {}
        try:
            with self.rules_file.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"讀取片商規則檔案失敗: {e}, 將使用空規則。")
            return {}

    def identify_studio(self, code: str) -> str:
        if not code:
            return "UNKNOWN"
        prefix_match = re.match(r"([A-Z]+)", code.upper())
        if not prefix_match:
            return "UNKNOWN"
        prefix = prefix_match.group(1)
        return self.code_to_studio.get(prefix, "UNKNOWN")

    def _build_code_to_studio_map(self) -> dict[str, str]:
        mapping = {}
        for studio, prefixes in self.studio_patterns.items():
            for prefix in prefixes:
                mapping[prefix.upper()] = studio
        return mapping
