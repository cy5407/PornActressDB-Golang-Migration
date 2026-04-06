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
├── db.py            ← db_get_video() / db_update_video() / db_get_actress() /
│                      db_backup_create() / db_backup_restore() 等
├── identify.py      ← identify_studio() / list_studios() 等
└── cache.py         ← cache_get() / cache_set() / cache_delete() /
                       cache_get_stats() / cache_prune() / cache_clear()
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

## Go 委派遷移進度（Phase 6 完成）

| Phase | 內容 | 狀態 |
|-------|------|------|
| Phase 1 | go_api runner keyword injection | ✅ 完成 |
| Phase 2 | extractor.py + studio.py 委派 Go | ✅ 完成 |
| Phase 3 | go_accelerated_db / studio 清理 | ✅ 完成 |
| Phase 4A | CacheManager Go core | ✅ 完成 |
| Phase 4B | IncrementalJSONDB get/update 委派 | ✅ 完成 |
| Phase 5 | JSONDBManager 完整委派 | ✅ 完成 |
| Phase 6 | **全數移除 Python fallback**（~1,440 行） | ✅ 完成（226 tests，1.9s） |
| Phase 7A | Actress CRUD Go（GetActress/Upsert/Delete/List） | ✅ 完成 |
| Phase 7B | 統計 Go 委派（GetActressStats/GetStudioStats） | ✅ 完成 |
| Phase 7C | Cache cleanup 委派（prune/clear/stats） | ✅ 完成 |
| Phase 7D | Backup/Restore Go（BackupCreate/Restore/List/Cleanup） | ✅ 完成 |
| Phase 7E | json_database.py Python fallback 瘦身（-137 行） | ✅ 完成 |
| Phase 8A | json_database.py backup fallback 全移除（-82 行） | ✅ 完成 |
| Phase 8B | cache_manager.py 5 個方法 fallback 全移除（-222 行） | ✅ 完成 |
| Phase 9A | e2e 整合測試（db/cache/identify/scan/bridge） | ✅ 完成 |
| Phase 9B | GoBridgeError 語意細化（ExecError/NotFoundError/JSONError） | ✅ 完成 |
| Phase 9C | IncrementalJSONDB add_video/delete_video 委派 Go | ✅ 完成 |
| Phase 9D | 文件收尾（wiki / 計畫 / 完成記錄） | ✅ 完成 |
| Phase 10 | **Go availability guards 全移除**（json_db / incremental / cache） | ✅ 完成（247 tests，直接委派） |
| Phase 11 | extractor siteRe 通用化 + CI e2e 整合 | ✅ 完成 |

### Phase 10+ 後的委派策略

Phase 10 完成後，`_GO_DB_AVAILABLE` guard 已全數移除。所有方法直接委派 Go，不再有可用性檢查。

```python
# Phase 10 之後：直接委派，不再有 guard
def add_or_update_video(self, code, data):
    result = db_update_video(code, data, data_dir=str(self.data_dir))
    if not result:
        raise RuntimeError(f"Go CLI 無法更新影片 {code}")
    return result

# 唯一合法的記憶體讀取 fallback（保留）
def get_all_videos(self):
    try:
        return db_get_all_videos(data_dir=str(self.data_dir))
    except Exception:
        return dict(self.data.get("videos", {}))  # ← 記憶體 cache
```

**判斷標準**：
| 操作類型 | Go 不可用時 |
|---------|------------|
| 寫入（add/update/delete） | `raise RuntimeError` |
| 磁碟讀取（backup list、cache stats） | `raise RuntimeError` |
| **記憶體讀取**（`self.data` 已載入） | **保留輕量 fallback** |
| 工具性功能（backup/cache cleanup） | `raise RuntimeError` |

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
