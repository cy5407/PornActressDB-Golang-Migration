# Python→Go 橋接層：go_cli.py

> 來源：`src/services/go_cli.py`、`AGENTS.md`
> 更新：2026-04-19（drift audit：完整重寫，反映 W6 後唯一橋接層現況）

---

## 概述

**目前唯一的 Python→Go 橋接點**：`src/services/go_cli.py`

舊架構的橋接層已於 W6（2026-04-07）**全數移除**：

| 已移除 | 說明 |
|--------|------|
| `src/services/go_bridge.py` | GoBridge Facade（146 行） |
| `src/services/go_runner.py` | subprocess 執行器（102 行） |
| `src/services/go_api/` | 領域 API 層（scan/move/db/identify/cache，約 1,339 行） |
| `src/ui/` | Python Tkinter GUI（約 2,588 行） |

---

## 架構設計：模組級函式（無類別）

`go_cli.py` **不使用類別**，全部以模組級函式暴露：

```python
from services import go_cli

# 核心執行函式
go_cli.run(args, exe_path=None)          # 執行 classifier，回傳 CompletedProcess
go_cli.run_json(args, exe_path=None)     # 執行並解析 JSON 輸出，回傳 dict/list

# 可用性檢查
go_cli.is_available(exe_path=None)       # 回傳 bool

# DB 相關便捷函式
go_cli.db_get_video(code, exe_path=None)
go_cli.db_update_video(code, data, exe_path=None)
go_cli.db_delete_video(code, exe_path=None)
go_cli.db_list_videos(exe_path=None)
go_cli.db_stats(exe_path=None)
go_cli.db_compact(exe_path=None)
go_cli.db_fix_studios(exe_path=None)
go_cli.actress_get(name, exe_path=None)
go_cli.actress_update(name, data, exe_path=None)
go_cli.actress_delete(name, exe_path=None)
go_cli.actress_list(exe_path=None)
go_cli.backup_create(exe_path=None)
go_cli.backup_restore(name, exe_path=None)
go_cli.backup_list(exe_path=None)
go_cli.backup_cleanup(exe_path=None)

# Cache 相關便捷函式
go_cli.cache_get(key, exe_path=None)
go_cli.cache_set(key, value, exe_path=None)
go_cli.cache_delete(key, exe_path=None)
go_cli.cache_stats(exe_path=None)
go_cli.cache_prune(ttl_days=None, exe_path=None)
go_cli.cache_clear(exe_path=None)
```

---

## _resolve_exe() 搜尋順序

當呼叫方未傳入 `exe_path` 時，`_resolve_exe()` 依下列順序尋找 `classifier` / `classifier.exe`：

1. **go_cli.py 所在位置往上 3 層**（尋找專案根目錄）
   - `src/services/go_cli.py` → 往上：`src/services/` → `src/` → 專案根目錄
   - 在每層目錄尋找 `classifier.exe`（Windows）或 `classifier`（Linux）
2. **當前工作目錄（CWD）**
3. **PATH 環境變數**中的 `classifier` 或 `classifier.exe`

> ⚠️ **不使用** `sys._MEIPASS`（PyInstaller 已移除）
> ⚠️ **不搜尋** `%PROGRAMFILES%` 或任何系統目錄

---

## 使用範例

```python
from services import go_cli

# 直接使用（自動搜尋 exe）
result = go_cli.run(["db", "get", "STARS-707"])
data = go_cli.run_json(["db", "get", "STARS-707"])

# 明確指定 exe 路徑
result = go_cli.run(["scan", "-dir", "D:/Videos"], exe_path="/path/to/classifier")

# 便捷函式
video = go_cli.db_get_video("STARS-707")
cached = go_cli.cache_get("search:STARS-707")

# 可用性確認
if not go_cli.is_available():
    raise RuntimeError("Go CLI 不可用，請確認 classifier.exe 存在")
```

---

## 錯誤類型

`go_cli.py` 定義語意化例外：

| 例外 | 觸發條件 |
|------|---------|
| `GoBridgeError` | 基底例外 |
| `ExecError` | subprocess 非零退出 |
| `NotFoundError` | 資源不存在（如查無番號） |
| `JSONError` | 輸出無法解析為 JSON |

---

## 相關頁面

- [go-cli.md](go-cli.md) — Go CLI 命令參考
- [overview.md](overview.md) — 系統架構總覽
- [pitfalls/go-api-export-missing.md](../pitfalls/go-api-export-missing.md)（歷史參考）
- [pitfalls/gui-bridge-wrong-access.md](../pitfalls/gui-bridge-wrong-access.md)（歷史參考）
