# Python→Go 委派層：go_cli.py

> 來源：`src/services/go_cli.py`、`src/models/json_database.py`、`src/models/incremental_json_database.py`、`src/utils/scanner.py`
> 更新：2026-04-27（校正現行函式名稱、例外類別與 `_resolve_exe()` 搜尋順序）

---

## 概述

**目前唯一的 Python→Go 委派入口**：`src/services/go_cli.py`

它不是舊版 GoBridge facade，也沒有 `run_json()` 這類額外包裝；現行 `run()` 會直接執行 `classifier(.exe)` 並解析 JSON stdout。

舊架構的橋接層已於 W6（2026-04-07）移除：

| 已移除 | 說明 |
|--------|------|
| `src/services/go_bridge.py` | 舊 GoBridge facade |
| `src/services/go_runner.py` | 舊 subprocess 執行器 |
| `src/services/go_api/` | 舊領域 API 層 |
| `src/ui/` | 舊 Python Tkinter GUI |

---

## 架構設計：模組級函式

`go_cli.py` 以模組級函式提供薄委派，不再新增 class wrapper。

```python
from src.services import go_cli

# 核心執行
go_cli.is_available(exe_path=None)
go_cli.run(["db", "get", "STARS-707"], timeout=30, exe_path=None)

# 掃描 / 番號 / 片商
go_cli.extract_code("STARS-707.mp4")
go_cli.identify_studio("STARS-707")
go_cli.normalize_studio_name("S1", video_code="STARS-707")

# DB
go_cli.db_get_video("STARS-707")
go_cli.db_update_video("STARS-707", data)
go_cli.db_delete_video("STARS-707")
go_cli.db_get_all_videos()
go_cli.db_compact_journal()

# DB backup
go_cli.db_backup_create()
go_cli.db_backup_list()
go_cli.db_backup_restore("data/json_db/backup/backup_YYYY-MM-DD_HH-MM-SS.json")
go_cli.db_backup_cleanup(days=30, max_count=50)

# Actress CRUD
go_cli.db_get_actress("Julia")
go_cli.db_update_actress("Julia", data)
go_cli.db_delete_actress("Julia")

# Cache
go_cli.cache_get("key")
go_cli.cache_set("key", b"value")
go_cli.cache_delete("key")
go_cli.cache_get_stats()
go_cli.cache_prune()
go_cli.cache_clear()

# Move / history
go_cli.move_file(src, dst)
go_cli.move_dir(src, dst)
go_cli.batch_move(items)
go_cli.rollback(operation_id)
go_cli.rollback_last()
go_cli.list_operations()
```

---

## `_resolve_exe()` 搜尋順序

當呼叫方未傳入 `exe_path` 時，`_resolve_exe()` 依序尋找 `classifier` / `classifier.exe`：

1. `CLASSIFIER_EXE` 環境變數
2. `src/services/go_cli.py` 往上三層得到的專案根目錄
3. 目前工作目錄（CWD）
4. PATH 環境變數

補充：

- Windows 優先找 `classifier.exe`。
- Linux / macOS / WSL 優先找 `classifier`，再找 `classifier.exe`。
- WSL 呼叫 Windows `.exe` 時，部分臨時 JSON 路徑會透過 `wslpath` 轉換。
- 不使用 `sys._MEIPASS`；PyInstaller 不是現行正式 GUI 發行路徑。

---

## 使用範例

```python
from src.services import go_cli

if not go_cli.is_available():
    raise RuntimeError("Go CLI 不可用，請確認 classifier(.exe) 存在")

video = go_cli.db_get_video("STARS-707")
if video is None:
    print("查無資料")

go_cli.db_update_video("STARS-707", {"title": "新標題"})
go_cli.db_compact_journal()
```

呼叫端若需要自訂執行檔位置，應明確傳 `exe_path`，例如 `src/utils/scanner.py` 的 `go_exe_path`。

---

## 錯誤類型

`go_cli.py` 現行定義兩個例外類別：

| 例外 | 觸發條件 |
|------|----------|
| `GoError` | CLI 非零退出、逾時、JSON 解析失敗等一般錯誤 |
| `GoNotFoundError` | 找不到 `classifier(.exe)` |

部分便捷函式會把「查無資料」轉成 `None` 或 `False`，但非爬蟲層不應把 Go 不可用包裝成假成功。

---

## 目前主要呼叫端

| 呼叫端 | 用途 |
|--------|------|
| `src/models/json_database.py` | JSON DB CRUD、backup、actress CRUD 委派 |
| `src/models/incremental_json_database.py` | 影片更新 / 刪除 / compact 委派 |
| `src/scrapers/cache_manager.py` | 快取維護委派 |
| `src/utils/scanner.py` | 掃描薄適配層 |

---

## 相關頁面

- [go-cli.md](go-cli.md) — Go CLI 命令參考
- [overview.md](overview.md) — 系統架構總覽
- [patterns/remove-python-fallback.md](../patterns/remove-python-fallback.md) — Python fallback 移除原則
