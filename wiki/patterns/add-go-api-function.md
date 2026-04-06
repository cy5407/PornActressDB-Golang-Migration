# 新增 Go API 函式 ← 必讀

> **每次**在 `go_api/` 新增公開函式，必須同步更新以下三個地方，缺一不可。

---

## 📋 三步驟 Checklist

```
[ ] Step 1: go_api/<module>.py   ← 實作函式本體
[ ] Step 2: go_api/__init__.py   ← import + __all__ 補上
[ ] Step 3: go_bridge.py         ← 模組層級重匯出補上
```

---

## Step 1：`go_api/<module>.py` 實作

以 `db_fix_studios` 為例：

```python
# src/services/go_api/db.py
def db_fix_studios(
    data_dir: str = "data/json_db",
    studios_file: str = "studios.json",
    force: bool = False,
    *,
    runner: GoCommandRunner | None = None,
) -> dict:
    r = _get_runner(runner)
    cmd = ["db", "fix-studios", "--data-dir", data_dir, "--studios", studios_file, "--json"]
    if force:
        cmd.append("--force")
    result = r.run(cmd, timeout=120)
    data = r.parse_json(result.stdout)
    ...
```

---

## Step 2：`go_api/__init__.py` 同步

```python
# src/services/go_api/__init__.py

from .db import (
    db_compact_journal,
    db_delete_video,
    db_fix_studios,    # ← 補上 import
    db_get_stats,
    ...
)

__all__ = [
    ...
    "db_fix_studios",  # ← 補上 __all__
    ...
]
```

---

## Step 3：`go_bridge.py` 模組層級重匯出

```python
# src/services/go_bridge.py（第 19-30 行附近）

db_compact_journal = api.db_compact_journal
db_delete_video = api.db_delete_video
db_fix_studios = api.db_fix_studios    # ← 補上
db_get_stats = api.db_get_stats
...
```

GoBridge 類別內的 one-liner 也要補：

```python
class GoBridge:
    def db_fix_studios(self, data_dir="data/json_db", studios_file="studios.json", force=False) -> dict:
        return api.db_fix_studios(data_dir, studios_file, force, runner=self._runner)
```

---

## 為什麼有三個地方？

`go_bridge.py` 用 `import services.go_api as api` 匯入整個 **package**，因此呼叫的是 `api.db_fix_studios`。Python package 的公開介面由 `__init__.py` 決定，若未在 `__init__.py` 匯出，`api.<function>` 就找不到（AttributeError）。

`go_bridge.py` 第 19-30 行的模組層級重匯出是為了讓呼叫方可以直接 `from services.go_bridge import db_fix_studios`，不須透過 GoBridge 實例。

---

## 相關踩坑

- [go_api 匯出遺漏](../pitfalls/go-api-export-missing.md)（Issue 14）
