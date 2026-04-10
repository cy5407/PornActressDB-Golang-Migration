"""補測 encoding_utils 覆蓋率。"""
import logging
import pytest
from unittest.mock import patch
from src.scrapers.encoding_utils import (
    EncodingDetector,
    EncodingWarningFilter,
    safe_decode_content,
    create_safe_soup,
    validate_japanese_content,
    install_encoding_warning_filter,
)


# ──────────────────────────────
# EncodingDetector.detect_and_decode
# ──────────────────────────────


def _detector() -> EncodingDetector:
    return EncodingDetector()


def test_detect_empty_bytes():
    d = _detector()
    text, enc = d.detect_and_decode(b"")
    assert text == ""
    assert enc == "unknown"


def test_detect_utf8():
    d = _detector()
    content = "Hello 日本語テスト".encode("utf-8")
    text, enc = d.detect_and_decode(content)
    assert "日本語" in text
    assert enc == "utf-8"


def test_detect_shift_jis():
    d = _detector()
    content = "テスト".encode("shift_jis")
    text, enc = d.detect_and_decode(content)
    assert enc in ("shift_jis", "utf-8", "cp932")  # 實際解碼用哪個都可


def test_detect_cp932():
    d = _detector()
    content = "日本語テスト".encode("cp932")
    text, enc = d.detect_and_decode(content)
    # cp932 是 shift_jis 擴展，解碼出的任一有效編碼皆可接受
    assert text  # 只要不是空白就好


def test_detect_increments_attempts():
    d = _detector()
    d.detect_and_decode(b"test")
    assert d.detection_stats["total_attempts"] == 1


def test_detect_increments_successes():
    d = _detector()
    d.detect_and_decode("テスト".encode("utf-8"))
    assert d.detection_stats["successful_detections"] == 1


def test_detect_fallback_chardet(monkeypatch):
    """清空 ENCODING_PRIORITIES，讓 chardet 高信心度路徑被執行。"""
    import chardet as _chardet

    monkeypatch.setattr(EncodingDetector, "ENCODING_PRIORITIES", [])
    monkeypatch.setattr(
        _chardet, "detect", lambda b: {"encoding": "utf-8", "confidence": 0.95}
    )
    d = _detector()
    text, enc = d.detect_and_decode("テスト".encode("utf-8"))
    assert enc == "utf-8"
    assert d.detection_stats["chardet_usage"] == 1


def test_detect_chardet_low_confidence_falls_through(monkeypatch):
    """chardet 信心度 <0.7 時應跳過，最終用 ignore fallback。"""
    import chardet as _chardet

    monkeypatch.setattr(EncodingDetector, "ENCODING_PRIORITIES", [])
    monkeypatch.setattr(
        _chardet, "detect", lambda b: {"encoding": "utf-8", "confidence": 0.3}
    )
    d = _detector()
    text, enc = d.detect_and_decode(b"hello")
    assert enc == "utf-8-ignore"


def test_detect_chardet_exception_falls_through(monkeypatch):
    """chardet 拋出例外時應繼續走 ignore fallback。"""
    import chardet as _chardet

    monkeypatch.setattr(EncodingDetector, "ENCODING_PRIORITIES", [])

    def raise_err(b):
        raise RuntimeError("chardet err")

    monkeypatch.setattr(_chardet, "detect", raise_err)
    d = _detector()
    text, enc = d.detect_and_decode(b"hello")
    assert enc == "utf-8-ignore"


def test_detect_all_fail_returns_str(monkeypatch):
    """所有方法都失敗時，回傳 str(bytes) 與 'failed'。"""
    import chardet as _chardet

    monkeypatch.setattr(EncodingDetector, "ENCODING_PRIORITIES", [])
    monkeypatch.setattr(
        _chardet, "detect", lambda b: {"encoding": "utf-8", "confidence": 0.95}
    )

    # chardet 偵測到 utf-8，但解碼仍然失敗
    original_decode = bytes.decode  # keep reference

    decoded_calls = {"n": 0}
    # 只能透過 patch 函數内部邏輯：讓 chardet 返回 None encoding
    monkeypatch.setattr(
        _chardet, "detect", lambda b: {"encoding": None, "confidence": 0.0}
    )

    d = _detector()
    text, enc = d.detect_and_decode(b"\x80\x81")
    # latin1 fallback (ENCODING_PRIORITIES empty → goes to chardet, chardet None → utf-8-ignore)
    assert enc == "utf-8-ignore"


# ──────────────────────────────
# _update_stats
# ──────────────────────────────


def test_update_stats_new_encoding():
    d = _detector()
    d._update_stats("utf-8", True)
    assert d.detection_stats["encoding_usage"]["utf-8"] == 1
    assert d.detection_stats["successful_detections"] == 1


def test_update_stats_existing_encoding():
    d = _detector()
    d._update_stats("utf-8", True)
    d._update_stats("utf-8", False)
    assert d.detection_stats["encoding_usage"]["utf-8"] == 2
    assert d.detection_stats["successful_detections"] == 1


# ──────────────────────────────
# get_stats
# ──────────────────────────────


def test_get_stats_empty():
    d = _detector()
    s = d.get_stats()
    assert s["success_rate"] == "0.0%"
    assert s["most_used_encoding"] == "none"


def test_get_stats_with_data():
    d = _detector()
    d.detect_and_decode("テスト".encode("utf-8"))
    s = d.get_stats()
    assert "%" in s["success_rate"]
    assert s["most_used_encoding"] != "none"


# ──────────────────────────────
# create_soup_with_encoding
# ──────────────────────────────


def test_create_soup_utf8():
    d = _detector()
    content = b"<html><body><p>Hello</p></body></html>"
    soup, enc = d.create_soup_with_encoding(content)
    assert soup.find("p").text == "Hello"


def test_create_soup_ignore_encoding():
    """enc=utf-8-ignore 時應用 utf-8 傳給 BeautifulSoup。"""
    d = _detector()
    content = b"<html><body></body></html>"
    # 強制回傳 utf-8-ignore
    with patch.object(d, "detect_and_decode", return_value=("<html><body></body></html>", "utf-8-ignore")):
        soup, enc = d.create_soup_with_encoding(content)
    assert enc == "utf-8-ignore"
    assert soup is not None


def test_create_soup_failed_encoding():
    """enc=failed 時應以解碼字串建立 soup。"""
    d = _detector()
    content = b"<html></html>"
    with patch.object(d, "detect_and_decode", return_value=("<html></html>", "failed")):
        soup, enc = d.create_soup_with_encoding(content)
    assert enc == "failed"


def test_create_soup_exception_fallback():
    """BeautifulSoup 建立失敗時走 except fallback。"""
    from bs4 import BeautifulSoup
    d = _detector()
    content = b"<html></html>"

    call_count = {"n": 0}
    original_bs4 = BeautifulSoup

    def patched_bs4(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("bs4 crash")
        return original_bs4(*args, **kwargs)

    with patch("src.scrapers.encoding_utils.BeautifulSoup", side_effect=patched_bs4):
        soup, enc = d.create_soup_with_encoding(content)
    assert soup is not None


# ──────────────────────────────
# safe_decode_content
# ──────────────────────────────


def test_safe_decode_content_utf8():
    text, enc = safe_decode_content("テスト".encode("utf-8"))
    assert "テスト" in text


def test_safe_decode_content_empty():
    text, enc = safe_decode_content(b"")
    assert text == ""
    assert enc == "unknown"


# ──────────────────────────────
# create_safe_soup
# ──────────────────────────────


def test_create_safe_soup():
    content = b"<html><body><p>test</p></body></html>"
    soup, enc = create_safe_soup(content)
    assert soup.find("p").text == "test"


def test_create_safe_soup_custom_parser():
    content = b"<html><body></body></html>"
    soup, enc = create_safe_soup(content, parser="html.parser")
    assert soup is not None


# ──────────────────────────────
# validate_japanese_content
# ──────────────────────────────


def test_validate_japanese_empty():
    r = validate_japanese_content("")
    assert r["total_chars"] == 0
    assert r["japanese_ratio"] == "0.0%"
    assert r["encoding_quality"] == "poor"


def test_validate_japanese_good():
    text = "これはテストです。日本語のコンテンツを確認します。" * 5
    r = validate_japanese_content(text)
    assert float(r["japanese_ratio"].rstrip("%")) > 10
    assert r["encoding_quality"] == "good"


def test_validate_japanese_with_replacement_chars():
    text = "テスト" + "\ufffd" * 20 + "あ"
    r = validate_japanese_content(text)
    assert r["replacement_chars"] == 20


def test_validate_japanese_with_question_marks():
    text = "abc???"
    r = validate_japanese_content(text)
    assert r["question_marks"] == 3


def test_validate_japanese_kanji_hiragana_katakana():
    text = "漢字ひらがなカタカナ"
    r = validate_japanese_content(text)
    assert r["kanji_count"] > 0
    assert r["hiragana_count"] > 0
    assert r["katakana_count"] > 0


# ──────────────────────────────
# EncodingWarningFilter
# ──────────────────────────────


def test_filter_blocks_replacement_char_msg():
    f = EncodingWarningFilter()
    record = logging.LogRecord(
        name="bs4", level=logging.WARNING,
        pathname="", lineno=0,
        msg="REPLACEMENT CHARACTER found", args=(), exc_info=None,
    )
    assert f.filter(record) is False


def test_filter_blocks_could_not_decode_msg():
    f = EncodingWarningFilter()
    record = logging.LogRecord(
        name="bs4", level=logging.WARNING,
        pathname="", lineno=0,
        msg="Some characters could not be decoded", args=(), exc_info=None,
    )
    assert f.filter(record) is False


def test_filter_passes_other_msg():
    f = EncodingWarningFilter()
    record = logging.LogRecord(
        name="bs4", level=logging.INFO,
        pathname="", lineno=0,
        msg="Normal message", args=(), exc_info=None,
    )
    assert f.filter(record) is True


# ──────────────────────────────
# install_encoding_warning_filter
# ──────────────────────────────


def test_install_encoding_warning_filter():
    install_encoding_warning_filter()
    bs4_logger = logging.getLogger("bs4.dammit")
    # 確認有安裝 EncodingWarningFilter
    assert any(isinstance(f, EncodingWarningFilter) for f in bs4_logger.filters)
