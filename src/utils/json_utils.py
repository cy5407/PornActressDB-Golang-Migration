"""JSON 工具：優先使用 orjson（效能），必要時回退 stdlib json（相容）。

目標：
- 介面盡量貼近 `json` 模組的 load/dump/loads/dumps
- 回傳型別與 `json` 一致：dumps -> str、loads -> object
- 預設使用 UTF-8
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, TextIO

try:
    import orjson  # type: ignore

    _ORJSON_AVAILABLE = True
except Exception:  # pragma: no cover
    orjson = None  # type: ignore
    _ORJSON_AVAILABLE = False


def is_orjson_available() -> bool:
    return _ORJSON_AVAILABLE


def loads(data: str | bytes, /) -> Any:
    """解析 JSON 字串/位元組。"""

    if _ORJSON_AVAILABLE:
        if isinstance(data, str):
            return orjson.loads(data.encode("utf-8"))
        return orjson.loads(data)

    if isinstance(data, bytes):
        data = data.decode("utf-8")
    return json.loads(data)


def dumps(
    obj: Any,
    /,
    *,
    ensure_ascii: bool = False,
    indent: int | None = None,
    sort_keys: bool = False,
    default: Callable[[Any], Any] | None = None,
) -> str:
    """序列化為 JSON 字串（回傳 str，與 stdlib json.dumps 一致）。

    orjson 相容限制：
    - indent 只支援 None 或 2（否則回退 json）
    - ensure_ascii=True 會回退 json（orjson 預設輸出 UTF-8，不做 ASCII escape）
    """

    if _ORJSON_AVAILABLE and not ensure_ascii and (indent in (None, 2)):
        option = 0
        if sort_keys:
            option |= orjson.OPT_SORT_KEYS
        if indent == 2:
            option |= orjson.OPT_INDENT_2

        data_bytes: bytes = orjson.dumps(obj, option=option, default=default)
        return data_bytes.decode("utf-8")

    return json.dumps(
        obj,
        ensure_ascii=ensure_ascii,
        indent=indent,
        sort_keys=sort_keys,
        default=default,
    )


def load(fp: TextIO, /) -> Any:
    """從已開啟的檔案物件讀取並解析 JSON。"""

    return loads(fp.read())


def dump(
    obj: Any,
    fp: TextIO,
    /,
    *,
    ensure_ascii: bool = False,
    indent: int | None = None,
    sort_keys: bool = False,
    default: Callable[[Any], Any] | None = None,
) -> None:
    """將物件寫入已開啟的檔案物件（與 stdlib json.dump 類似）。"""

    fp.write(
        dumps(
            obj,
            ensure_ascii=ensure_ascii,
            indent=indent,
            sort_keys=sort_keys,
            default=default,
        )
    )
