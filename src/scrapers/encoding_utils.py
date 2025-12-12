"""
多編碼檢測與處理工具
解決日文網站內容編碼問題
"""

import logging

import chardet
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class EncodingDetector:
    """多編碼自動檢測器"""

    # 針對日本AV網站優化的編碼優先級序列
    ENCODING_PRIORITIES = [
        "utf-8",
        "shift_jis",  # 日文常用編碼
        "euc-jp",  # 日文EUC編碼
        "cp932",  # Windows日文編碼 (Shift-JIS擴展)
        "iso-2022-jp",  # JIS編碼
        "euc-jisx0213",  # 擴展EUC-JP
        "utf-16",  # Unicode 16位
        "gb2312",  # 簡體中文
        "big5",  # 繁體中文
        "latin1",  # 西歐編碼 (最後備用)
    ]

    def __init__(self):
        self.detection_stats = {
            "total_attempts": 0,
            "successful_detections": 0,
            "encoding_usage": {},
            "chardet_usage": 0,
        }

    def detect_and_decode(self, content_bytes: bytes) -> tuple[str, str]:
        """
        檢測並解碼內容

        Returns:
            Tuple[str, str]: (decoded_content, detected_encoding)
        """
        self.detection_stats["total_attempts"] += 1

        if not content_bytes:
            return "", "unknown"

        # 方法1: 嘗試預定義的編碼優先級序列
        for encoding in self.ENCODING_PRIORITIES:
            try:
                decoded_content = content_bytes.decode(encoding)
                self._update_stats(encoding, True)
                logger.debug(f"✅ 成功使用編碼 {encoding} 解碼內容")
                return decoded_content, encoding

            except (UnicodeDecodeError, UnicodeError):
                continue

        # 方法2: 使用 chardet 自動檢測
        try:
            detected = chardet.detect(content_bytes)
            if detected and detected["encoding"]:
                detected_encoding = detected["encoding"].lower()
                confidence = detected.get("confidence", 0)

                logger.debug(
                    f"🔍 chardet 檢測到編碼: {detected_encoding} (信心度: {confidence:.2f})"
                )

                # 只在信心度足夠高時使用
                if confidence >= 0.7:
                    try:
                        decoded_content = content_bytes.decode(detected_encoding)
                        self._update_stats(detected_encoding, True)
                        self.detection_stats["chardet_usage"] += 1
                        logger.info(f"✅ chardet 成功解碼，編碼: {detected_encoding}")
                        return decoded_content, detected_encoding
                    except (UnicodeDecodeError, UnicodeError):
                        pass

        except Exception as e:
            logger.warning(f"chardet 檢測失敗: {e}")

        # 方法3: 最後備用 - 使用錯誤忽略模式
        try:
            decoded_content = content_bytes.decode("utf-8", errors="ignore")
            self._update_stats("utf-8-ignore", True)
            logger.warning("⚠️ 使用 UTF-8 錯誤忽略模式解碼")
            return decoded_content, "utf-8-ignore"

        except Exception as e:
            logger.error(f"❌ 所有解碼方法都失敗: {e}")
            self._update_stats("failed", False)
            return str(content_bytes), "failed"

    def _update_stats(self, encoding: str, success: bool):
        """更新檢測統計"""
        if success:
            self.detection_stats["successful_detections"] += 1

        if encoding not in self.detection_stats["encoding_usage"]:
            self.detection_stats["encoding_usage"][encoding] = 0
        self.detection_stats["encoding_usage"][encoding] += 1

    def get_stats(self) -> dict:
        """獲取檢測統計資訊"""
        total = self.detection_stats["total_attempts"]
        success_rate = (
            (self.detection_stats["successful_detections"] / total * 100)
            if total > 0
            else 0
        )

        return {
            **self.detection_stats,
            "success_rate": f"{success_rate:.1f}%",
            "most_used_encoding": max(
                self.detection_stats["encoding_usage"].items(),
                key=lambda x: x[1],
                default=("none", 0),
            )[0]
            if self.detection_stats["encoding_usage"]
            else "none",
        }

    def create_soup_with_encoding(
        self, content_bytes: bytes, parser: str = "html.parser"
    ) -> tuple[BeautifulSoup, str]:
        """
        創建 BeautifulSoup 物件並自動處理編碼

        Args:
            content_bytes: 原始網頁位元組
            parser: HTML解析器類型

        Returns:
            Tuple[BeautifulSoup, str]: (soup物件, 使用的編碼)
        """
        decoded_content, encoding = self.detect_and_decode(content_bytes)

        try:
            # 使用檢測到的編碼明確指定給BeautifulSoup
            if encoding != "failed":
                soup = BeautifulSoup(
                    content_bytes,
                    parser,
                    from_encoding=encoding if encoding != "utf-8-ignore" else "utf-8",
                )
            else:
                # 備用方案：直接使用字符串
                soup = BeautifulSoup(decoded_content, parser)

            logger.debug(f"🍲 已創建 BeautifulSoup 物件，編碼: {encoding}")
            return soup, encoding

        except Exception as e:
            logger.error(f"❌ 創建 BeautifulSoup 物件失敗: {e}")
            # 最後備用方案
            soup = BeautifulSoup(decoded_content, parser)
            return soup, encoding


# 便利函數
def safe_decode_content(content_bytes: bytes) -> tuple[str, str]:
    """
    安全解碼網頁內容的便利函數

    Args:
        content_bytes: 原始位元組內容

    Returns:
        Tuple[str, str]: (解碼後的字符串, 使用的編碼)
    """
    detector = EncodingDetector()
    return detector.detect_and_decode(content_bytes)


def create_safe_soup(
    content_bytes: bytes, parser: str = "html.parser"
) -> tuple[BeautifulSoup, str]:
    """
    創建安全的 BeautifulSoup 物件的便利函數

    Args:
        content_bytes: 原始位元組內容
        parser: HTML解析器類型

    Returns:
        Tuple[BeautifulSoup, str]: (BeautifulSoup物件, 使用的編碼)
    """
    detector = EncodingDetector()
    return detector.create_soup_with_encoding(content_bytes, parser)


def validate_japanese_content(text: str) -> dict:
    """
    驗證日文內容的完整性

    Args:
        text: 待驗證的文本

    Returns:
        dict: 驗證結果統計
    """
    import re

    # 日文字符集統計
    hiragana_count = len(re.findall(r"[\u3040-\u309F]", text))  # 平假名
    katakana_count = len(re.findall(r"[\u30A0-\u30FF]", text))  # 片假名
    kanji_count = len(re.findall(r"[\u4E00-\u9FAF]", text))  # 漢字

    total_japanese = hiragana_count + katakana_count + kanji_count
    total_chars = len(text)

    # 檢查亂碼字符
    replacement_chars = text.count("�")  # Unicode 替換字符
    question_marks = text.count("?")  # 問號 (可能的編碼錯誤)

    japanese_ratio = (total_japanese / total_chars * 100) if total_chars > 0 else 0
    error_ratio = (
        ((replacement_chars + question_marks) / total_chars * 100)
        if total_chars > 0
        else 0
    )

    return {
        "total_chars": total_chars,
        "japanese_chars": total_japanese,
        "hiragana_count": hiragana_count,
        "katakana_count": katakana_count,
        "kanji_count": kanji_count,
        "japanese_ratio": f"{japanese_ratio:.1f}%",
        "replacement_chars": replacement_chars,
        "question_marks": question_marks,
        "error_ratio": f"{error_ratio:.1f}%",
        "encoding_quality": "good"
        if error_ratio < 5 and japanese_ratio > 10
        else "poor",
    }


class EncodingWarningFilter(logging.Filter):
    """過濾 BeautifulSoup 編碼警告的日誌過濾器"""

    def filter(self, record):
        # 過濾掉特定的 BeautifulSoup 編碼警告
        if "Some characters could not be decoded" in record.getMessage():
            return False
        if "REPLACEMENT CHARACTER" in record.getMessage():
            return False
        return True


def install_encoding_warning_filter():
    """安裝編碼警告過濾器到 bs4.dammit logger"""
    bs4_logger = logging.getLogger("bs4.dammit")
    filter_obj = EncodingWarningFilter()
    bs4_logger.addFilter(filter_obj)
    logger.info("🔇 已安裝 BeautifulSoup 編碼警告過濾器")
