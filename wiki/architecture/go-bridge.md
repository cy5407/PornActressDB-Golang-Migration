# GoBridge 委派架構（現況：go_cli.py）

> 來源：`MIGRATION_STATUS.md`、`src/services/go_cli.py`
> 更新：2026-04-19（drift audit：W6 後 go_bridge.py / go_api / go_runner.py 已全數移除）

---

## ⚠️ 架構重要變更（2026-04-07，W6）

舊架構的 Python→Go 橋接層已**全數移除**：

| 已移除 | 行數 | 說明 |
|--------|------|------|
| `src/services/go_bridge.py` | 146 | GoBridge Facade |
| `src/services/go_runner.py` | 102 | subprocess 執行器 |
| `src/services/go_api/` | ~1,339 | 領域 API 層（scan/move/db/identify/cache） |
| `src/ui/` | ~2,588 | Python Tkinter GUI |

**目前唯一的 Python→Go 橋接點**：`src/services/go_cli.py`

---

## 現行架構

```
Wails GUI（React）
      ↓ Wails binding（直接呼叫 Go 函數）
wails-app/backend/app.go
      ↓ Go 直接 import
pkg/ (extractor / mover / database / studio / cache)
      ↓ subprocess（搜尋專用）
Python 爬蟲（src/scrapers/run_search.py）

Python 搜尋管線（非 Wails 路徑，如 scanner.py）
      ↓
src/services/go_cli.py  ← Python 呼叫 classifier.exe 的唯一入口
      ↓ subprocess
classifier.exe（Go CLI）
```

---

## go_cli.py（現行橋接層）

**位置**：`src/services/go_cli.py`

### 使用方式

```python
from services.go_cli import is_available, run

# 確認 Go CLI 可用
if not is_available(exe_path):
    raise RuntimeError("Go CLI 不可用")

# 執行命令
result = run(["db", "get", "STARS-707"], exe_path=exe_path)
```

### exe 自動偵測順序

1. 呼叫方傳入的 `exe_path` 參數
2. `_resolve_exe()` 自動找尋：
   - 與腳本同目錄的 `classifier.exe`
   - 當前工作目錄 `classifier.exe`
   - `$PATH` 中的 `classifier` 或 `classifier.exe`

### WSL 支援

`go_cli.py` 含 WSL↔Windows 路徑轉換（`wslpath`），支援在 WSL 環境下呼叫 Windows `classifier.exe`。

---

## Phase 委派遷移進度（已全數完成）

| Phase | 內容 | 狀態 |
|-------|------|------|
| Phase 1 | go_api runner keyword injection | ✅ 完成 |
| Phase 2 | extractor.py + studio.py 委派 Go | ✅ 完成 |
| Phase 3 | go_accelerated_db / studio 清理 | ✅ 完成 |
| Phase 4A | CacheManager Go core | ✅ 完成 |
| Phase 4B | IncrementalJSONDB get/update 委派 | ✅ 完成 |
| Phase 5 | JSONDBManager 完整委派 | ✅ 完成 |
| Phase 6 | **全數移除 Python fallback**（~1,440 行） | ✅ 完成 |
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
| **W1~W6** | **Wails GUI 取代 Tkinter；go_bridge/go_api/go_runner 全移除** | ✅ 完成（2026-04-07） |

---

## Phase 10+ 後的委派策略

Phase 10 完成後，所有方法直接委派 Go，不再有 availability guard。

```python
# Phase 10 之後：直接委派，不再有 guard
def add_or_update_video(self, code, data):
    result = go_cli.run(["db", "update", code, ...], exe_path=self.exe_path)
    if not result:
        raise RuntimeError(f"Go CLI 無法更新影片 {code}")
    return result

# 唯一合法的記憶體讀取 fallback（保留）
def get_all_videos(self):
    try:
        return go_cli.run(["db", "list", "--full"], exe_path=self.exe_path)
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

## 相關頁面

- [wiki/architecture/go-cli.md](go-cli.md)
- [wiki/architecture/wails-gui.md](wails-gui.md)
- [wiki/pitfalls/go-api-export-missing.md](../pitfalls/go-api-export-missing.md)
- [wiki/pitfalls/gui-bridge-wrong-access.md](../pitfalls/gui-bridge-wrong-access.md)
