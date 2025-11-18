# 🔄 零女優番號二次搜尋功能實現文件

## 概述

此功能實現了一套完整的「二次搜尋機制」，用於處理 JAVDB 搜尋無法找到女優資訊的番號（如 SNIS-539）。

## 問題背景

- **SNIS-539** 等某些番號在 AV-WIKI 和初次 JAVDB 搜尋中無法找到女優資訊
- 用戶需要一個自動機制來重新搜尋這些「零女優」番號
- 需要清除快取並從不同路徑重新搜尋

## 實現方案

### 1. 快取清除機制
**位置**: `src/services/safe_javdb_searcher.py`

新增方法 `clear_cache_for_code(video_id: str) -> bool`:
```python
def clear_cache_for_code(self, video_id: str) -> bool:
    """清除特定番號的快取 - 用於二次搜尋"""
    cache_key = f"javdb_{video_id.upper()}"
    if cache_key in self.cache:
        del self.cache[cache_key]
        self.save_cache()
        logger.info(f"🧹 已清除 {video_id} 的 JAVDB 快取")
        return True
    return False
```

### 2. 改進的搜尋邏輯
**位置**: `src/services/classifier_core.py` - `process_and_search_javdb()` 方法

#### 偵測零女優番號
```python
# 新增判斷邏輯
if not actresses or len(actresses) == 0:
    # 特別處理零女優番號
    if code not in zero_actress_code_map:
        zero_actress_code_map[code] = []
    zero_actress_code_map[code].append(file_path)
    should_research = False  # 在第二輪單獨處理
```

#### 第一輪搜尋
- 搜尋所有需要的番號（新番號 + 無結果番號 + 零女優番號）
- 將結果分類為「成功」和「仍無結果」

#### 第二輪搜尋（新增）
```python
# 如果是零女優番號，標記為需要二次搜尋
if code in zero_actress_code_map:
    if progress_callback:
        progress_callback(f"⚠️ {code}: 仍無女優資訊，標記為二次搜尋\n")
    second_round_codes[code] = all_codes_to_search[code]
```

流程：
1. 清除零女優番號的 JAVDB 快取
2. 重新調用 `batch_search()` 進行搜尋
3. 根據結果更新資料庫

### 3. 進度提示改進
**輸出信息示例**:
```
📊 開始掃描資料夾 (JAVDB 搜尋模式)...
📁 發現 X 個影片檔案。
✅ 資料庫中已存在 X 個影片的番號記錄。
🎯 需要搜尋 X 個新番號。
🔄 需要重新搜尋 X 個之前無結果的番號。
⚠️ 發現 X 個零女優番號，將進行重新搜尋。

🔍 開始第一輪搜尋 (X 個番號)...
[第一輪結果...]

🔄 開始第二輪搜尋（清除快取，重新查詢 X 個零女優番號）...
🧹 已清除 SNIS-539 的快取
[第二輪結果...]
```

## 返回值改進

舊返回值:
```python
{
    'status': 'success',
    'total_files': 100,
    'new_codes': 50,
    'research_codes': 10,
    'success': 40,
    'failed': 20
}
```

新返回值:
```python
{
    'status': 'success',
    'total_files': 100,
    'new_codes': 50,
    'research_codes': 10,
    'zero_actress_codes': 5,          # 新增：零女優番號數
    'first_round_success': 40,        # 新增：第一輪成功數
    'first_round_failed': 20,         # 新增：第一輪失敗數
    'second_round_success': 3         # 新增：第二輪成功數
}
```

## 使用流程

### 通過 GUI 運行
1. 點擊「📊 JAVDB 搜尋」按鈕
2. 選擇包含影片檔案的資料夾
3. 系統自動：
   - 🔍 第一輪搜尋所有需要的番號
   - ⚠️ 偵測零女優番號
   - 🧹 清除快取
   - 🔄 第二輪搜尋零女優番號
   - ✏️ 複寫資料庫

### 通過代碼運行
```python
from src.services.classifier_core import UnifiedClassifierCore
from src.models.config import ConfigManager

config = ConfigManager()
core = UnifiedClassifierCore(config)

result = core.process_and_search_javdb(
    folder_path='/path/to/videos',
    stop_event=threading.Event(),
    progress_callback=lambda msg: print(msg)
)
```

## 關鍵特性

✅ **自動偵測**: 自動識別零女優番號，無需手動干預
✅ **快取管理**: 在二次搜尋前清除快取，確保獲得最新結果
✅ **進度追蹤**: 詳細的搜尋進度提示，包括所有階段
✅ **資料庫複寫**: 找到女優後自動更新記錄，search_status 標記為 'searched_found'
✅ **錯誤處理**: 二次搜尋仍無結果時正確標記為 'searched_not_found'
✅ **方法標記**: search_method 中標註是否為二次搜尋

## 測試案例

### SNIS-539
- 初始狀態: 0 位女優
- 第一輪結果: 仍為 0 位女優
- 第二輪結果: 依然 0 位（確實無結果頁面）
- 最終狀態: 保持 0 位，但 search_method = 'JAVDB (二次搜尋)'

### 其他零女優番號
- 系統會依次進行相同的二次搜尋流程
- 如果第二輪找到女優，更新為有女優狀態

## 限制與考慮

⚠️ **快取延遲**: JAVDB 可能有快取層，二次搜尋結果可能與第一輪相同
⚠️ **速率限制**: 連續搜尋相同番號可能觸發速率限制，建議間隔充足
⚠️ **網頁變化**: 如果目標網頁結構改變，搜尋方法需要相應調整

## 後續優化方向

1. **智能備選搜尋**: 如果 JAVDB 無結果，自動轉向 AV-WIKI 等其他源
2. **搜尋延遲**: 在二次搜尋前增加更長延遲，避免速率限制
3. **結果驗證**: 二次搜尋結果與第一輪對比，標記為「新發現」
4. **統計分析**: 記錄哪些番號經常需要二次搜尋，用於改進搜尋算法
