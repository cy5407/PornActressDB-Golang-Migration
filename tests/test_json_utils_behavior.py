"""
json_utils 行為測試

目標：驗證 JSON 包裝層對外承諾的行為：
- loads / dumps 的 round-trip
- non-ASCII 與 ensure_ascii 行為
- file object load / dump
- default callable 序列化
"""

from io import StringIO

from src.utils.json_utils import dump, dumps, load, loads


class CustomObject:
    def __init__(self, value: int):
        self.value = value


def test_json_roundtrip_preserves_nested_structure():
    payload = {
        "title": "測試",
        "count": 3,
        "items": [1, 2, {"nested": True}],
    }

    text = dumps(payload, sort_keys=True)
    restored = loads(text)

    assert restored == payload


def test_dumps_preserves_unicode_by_default():
    payload = {"名稱": "測試", "片商": "S1"}

    text = dumps(payload)

    assert "測試" in text
    assert "\\u6e2c\\u8a66" not in text


def test_dumps_escapes_unicode_when_ensure_ascii_enabled():
    payload = {"名稱": "測試"}

    text = dumps(payload, ensure_ascii=True)

    assert "\\u540d\\u7a31" in text
    assert "\\u6e2c\\u8a66" in text


def test_dump_and_load_work_with_file_like_objects():
    payload = {"code": "SONE-123", "actresses": ["葵つかさ"]}
    buf = StringIO()

    dump(payload, buf, sort_keys=True)
    buf.seek(0)

    restored = load(buf)
    assert restored == payload


def test_dumps_supports_default_callable_for_custom_objects():
    payload = {"obj": CustomObject(7)}

    text = dumps(payload, default=lambda obj: {"value": obj.value}, sort_keys=True)
    restored = loads(text)

    assert restored == {"obj": {"value": 7}}


def test_loads_accepts_bytes_input():
    payload = {"key": "value", "num": 42}
    text = dumps(payload)

    restored = loads(text.encode("utf-8"))

    assert restored == payload
