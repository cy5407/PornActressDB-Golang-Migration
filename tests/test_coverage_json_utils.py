"""
json_utils.py 覆蓋率補測
目標：覆蓋純 JSON 包裝層的 orjson / stdlib fallback 行為。
"""

from io import StringIO

import pytest

import src.utils.json_utils as json_utils


# ──────────────────────────────
# availability
# ──────────────────────────────


def test_is_orjson_available_returns_bool():
    assert isinstance(json_utils.is_orjson_available(), bool)


# ──────────────────────────────
# loads / dumps / load / dump
# ──────────────────────────────


def test_loads_accepts_str_and_bytes_roundtrip():
    payload = {"a": 1, "b": [2, 3]}
    dumped = json_utils.dumps(payload, sort_keys=True)
    assert json_utils.loads(dumped) == payload
    assert json_utils.loads(dumped.encode("utf-8")) == payload


def test_dumps_returns_string_and_respects_ascii_and_indent():
    payload = {"日本語": "テスト", "n": 1}

    text = json_utils.dumps(payload, ensure_ascii=True, sort_keys=True)
    assert isinstance(text, str)
    assert "\\u65e5\\u672c\\u8a9e" in text

    pretty = json_utils.dumps(payload, indent=2, sort_keys=True)
    assert isinstance(pretty, str)
    assert "\n  " in pretty


def test_load_and_dump_file_objects():
    buf = StringIO()
    json_utils.dump({"x": 1}, buf, sort_keys=True)
    assert buf.getvalue() in ('{"x":1}', '{"x": 1}')

    buf.seek(0)
    assert json_utils.load(buf) == {"x": 1}


# ──────────────────────────────
# fallback-specific branches
# ──────────────────────────────


def test_orjson_branch_fallback_to_stdlib_when_indent_is_not_supported(monkeypatch):
    """orjson 可用時，indent=4 應走 stdlib json 路徑。"""
    if not json_utils.is_orjson_available():
        pytest.skip("orjson unavailable in this environment")

    payload = {"a": 1}
    text = json_utils.dumps(payload, indent=4, sort_keys=True)
    assert text.startswith("{\n")
    assert "    \"a\"" in text


def test_orjson_branch_fallback_to_stdlib_when_ensure_ascii_true(monkeypatch):
    """orjson 可用時，ensure_ascii=True 應走 stdlib json 路徑。"""
    if not json_utils.is_orjson_available():
        pytest.skip("orjson unavailable in this environment")

    payload = {"日本語": "テスト"}
    text = json_utils.dumps(payload, ensure_ascii=True, sort_keys=True)
    assert "\\u65e5\\u672c\\u8a9e" in text
