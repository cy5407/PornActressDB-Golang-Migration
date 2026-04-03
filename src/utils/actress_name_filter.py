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
    def is_valid_actress_name(
        name: str, allow_single_latin_name: bool = False
    ) -> bool:
        """
        判斷是否為有效的女優名字
        
        Args:
            name: 待檢查的名字
            
        Returns:
            bool: True 表示可能是女優名字，False 表示明顯不是
        """
        if not name or not isinstance(name, str):
            return False
            
        name = name.strip()
        
        # 長度檢查：女優名字通常是 2-15 個字元
        if len(name) < 2 or len(name) > 15:
            logger.debug(f"❌ 長度不符: '{name}' (長度: {len(name)})")
            return False
        
        # 檢查是否包含標題關鍵字（日文）
        for keyword in ActressNameFilter.TITLE_KEYWORDS:
            if keyword in name:
                logger.debug(f"❌ 包含標題關鍵字: '{name}' (關鍵字: {keyword})")
                return False
        
        # 檢查是否包含標題關鍵字（中文）
        for keyword in ActressNameFilter.TITLE_KEYWORDS_ZH:
            if keyword in name:
                logger.debug(f"❌ 包含中文標題關鍵字: '{name}' (關鍵字: {keyword})")
                return False
        
        # 檢查是否包含動詞/形容詞片段（使用正則表達式）
        for pattern in ActressNameFilter.VERB_PATTERNS:
            if re.search(pattern, name):
                logger.debug(f"❌ 包含動詞片段: '{name}' (模式: {pattern})")
                return False
        
        # 檢查是否包含截斷的標題（以特殊字元結尾）
        if name.endswith(("ガ", "オ", "自", "香", "期")):
            # 這些字元常出現在被截斷的標題結尾
            # 但也可能是真實名字的一部分，所以要額外檢查
            if len(name) > 10:
                logger.debug(f"❌ 疑似被截斷的標題: '{name}'")
                return False
        
        # 檢查是否為純數字或符號
        if re.match(r'^[\d\W]+$', name):
            logger.debug(f"❌ 純數字或符號: '{name}'")
            return False
        
        # 檢查是否包含過多的非漢字日文（可能是標題片段）
        hiragana_count = len(re.findall(r'[\u3040-\u309F]', name))
        katakana_count = len(re.findall(r'[\u30A0-\u30FF]', name))
        total_kana = hiragana_count + katakana_count
        
        # 女優名字通常以漢字或片假名為主，平假名不會太多
        # 但短名字（≤5字元）例外，因為很多女優名字就是短的
        if len(name) > 5 and hiragana_count > len(name) * 0.6:
            logger.debug(f"❌ 平假名比例過高: '{name}' (平假名: {hiragana_count}/{len(name)})")
            return False
        
        # 檢查是否包含日文或中文字元
        if not re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', name):
            if allow_single_latin_name and re.fullmatch(r"[A-Za-z]{2,12}", name):
                logger.debug(f"✅ 允許單一英文藝名: '{name}'")
                return True
            # 如果沒有日文/中文，檢查是否為西方名字格式
            if not re.match(r'^[A-Za-z\s]+$', name) or ' ' not in name:
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
        sorted_names = sorted(valid_names, key=score_name, reverse=True)
        best_name = sorted_names[0]
        
        logger.info(f"🎯 從 {len(actresses)} 個候選中選出最佳: '{best_name}'")
        return best_name
