---
category: Go
date: 2026-04-06
---
# Issue 14：go_api 匯出遺漏 → AttributeError

**日期**：2026-04-06  
**嚴重度**：🔴 高（功能完全無法使用）

---

## 症狀

```text
AttributeError: module 'services.go_api' has no attribute 'db_fix_studios'
```

點擊 GUI 按鈕後立即崩潰，即使 `go_api/db.py` 中已有 `db_fix_studios()` 函式。

---

## 根本原因

`go_api/` 套件是三層匯出架構，新增函式後需要**同步三個地方**，任何一層遺漏都會導致 AttributeError：

```
go_api/db.py          ← 第一層：函式實作
go_api/__init__.py    ← 第二層：套件 import + __all__
go_bridge.py          ← 第三層：模組層級重匯出（供 GUI 直接使用）
```

只在 `db.py` 加函式，`__init__.py` 和 `go_bridge.py` 沒有更新，Python 從模組層級找不到此函式。

---

## 修正：三處同步

### 1. `go_api/db.py` — 實作函式

```python
def db_fix_studios(
    data_dir: str | None = None,
    studios_file: str | None = None,
    force: bool = False,
    *,
    runner: GoCommandRunner | None = None,
) -> dict:
    r = _get_runner(runner)
    args = ["db", "fix-studios"]
    if data_dir:
        args += ["-data-dir", data_dir]
    if studios_file:
        args += ["-studios-file", studios_file]
    if force:
        args.append("-force")
    return r.run_json(args)
```

### 2. `go_api/__init__.py` — import + __all__

```python
from .db import (
    db_get_video,
    db_update_video,
    # ... 其他函式
    db_fix_studios,   # ← 補上
)

__all__ = [
    "db_get_video",
    "db_update_video",
    # ... 其他
    "db_fix_studios",  # ← 補上
]
```

### 3. `go_bridge.py` — 模組層級重匯出

```python
import src.services.go_api as api

db_fix_studios = api.db_fix_studios  # ← 補上
```

---

## 診斷方法

發生 AttributeError 時，先確認三層是否一致：

```python
# 在 Python REPL 中快速驗證
import src.services.go_api as api
print(dir(api))          # 看 __init__.py 有沒有匯出

from src.services import go_bridge
print(hasattr(go_bridge, 'db_fix_studios'))  # 看 go_bridge.py 有沒有重匯出
```

---

## 預防

每次新增函式後，使用 checklist：

- [ ] `go_api/db.py`（或 cache.py / identify.py）— 實作函式
- [ ] `go_api/__init__.py` — import + `__all__`
- [ ] `go_bridge.py` — 模組層級重匯出

→ 詳見 [patterns/add-go-api-function.md](../patterns/add-go-api-function.md)
