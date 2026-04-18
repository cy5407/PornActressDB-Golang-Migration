"""
女優名字過濾器測試
"""

import pytest
from src.utils.actress_name_filter import ActressNameFilter


class TestActressNameFilter:
    """測試女優名字過濾器"""

    def test_valid_actress_names(self):
        """測試有效的女優名字"""
        valid_names = [
            "市瀬あいり",
            "清宮仁愛",
            "青葉香奈",
            "宮下玲奈",
            "泉ももか",
            "桜ゆの",
            "神木麗",
        ]
        
        for name in valid_names:
            assert ActressNameFilter.is_valid_actress_name(name), \
                f"應該通過驗證但失敗: {name}"

    def test_invalid_title_fragments(self):
        """測試明顯的標題片段（應該被過濾）"""
        invalid_names = [
            "半裸水着学園",  # 包含 "水着", "学園"
            "初めての中出し解禁",  # 包含 "初めて", "中出し", "解禁"
            "新人",  # 包含 "新人"
            "市瀬あいりエレガンス",  # 包含 "エレガンス"
            "つい勃起しちゃ",  # 包含 "つい", "勃起", "しちゃ"
            "スポーツ学校を中退した青葉香",  # 包含 "スポーツ", "学校"
            "新型媚薬でキメセク洗脳美脚ガ",  # 包含 "媚薬", "キメセク", "洗脳", "美脚"
            "田舎帰省で成長期の姪っ子と自",  # 包含 "帰省", "成長期", "姪っ子"
            "せつスポーツ",  # 包含 "スポーツ"
            "初めての全裸わ",  # 包含 "初めて", "全裸"
        ]
        
        for name in invalid_names:
            assert not ActressNameFilter.is_valid_actress_name(name), \
                f"應該被過濾但通過: {name}"

    def test_edge_cases(self):
        """測試邊界情況"""
        # 過短
        assert not ActressNameFilter.is_valid_actress_name("あ")
        
        # 過長
        assert not ActressNameFilter.is_valid_actress_name("あ" * 20)
        
        # 空字串
        assert not ActressNameFilter.is_valid_actress_name("")
        
        # None
        assert not ActressNameFilter.is_valid_actress_name(None)
        
        # 純數字
        assert not ActressNameFilter.is_valid_actress_name("12345")

    def test_filter_actress_list(self):
        """測試過濾女優名單"""
        mixed_list = [
            "市瀬あいり",  # 有效
            "新人",  # 無效
            "市瀬あいりエレガンス",  # 無效
            "清宮仁愛",  # 有效
            "半裸水着学園",  # 無效
        ]
        
        filtered = ActressNameFilter.filter_actress_list(mixed_list)
        
        assert len(filtered) == 2
        assert "市瀬あいり" in filtered
        assert "清宮仁愛" in filtered
        assert "新人" not in filtered
        assert "半裸水着学園" not in filtered

    def test_get_most_likely_actress(self):
        """測試選出最可能的女優名字"""
        candidates = [
            "市瀬あいり",  # 較短，包含漢字
            "市瀬あいりエレガンス",  # 較長
            "新人",  # 無效
        ]
        
        best = ActressNameFilter.get_most_likely_actress(candidates)
        assert best == "市瀬あいり"

    def test_hiragana_ratio_filter(self):
        """測試平假名比例過濾"""
        # 平假名比例過高（標題片段）
        high_hiragana = "つい勃起しちゃう"
        assert not ActressNameFilter.is_valid_actress_name(high_hiragana)
        
        # 正常女優名字（漢字+假名）
        normal_name = "桜ゆの"
        assert ActressNameFilter.is_valid_actress_name(normal_name)

    def test_verb_pattern_filter(self):
        """測試動詞片段過濾"""
        verb_fragments = [
            "つい勃起しちゃ",  # 包含 "つい", "しちゃ"
            "田舎帰省で",  # 包含 "で"
            "成長期の",  # 包含 "の"
        ]
        
        for fragment in verb_fragments:
            assert not ActressNameFilter.is_valid_actress_name(fragment), \
                f"動詞片段應該被過濾: {fragment}"

    def test_chinese_title_keywords(self):
        """測試中文標題關鍵字過濾"""
        chinese_titles = [
            "新人出道",
            "巨乳女優",
            "中出解禁",
        ]
        
        for title in chinese_titles:
            assert not ActressNameFilter.is_valid_actress_name(title), \
                f"中文標題應該被過濾: {title}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
