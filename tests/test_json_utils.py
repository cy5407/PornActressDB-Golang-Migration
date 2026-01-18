"""
測試 JSON 工具模組
"""

import json
import tempfile
from pathlib import Path

import pytest

from src.utils.json_utils import dump, dumps, is_orjson_available, load, loads


class TestJsonUtils:
    """測試 JSON 工具函式"""

    def test_is_orjson_available(self):
        """測試 orjson 可用性檢查"""
        result = is_orjson_available()
        assert isinstance(result, bool)

    def test_loads_string(self):
        """測試載入 JSON 字串"""
        data = '{"key": "value", "number": 42}'
        result = loads(data)
        assert result == {"key": "value", "number": 42}

    def test_loads_bytes(self):
        """測試載入 JSON 位元組"""
        data = b'{"key": "value", "number": 42}'
        result = loads(data)
        assert result == {"key": "value", "number": 42}

    def test_loads_chinese(self):
        """測試載入中文 JSON"""
        data = '{"名稱": "測試", "數字": 123}'
        result = loads(data)
        assert result == {"名稱": "測試", "數字": 123}

    def test_dumps_basic(self):
        """測試基本序列化"""
        obj = {"key": "value", "number": 42}
        result = dumps(obj)
        assert json.loads(result) == obj

    def test_dumps_chinese(self):
        """測試中文序列化"""
        obj = {"名稱": "測試", "數字": 123}
        result = dumps(obj)
        assert "測試" in result  # 確保不是 escaped

    def test_dumps_with_indent(self):
        """測試帶縮排的序列化"""
        obj = {"key": "value", "nested": {"inner": "data"}}
        result = dumps(obj, indent=2)
        assert "\n" in result
        assert "  " in result

    def test_dumps_sort_keys(self):
        """測試排序鍵值"""
        obj = {"z": 1, "a": 2, "m": 3}
        result = dumps(obj, sort_keys=True)
        parsed = json.loads(result)
        assert list(parsed.keys()) == ["a", "m", "z"]

    def test_dumps_ensure_ascii(self):
        """測試 ASCII 編碼"""
        obj = {"中文": "測試"}
        result = dumps(obj, ensure_ascii=True)
        assert "\\u" in result

    def test_load_from_file(self):
        """測試從檔案載入"""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            json.dump({"test": "data"}, f)
            temp_path = f.name

        try:
            with open(temp_path, "r") as f:
                result = load(f)
            assert result == {"test": "data"}
        finally:
            Path(temp_path).unlink()

    def test_dump_to_file(self):
        """測試寫入檔案"""
        obj = {"test": "data", "number": 42}
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            temp_path = f.name

        try:
            with open(temp_path, "w") as f:
                dump(obj, f)

            with open(temp_path, "r") as f:
                result = json.load(f)
            assert result == obj
        finally:
            Path(temp_path).unlink()

    def test_dump_with_indent(self):
        """測試帶縮排寫入檔案"""
        obj = {"key": "value", "nested": {"inner": "data"}}
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            temp_path = f.name

        try:
            with open(temp_path, "w") as f:
                dump(obj, f, indent=2)

            with open(temp_path, "r") as f:
                content = f.read()
            assert "\n" in content
        finally:
            Path(temp_path).unlink()

    def test_roundtrip(self):
        """測試往返轉換"""
        original = {
            "string": "value",
            "number": 42,
            "float": 3.14,
            "list": [1, 2, 3],
            "nested": {"inner": "data"},
            "中文": "測試",
        }
        serialized = dumps(original)
        deserialized = loads(serialized)
        assert deserialized == original
