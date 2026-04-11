"""
女優名字過濾工具模組
用於過濾從網站擷取的標籤，避免將影片標題片段誤認為女優名字
"""

import re
import logging

logger = logging.getLogger(__name__)


class ActressNameFilter:
    """女優名字過濾器 - 移除明顯不是女優名字的內容"""

    # 常見的影片標題關鍵字（日文）
    TITLE_KEYWORDS = [
        # 首次/初次相關
        "初めて",
        "初体験",
        "デビュー",
        "新人",
        
        # 性愛相關
        "中出し",
        "解禁",
        "痴女",
        "痴漢",
        "輪姦",
        "調教",
        "陵辱",
        "凌辱",
        "犯され",
        "犯す",
        "侵され",
        "姦",
        
        # 身體部位
        "おっぱい",
        "巨乳",
        "美乳",
        "爆乳",
        "美脚",
        "美尻",
        "美少女",
        
        # 場景/情境
        "学園",
        "学校",
        "スポーツ",
        "ビーチ",
        "温泉",
        "寝取",
        "不倫",
        "近親",
        "姪っ子",
        "義母",
        "義父",
        "義姉",
        "義妹",
        "兄嫁",
        
        # 動作/狀態
        "勃起",
        "興奮",
        "絶頂",
        "イキ",
        "逝き",
        "喘ぎ",
        "乱れ",
        
        # 衣著相關
        "水着",
        "制服",
        "コスプレ",
        "下着",
        "裸",
        "全裸",
        "半裸",
        
        # 其他常見詞
        "エレガンス",
        "エロ",
        "共演",
        "出演者",
        "演員",
        "女優",
        "続編",
        "完全版",
        "総集編",
        
        # 藥物/媚藥相關
        "媚薬",
        "キメセク",
        "洗脳",
        
        # 類型相關
        "ドキュメント",
        "企画",
        "ガチ",
        
        # 情節相關
        "帰省",
        "成長期",
        "田舎",
        "中年",
        "オジ",
        "おじさん",
    ]
    
    # 中文標題關鍵字
    TITLE_KEYWORDS_ZH = [
        "中出",
        "解禁",
        "初體驗",
        "新人",
        "巨乳",
        "美乳",
        "美腿",
        "學園",
        "學校",
        "溫泉",
        "制服",
        "泳裝",
        "共演",
    ]
    
    # 動詞/形容詞片段（通常不會出現在名字中）
    # 注意：這些應該作為獨立詞或特定位置出現，不是簡單包含
    VERB_PATTERNS = [
        r"^て$",  # 單獨的 "て"
        r"^つい",  # 以 "つい" 開頭（不小心）
        r"られ",  # 被動形
        r"させ",  # 使役形
        r"ちゃ",  # 口語縮約
        r"しちゃ",  # 做了（口語）
        r"^した",  # 以 "した" 開頭
        r"^する",  # 以 "する" 開頭
        r"され",  # 被
        r"^を",  # 以助詞 "を" 開頭
        r"^が",  # 以助詞 "が" 開頭
        r"で$",  # 以助詞 "で" 結尾
    ]

    @staticmethod
    def _fails_length_check(name: str) -> bool:
        return len(name) < 2 or len(name) > 15

    @staticmethod
    def _contains_any_keyword(name: str, keywords: list[str]) -> str | None:
        for keyword in keywords:
            if keyword in name:
                return keyword
        return None

    @staticmethod
    def _contains_verb_pattern(name: str) -> str | None:
        for pattern in ActressNameFilter.VERB_PATTERNS:
            if re.search(pattern, name):
                return pattern
        return None

    @staticmethod
    def _looks_like_truncated_title(name: str) -> bool:
        return name.endswith(("ガ", "オ", "自", "香", "期")) and len(name) > 10

    @staticmethod
    def _is_numeric_or_symbol_only(name: str) -> bool:
        return bool(re.match(r'^[\d\W]+$', name))

    @staticmethod
    def _fails_hiragana_ratio(name: str) -> bool:
        hiragana_count = len(re.findall(r'[぀-ゟ]', name))
        return len(name) > 5 and hiragana_count > len(name) * 0.6

    @staticmethod
    def _passes_language_shape(name: str, allow_single_latin_name: bool) -> bool:
        if re.search(r'[぀-ゟ゠-ヿ一-龯]', name):
            return True
        if allow_single_latin_name and re.fullmatch(r"[A-Za-z]{2,12}", name):
            logger.debug(f"✅ 允許單一英文藝名: '{name}'")
            return True
        return bool(re.match(r'^[A-Za-z\s]+$', name) and ' ' in name)

    @staticmethod
    def is_valid_actress_name(
        name: str, allow_single_latin_name: bool = False
    ) -> bool:
        if not name or not isinstance(name, str):
            return False
        name = name.strip()
        if ActressNameFilter._fails_length_check(name):
            logger.debug(f"❌ 長度不符: '{name}' (長度: {len(name)})")
            return False
        keyword = ActressNameFilter._contains_any_keyword(name, ActressNameFilter.TITLE_KEYWORDS)
        if keyword:
            logger.debug(f"❌ 包含標題關鍵字: '{name}' (關鍵字: {keyword})")
            return False
        keyword = ActressNameFilter._contains_any_keyword(name, ActressNameFilter.TITLE_KEYWORDS_ZH)
        if keyword:
            logger.debug(f"❌ 包含中文標題關鍵字: '{name}' (關鍵字: {keyword})")
            return False
        pattern = ActressNameFilter._contains_verb_pattern(name)
        if pattern:
            logger.debug(f"❌ 包含動詞片段: '{name}' (模式: {pattern})")
            return False
        if ActressNameFilter._looks_like_truncated_title(name):
            logger.debug(f"❌ 疑似被截斷的標題: '{name}'")
            return False
        if ActressNameFilter._is_numeric_or_symbol_only(name):
            logger.debug(f"❌ 純數字或符號: '{name}'")
            return False
        if ActressNameFilter._fails_hiragana_ratio(name):
            logger.debug(f"❌ 平假名比例過高: '{name}'")
            return False
        if not ActressNameFilter._passes_language_shape(name, allow_single_latin_name):
            logger.debug(f"❌ 不符合名字格式: '{name}'")
            return False
        logger.debug(f"✅ 通過驗證: '{name}'")
        return True

    @staticmethod
    def filter_actress_list(actresses: list[str]) -> list[str]:
        """
        過濾女優名單，移除明顯不是女優名字的項目
        
        Args:
            actresses: 原始女優名單
            
        Returns:
            list[str]: 過濾後的女優名單
        """
        if not actresses:
            return []
        
        filtered = []
        for name in actresses:
            if ActressNameFilter.is_valid_actress_name(name):
                filtered.append(name)
            else:
                logger.info(f"🔍 過濾掉非女優名字: '{name}'")
        
        return filtered

    @staticmethod
    def get_most_likely_actress(actresses: list[str]) -> str | None:
        """
        從候選名單中選出最可能是女優名字的項目
        
        策略：
        1. 最短的名字（通常標題片段較長）
        2. 包含漢字的名字（女優名字通常包含漢字）
        
        Args:
            actresses: 候選名單
            
        Returns:
            str | None: 最可能的女優名字，如果全部無效則返回 None
        """
        if not actresses:
            return None
        
        # 先過濾明顯無效的項目
        valid_names = ActressNameFilter.filter_actress_list(actresses)
        
        if not valid_names:
            return None
        
        if len(valid_names) == 1:
            return valid_names[0]
        
        # 優先選擇包含漢字的較短名字
        def score_name(name: str) -> tuple[int, int]:
            """
            評分函式：返回 (是否包含漢字, 負長度)
            排序時會先選包含漢字的，再選較短的
            """
            has_kanji = 1 if re.search(r'[\u4E00-\u9FAF]', name) else 0
            return (has_kanji, -len(name))
        
        # 排序並返回最佳候選
        sorted_names = sorted(valid_names, key=score_name, reverse=True)  # 依評分排序
        best_name = sorted_names[0]  # 取最高分的名字

        logger.info(f"🎯 從 {len(actresses)} 個候選中選出最佳: '{best_name}'")
        return best_name