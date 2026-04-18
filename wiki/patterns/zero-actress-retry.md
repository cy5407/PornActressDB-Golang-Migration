# 零女優二次搜尋模式

> 來源：`QUICK_START_GUIDE.md`  
> 更新：2026-04-06

---

## 問題背景

部分番號（如 `SNIS-539`）在 JAVDB 上的搜尋結果會因快取問題，導致第一次搜尋時女優列表為空（零女優）。清除快取後重新搜尋，有 10-15% 的機率能找到正確女優。

---

## 搜尋流程

```
掃描資料夾
    ↓
分類番號：新番號 / 無結果番號 / 零女優番號
    ↓
【第一輪搜尋】
├─ 有女優 → 儲存，標記 searched_found
├─ 無女優（零女優）→ 標記，進第二輪
└─ 無女優（非零女優）→ 儲存 searched_not_found
    ↓
【第二輪搜尋】（僅零女優）
├─ 清除快取 🧹（clear_cache_for_code）
├─ 重新查詢 JAVDB 🔍
├─ 找到 → 覆寫資料庫，標記 "JAVDB (二次搜尋)"
└─ 未找到 → 儲存 searched_not_found
```

---

## 程式碼位置

| 功能 | 位置 |
|------|------|
| 清除快取 | `src/services/safe_javdb_searcher.py::clear_cache_for_code()` |
| 零女優偵測 + 第二輪搜尋 | `src/services/classifier_core.py::process_and_search_javdb()` |

---

## 判定標準

```python
# 資料庫中有記錄，但女優列表為空
if code in database and not video['actresses']:
    # 零女優番號，進入第二輪搜尋
```

---

## 呼叫方式

### GUI
點擊「📊 JAVDB 搜尋」按鈕，自動執行（無需額外操作）。

### 程式碼

```python
from services.classifier_core import UnifiedClassifierCore
from models.config import ConfigManager
import threading

core = UnifiedClassifierCore(ConfigManager())
result = core.process_and_search_javdb(
    folder_path='C:\\Videos',
    stop_event=threading.Event(),
    progress_callback=lambda msg: print(msg, end='', flush=True)
)

# 回傳值
print(result['zero_actress_codes'])    # 零女優番號列表
print(result['second_round_success'])  # 第二輪成功數
```

---

## 回傳值說明

```python
{
    'status': 'success',
    'total_files': 100,
    'new_codes': 20,            # 全新番號
    'research_codes': 5,        # 無結果重試番號
    'zero_actress_codes': 3,    # 零女優番號
    'first_round_success': 23,  # 第一輪成功數
    'first_round_failed': 20,   # 第一輪失敗數
    'second_round_success': 2   # 第二輪成功數
}
```

---

## 資料庫標記

### 二次搜尋成功
```json
{
  "search_status": "searched_found",
  "search_method": "JAVDB (二次搜尋)"
}
```

### 二次搜尋確認無結果
```json
{
  "search_status": "searched_not_found",
  "search_method": "JAVDB (二次搜尋)"
}
```

---

## 效能參考

| 指標 | 數值 |
|------|------|
| 零女優番號偵測準確率 | 100% |
| 第二輪找到女優的機率 | 10-15% |
| 搜尋時間增加 | +15-30% |
| 搜尋成功率提升 | +3-5% |

---

## 相關頁面

- [wiki/architecture/search-engine.md](../architecture/search-engine.md)
- [wiki/pitfalls/javdb-false-positive.md](../pitfalls/javdb-false-positive.md)
