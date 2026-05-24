"""
actress_name_filter.py 覆蓋率補測
目標：覆蓋純邏輯的名字驗證、過濾與候選選擇。
"""

from src.utils.actress_name_filter import ActressNameFilter

# ──────────────────────────────
# helper methods
# ──────────────────────────────


def test_fails_length_check():
    assert ActressNameFilter._fails_length_check("a") is True
    assert ActressNameFilter._fails_length_check("ab") is False
    assert ActressNameFilter._fails_length_check("a" * 16) is True


def test_contains_any_keyword_returns_first_match():
    assert ActressNameFilter._contains_any_keyword("新人巨乳", ["巨乳", "新人"]) == "巨乳"
    assert ActressNameFilter._contains_any_keyword("普通名字", ["巨乳", "新人"]) is None


def test_contains_verb_pattern_and_truncated_title():
    assert ActressNameFilter._contains_verb_pattern("したい") is not None
    assert ActressNameFilter._contains_verb_pattern("山田花子") is None
    assert ActressNameFilter._looks_like_truncated_title("これはとても長い名前の途中ガ") is True
    assert ActressNameFilter._looks_like_truncated_title("短いガ") is False


def test_numeric_or_symbol_only_and_hiragana_ratio():
    assert ActressNameFilter._is_numeric_or_symbol_only("12345!!") is True
    assert ActressNameFilter._is_numeric_or_symbol_only("葵つかさ") is False
    assert ActressNameFilter._fails_hiragana_ratio("あいうえおかき") is True
    assert ActressNameFilter._fails_hiragana_ratio("葵つかさ") is False


def test_passes_language_shape():
    assert ActressNameFilter._passes_language_shape("葵つかさ", False) is True
    assert ActressNameFilter._passes_language_shape("John Doe", False) is True
    assert ActressNameFilter._passes_language_shape("John", False) is False
    assert ActressNameFilter._passes_language_shape("John", True) is True


# ──────────────────────────────
# is_valid_actress_name
# ──────────────────────────────


def test_is_valid_actress_name_accepts_japanese_name():
    assert ActressNameFilter.is_valid_actress_name("葵つかさ") is True


def test_is_valid_actress_name_rejects_bad_patterns():
    assert ActressNameFilter.is_valid_actress_name("新人巨乳") is False
    assert ActressNameFilter.is_valid_actress_name("12345") is False
    assert ActressNameFilter.is_valid_actress_name("あいうえおかき") is False
    assert ActressNameFilter.is_valid_actress_name("John") is False
    assert ActressNameFilter.is_valid_actress_name("John Doe") is True


def test_is_valid_actress_name_optional_single_latin():
    assert ActressNameFilter.is_valid_actress_name("Aoi", allow_single_latin_name=True) is True
    assert ActressNameFilter.is_valid_actress_name("Aoi", allow_single_latin_name=False) is False


# ──────────────────────────────
# filter_actress_list / get_most_likely_actress
# ──────────────────────────────


def test_filter_actress_list_removes_invalid_entries():
    result = ActressNameFilter.filter_actress_list([
        "葵つかさ",
        "新人巨乳",
        "John Doe",
        "12345",
    ])
    assert result == ["葵つかさ", "John Doe"]


def test_filter_actress_list_empty():
    assert ActressNameFilter.filter_actress_list([]) == []


def test_score_actress_name_prefers_kanji_and_shorter_name():
    assert ActressNameFilter._score_actress_name("山田花子") > ActressNameFilter._score_actress_name("Aoi")
    assert ActressNameFilter._score_actress_name("山田") > ActressNameFilter._score_actress_name("山田花子")


def test_get_most_likely_actress_handles_edge_cases():
    assert ActressNameFilter.get_most_likely_actress([]) is None
    assert ActressNameFilter.get_most_likely_actress(["新人巨乳", "12345"]) is None
    assert ActressNameFilter.get_most_likely_actress(["葵つかさ"]) == "葵つかさ"


def test_get_most_likely_actress_prefers_kanji_and_shorter_valid_name():
    # 同為有效候選時，包含漢字且較短者優先
    result = ActressNameFilter.get_most_likely_actress(["Aoi Yuki", "山田花子", "山田"])
    assert result == "山田"
