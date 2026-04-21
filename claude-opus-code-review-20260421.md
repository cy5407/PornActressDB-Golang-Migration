# Claude Opus 程式碼審查報告
**日期**：2026-04-21  
**審查範圍**：死碼清除清單驗證  
**審查模型**：Claude Opus 4.7  
**分支**：`refactor/sonar-cognitive-complexity`

---

## 審查背景

針對提交的死碼清除清單進行逐項驗證，確認各項目是否確實未被引用，避免誤刪影響系統運作。

---

## 逐項驗證結果

### 1. 無用 import（5 處）

#### 1-1. `src/models/config.py` — `json_dump`, `json_load`

```python
# 第 12-16 行
try:
    from utils.json_utils import dump as json_dump
    from utils.json_utils import load as json_load
except ImportError:
    from src.utils.json_utils import dump as json_dump
    from src.utils.json_utils import load as json_load
```

**結論：✅ 可安全刪除**  
全檔案搜尋確認 `json_dump` 與 `json_load` 在 import 以外無任何使用點。`ConfigManager` 使用的是 `configparser`，與 json_utils 完全無關。

---

#### 1-2. `src/utils/progress_tracker.py:6-7` — `builtins`, `contextlib`

```python
import builtins
import contextlib
```

**結論：✅ 可安全刪除**  
全檔搜尋確認兩者在 import 行以外無任何使用。模組主要依賴 `threading`、`time`、`dataclasses`，與 `builtins`/`contextlib` 無關聯。

---

#### 1-3. `src/scrapers/async_scraper.py:19` — `RateLimiter`

```python
from .rate_limiter import RateLimiter, get_global_rate_limiter
```

**結論：✅ 可安全刪除 `RateLimiter`，保留 `get_global_rate_limiter`**  
全檔搜尋確認 `RateLimiter` 類別在 import 行以外無任何使用。`get_global_rate_limiter` 則確實在爬蟲邏輯中被調用，必須保留。  
修改後應改為：
```python
from .rate_limiter import get_global_rate_limiter
```

---

### 2. 未使用常數（`src/models/json_types.py`）

#### 2-1. `ISO_DATE_FORMAT`

```python
ISO_DATE_FORMAT = "%Y-%m-%d"
```

**結論：✅ 可安全刪除**  
全專案搜尋（包含所有 `.py` 檔）確認此常數只出現在定義處。  
注意：同檔的 `ISO_DATETIME_FORMAT` **有被使用**（`get_empty_json_database()`、`get_empty_video()` 等），不可誤刪。

---

#### 2-2. `DATA_DIR`, `JSON_DB_FILE`, `BACKUP_DIR`

```python
DATA_DIR = "data/json_db"
JSON_DB_FILE = "data/json_db/data.json"
BACKUP_DIR = "data/json_db/backup"
```

**結論：✅ 可安全刪除**  
全專案搜尋確認這三個常數無任何外部引用。  
`go_cli.py` 雖有 `_DEFAULT_DATA_DIR = "data/json_db"` 字面值相同，但為各自獨立定義，互不 import，兩者完全解耦。

---

#### 2-3. `VIDEO_ALLOWED_FIELDS`

```python
VIDEO_ALLOWED_FIELDS = {
    "code", "title", "studio", "release_date", "url",
    "actresses", "search_status", "search_method", ...
}
```

**結論：❌ 清單錯誤，不可刪除**  
此常數仍被兩個工具腳本引用：

| 檔案 | 行號 | 用途 |
|------|------|------|
| `tools/diagnostics/normalize_json_db_schema.py` | 27, 147 | 驗證影片欄位是否在允許集合中 |
| `tools/verify/verify_json_db_schema.py` | 18, 80 | 同上，用於 schema 驗證 |

刪除後這兩個驗證工具會立即 `ImportError` 失敗。  
**應從刪除清單中移除。**

---

#### 2-4. `ROLE_TYPES`

```python
ROLE_TYPES = {
    "MAIN": "主演",
    "SUPPORTING": "配角",
    "GUEST": "客串",
}
```

**結論：✅ 可安全刪除**  
全專案搜尋確認只出現在定義處。`VideoActressLinkDict` 的 `role_type` 欄位雖有角色值的字串說明（`"主演" | "配角" | "客串"`），但僅為型別說明字串，並非引用此常數。

---

#### 2-5. `MAX_STRING_LENGTH`, `MAX_ACTRESSES_PER_VIDEO`, `MAX_ALIASES_PER_ACTRESS`

```python
MAX_STRING_LENGTH = 2000
MAX_ACTRESSES_PER_VIDEO = 20
MAX_ALIASES_PER_ACTRESS = 10
```

**結論：✅ 可安全刪除**  
全專案搜尋（含所有目錄、子目錄）確認三者均只出現在 `json_types.py` 定義處，無任何驗證邏輯引用。原規劃的驗證功能顯然未實作。

---

### 3. 重複實作：`_secure_uniform`（三份複製）

三個模組各自定義了完全相同的函式：

```python
# src/scrapers/rate_limiter.py:18
# src/scrapers/base_scraper.py:23
# src/utils/retry_utils.py:13
def _secure_uniform(min_value: float, max_value: float) -> float:
    ...
```

**結論：⚠️ 可合併，但需連帶調整測試**

**`src/utils/retry_utils.py`** 為建議保留的來源（工具層，最底層無相依）。

| 模組 | 處理方式 | 說明 |
|------|----------|------|
| `src/scrapers/base_scraper.py` | 改為 import | 無測試直接引用其 `_secure_uniform`，可直接刪除定義、改 import |
| `src/scrapers/rate_limiter.py` | 需注意 | `tests/test_coverage_rate_limiter.py:18` 直接 `from src.scrapers.rate_limiter import _secure_uniform`，若直接刪除定義會導致測試 ImportError |

**兩種處理選項**：

**選項 A（改測試）**：刪除 `rate_limiter.py` 的定義，把測試的 import 改為：
```python
from src.utils.retry_utils import _secure_uniform
```
語義更正確，但需修改測試。

**選項 B（re-export）**：在 `rate_limiter.py` 改為：
```python
from src.utils.retry_utils import _secure_uniform  # re-export
```
測試不需動，但 `rate_limiter.py` 仍有一行 import（非完全消除）。

---

## 整體結論

| 項目 | 可刪除？ | 備註 |
|------|----------|------|
| config.py `json_dump`/`json_load` | ✅ 是 | 全檔無使用 |
| progress_tracker.py `builtins`/`contextlib` | ✅ 是 | 全檔無使用 |
| async_scraper.py `RateLimiter` | ✅ 是 | 保留 `get_global_rate_limiter` |
| json_types.py `ISO_DATE_FORMAT` | ✅ 是 | 注意勿誤刪 `ISO_DATETIME_FORMAT` |
| json_types.py `DATA_DIR`/`JSON_DB_FILE`/`BACKUP_DIR` | ✅ 是 | 與 go_cli.py 互不相依 |
| json_types.py `VIDEO_ALLOWED_FIELDS` | ❌ **否** | tools/ 兩個腳本仍在使用 |
| json_types.py `ROLE_TYPES` | ✅ 是 | 全專案無引用 |
| json_types.py `MAX_STRING_LENGTH` 等 3 個 | ✅ 是 | 全專案無引用 |
| `_secure_uniform` 三份複製 | ✅ 可合併 | 需決定測試調整策略（選項 A/B） |

**安全可執行（零風險）**：前 8 項（排除 `VIDEO_ALLOWED_FIELDS`）  
**需額外決策**：`_secure_uniform` 合併策略

---

---

## 補充驗證（2026-04-21 二次核查）

初次審查時 `progress_tracker.py`（254 行）與 `async_scraper.py`（462 行）僅讀取前 30/40 行，存在殘餘盲點。補充全檔 grep 驗證如下：

| 項目 | 補充驗證結果 |
|------|-------------|
| `progress_tracker.py` 全檔搜尋 `builtins`/`contextlib` | 僅出現在第 6-7 行 import，全檔無任何使用，結論不變 ✅ |
| `async_scraper.py` 全檔搜尋 `RateLimiter` | 僅出現在第 19 行 import，全檔無任何使用，結論不變 ✅ |
| 全專案搜尋萬用字元 `from ... json_types import *` | 無任何萬用字元 import，常數清單的搜尋結果可信 ✅ |
| `config.py` 的 `json_dump`/`json_load` 跨檔比對 | 其他檔案（`safe_searcher.py`、`studio.py`、`cache_manager.py` 等）雖也使用相同別名，但為各自獨立 import，與 `config.py` 是否刪除無關 ✅ |

**二次核查後所有原始結論維持不變。**

---

*審查完成。所有結論均基於全專案 `.py` 檔的靜態搜尋驗證，非推測。*
