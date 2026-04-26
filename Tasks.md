# _apply_detail_panel_value 重構任務

## 目標

重構 `src/services/safe_javdb_searcher.py` 的 `SafeJAVDBSearcher._apply_detail_panel_value()`，降低條件分支複雜度，並補齊英文 label 與邊界契約測試。

本任務只允許結構重構與測試補強，不變更 JAVDB 解析的商業邏輯。

## Public Contract

- `SafeJAVDBSearcher._apply_detail_panel_value(info: dict[str, Any], label: str, value_element) -> None`
- 維持 `@staticmethod`，不新增 `self` 或 `cls` 參數。
- 永遠回傳 `None`。
- 僅原地修改傳入的 `info` dict。
- 不新增 logging、I/O、網路請求或全域狀態修改。
- 不主動捕捉例外；`value_element` 介面不合法時仍由上層既有流程處理。
- 未知 label 必須維持 no-op，不修改 `info`。

## 商業邏輯不變項

- `片商` / `Maker`：只使用 `value_element.select_one('a[href*="/makers/"]')`，找到才寫入 `info["studio"]`。
- `日期` / `Released Date`：使用 `value_element.text.strip()`，非空才寫入 `info["release_date"]`。
- `時長` / `Duration`：使用 `value_element.text.strip()`，非空才寫入 `info["duration"]`。
- `導演` / `Director`：使用 `value_element.select_one("a")`，找到才寫入 `info["director"]`。
- `系列` / `Series`：使用 `value_element.select_one("a")`，找到才寫入 `info["series"]`。
- `評分` / `Rating`：維持 regex `(\d+\.?\d*)`，命中才寫入 `float` 到 `info["rating"]`。
- `類別` / `Tags`：維持 `info["categories"] = [link.text.strip() for link in value_element.select("a")]`，即使結果是空清單也要覆寫。
- 不加入未驗證 label alias，例如 `Genre`。
- 不把 `Maker` 合併到 generic first-link helper。

## 實作策略

- 在 `SafeJAVDBSearcher` class body 加入 class-level label/field 常數：
  - `_DETAIL_MAKER_LABELS`
  - `_DETAIL_RATING_LABELS`
  - `_DETAIL_CATEGORY_LABELS`
  - `_DETAIL_TEXT_FIELDS`
  - `_DETAIL_LINK_FIELDS`
- `_apply_detail_panel_value()` 只做 dispatch：
  - maker labels -> `_apply_detail_maker()`
  - text field map -> `_apply_detail_text_field()`
  - link field map -> `_apply_detail_link_field()`
  - rating labels -> `_apply_detail_rating()`
  - category labels -> `_apply_detail_categories()`
- map lookup 使用 `is not None` 判斷是否命中，不依賴字串 truthiness。
- 新增 static helper：
  - `_apply_detail_maker`
  - `_apply_detail_text_field`
  - `_apply_detail_link_field`
  - `_apply_detail_rating`
  - `_apply_detail_categories`

## 測試清單

- 保留既有 7 支中文 label 測試。
- 新增 7 支英文 label smoke tests：
  - `Maker`
  - `Released Date`
  - `Duration`
  - `Director`
  - `Series`
  - `Rating`
  - `Tags`
- 新增 4 支契約保護測試：
  - unknown label no-op
  - Maker 非 `/makers/` link 不寫入 `studio`
  - Tags 空節點覆寫為 `[]`
  - Rating 無數字時維持 `None`

## 驗證命令

```powershell
python -m pytest tests/test_coverage_safe_javdb_searcher.py -q -p no:cacheprovider
python -m pytest tests/test_safe_javdb_searcher.py -q -p no:cacheprovider
```

## 執行狀態

- [x] 建立本任務文件
- [x] 重構 `_apply_detail_panel_value`
- [x] 補齊英文 label smoke tests
- [x] 補齊契約保護測試
- [x] 執行 pytest 驗證

## 驗證結果

```powershell
python -m pytest tests/test_coverage_safe_javdb_searcher.py -q -p no:cacheprovider
# 80 passed

python -m pytest tests/test_safe_javdb_searcher.py -q -p no:cacheprovider
# 8 passed

python -m pytest tests/ -q -p no:cacheprovider
# 1049 passed, 2 skipped, 1 warning

python -m pytest tests/test_safe_javdb_searcher.py tests/test_coverage_safe_javdb_searcher.py -q -p no:cacheprovider
# 89 passed

python -m pytest tests/ -q -p no:cacheprovider
# 1050 passed, 2 skipped, 2 warnings
```
