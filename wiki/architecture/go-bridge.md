# GoBridge 委派架構

> 來源：`MIGRATION_STATUS.md`、`src/services/go_bridge.py`  
> 更新：2026-04-06

---

## 架構概覽

```
Python GUI / 業務邏輯
        ↓
   GoBridge（Facade）
   src/services/go_bridge.py
        ↓
   go_api/*.py（領域 API）
   scan.py / move.py / db.py / identify.py / cache.py
        ↓
   GoCommandRunner
   src/services/go_runner.py
        ↓ subprocess
   classifier.exe（Go CLI）
```

---

## GoBridge 類別

**位置**：`src/services/go_bridge.py`

### 初始化

```python
from services.go_bridge import get_bridge  # 正確取法

bridge = get_bridge()
if bridge.is_available:
    # 使用 Go 加速
```

> ⚠️ **不要用** `self.core.go_bridge`（`UnifiedClassifierCore` 沒有此屬性）  
> → 相關 pitfall：[gui-bridge-wrong-access.md](../pitfalls/gui-bridge-wrong-access.md)

### exe 自動偵測順序

1. `sys._MEIPASS / classifier.exe`（PyInstaller 打包）
2. 專案根目錄 `classifier.exe`
3. 當前工作目錄 `classifier.exe`
4. `%PROGRAMFILES%/classifier/classifier.exe`
5. `$PATH` 中的 `classifier` 或 `classifier.exe`

### 主要公開方法

| 方法 | 說明 |
|------|------|
| `scan_directory(dir, workers, recursive)` | 掃描目錄，回傳 `list[ScanResult]` |
| `move_file(src, dst, strategy)` | 移動單一檔案 |
| `move_dir(src, dst, strategy)` | 移動目錄 |
| `batch_move(items, strategy)` | 批次移動 |
| `list_operations()` | 列出操作歷史 |
| `rollback(id)` | 回滾指定操作 |
| `rollback_last()` | 回滾最近一次 |
| `db_get_video(code, data_dir)` | 取得影片資料 |
| `db_update_video(code, data, data_dir)` | 更新影片 |
| `db_list_videos(data_dir)` | 列出所有番號 |
| `db_fix_studios(data_dir, studios_file, force)` | 批次修正片商 |
| `identify_studio(code)` | 識別片商 |
| `identify_studios_batch(codes)` | 批次識別片商 |

---

## go_api 套件結構

```
src/services/go_api/
├── __init__.py      ← 必須同步 import + __all__
├── scan.py          ← scan_directory()
├── move.py          ← move_file() / batch_move() / rollback()
├── db.py            ← db_get_video() / db_update_video() 等
├── identify.py      ← identify_studio() / list_studios() 等
└── cache.py         ← cache_get() / cache_set() / cache_delete()
```

### 新增函式時必須同步三處

```python
# 1. go_api/db.py — 實作
def db_new_func(data_dir, *, runner=None): ...

# 2. go_api/__init__.py — import
from .db import (
    ...
    db_new_func,   # ← 補上
)
__all__ = [
    ...
    "db_new_func",  # ← 補上
]

# 3. go_bridge.py — 模組層級重匯出
db_new_func = api.db_new_func  # ← 補上
```

→ 詳見 [go-api-export-missing.md](../pitfalls/go-api-export-missing.md)

---

## Go 委派遷移進度（Phase 5 完成）

| Phase | 內容 | 狀態 |
|-------|------|------|
| Phase 1 | go_api runner keyword injection | ✅ 完成 |
| Phase 2 | extractor.py + studio.py 委派 Go | ✅ 完成 |
| Phase 3 | go_accelerated_db / studio 清理 | ✅ 完成 |
| Phase 4A | CacheManager Go core | ✅ 完成 |
| Phase 4B | IncrementalJSONDB get/update 委派 | ✅ 完成 |
| Phase 5 | JSONDBManager 完整委派 | ✅ 完成（243 tests pass） |

### Phase 5 委派清單

| Python 方法 | Go CLI 命令 |
|-------------|-------------|
| `get_video_info` | `db get <code>` |
| `add_or_update_video` | `db update <code> <json>` |
| `delete_video` | `db delete <code>` |
| `get_all_videos` | `db list --full` |

---

## Fallback 策略

```python
# 標準模式：Go 優先，失敗時回退 Python
try:
    if bridge.is_available:
        result = bridge.scan_directory(dir)
    else:
        result = python_scanner.scan(dir)
except GoBridgeError as e:
    logger.warning(f"⚠️ Go 加速失敗，切換 Python: {e}")
    result = python_scanner.scan(dir)
```

---

## data_dir 正確取法

```python
# ✅ 正確：從 db_manager 取得
data_dir = str(getattr(self.core.db_manager, "data_dir", "data/json_db"))

# ❌ 錯誤：不存在的屬性
data_dir = self.core.db_path
```

---

## 相關頁面

- [wiki/architecture/go-cli.md](go-cli.md)
- [wiki/patterns/add-go-api-function.md](../patterns/add-go-api-function.md)
- [wiki/pitfalls/go-api-export-missing.md](../pitfalls/go-api-export-missing.md)
- [wiki/pitfalls/gui-bridge-wrong-access.md](../pitfalls/gui-bridge-wrong-access.md)
