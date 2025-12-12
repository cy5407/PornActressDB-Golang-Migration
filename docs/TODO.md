# 女優分類系統 - 待修正問題清單

> 📅 建立日期：2025-12-11
> 📊 專案版本：v5.4.3
> 🎯 目標版本：v5.5.0

本文件記錄了程式碼審查後發現的待修正問題，按嚴重程度和優先順序排列。

---

## 📋 目錄

- [已完成的修正](#已完成的修正)
- [待修正問題](#待修正問題)
  - [高嚴重性問題](#高嚴重性問題)
  - [中嚴重性問題](#中嚴重性問題)
  - [低嚴重性問題](#低嚴重性問題)
- [修正進度追蹤](#修正進度追蹤)

---

## ✅ 已完成的修正

### 1. ~~移除廢棄的 database.py (SQLiteDBManager)~~
**狀態**: ✅ 已完成 (2025-12-11)

**修正內容**:
- 刪除 `src/models/database.py` (466 行廢棄程式碼)
- 確認無任何依賴該模組的程式碼

**效果**:
- 減少 466 行維護負擔
- 清理專案結構

---

### 2. ~~修正匯入語句重複問題~~
**狀態**: ✅ 已完成 (2025-12-11)

**修正檔案**:
- `src/services/classifier_core.py`: 移除重複的 `from pathlib import Path`
- `src/services/web_searcher.py`: 清理重複的 `japanese_config` 定義
- `src/models/json_types.py`: 統一 `datetime` 和 `timezone` 匯入

**效果**:
- 減少 ~20 行重複代碼
- 改善模組載入效能

---

## 🔴 待修正問題

### 高嚴重性問題

---

## 3. 改善 GUI 執行緒安全性 ⚡

**嚴重程度**: 🔴 高
**優先順序**: P1 (最高)
**預估工作量**: 4-6 小時

### 問題描述

在多執行緒環境下，GUI 元件的存在性檢查和實際操作之間存在競爭條件（Race Condition），可能導致應用程式崩潰。

### 影響範圍

**檔案位置**:
- `src/ui/main_gui.py`
  - 第 275 行：批次搜尋進度更新
  - 第 309 行：搜尋結果顯示
  - 第 314 行：錯誤訊息顯示
  - 第 411 行：狀態列更新

**問題程式碼範例**:
```python
# main_gui.py:278
if self.is_running and self.result_text.winfo_exists():
    self.result_text.insert(...)  # ⚠️ 檢查和操作之間可能發生競爭
```

### 影響

- **用戶體驗**: 大批量搜尋時 GUI 可能崩潰
- **穩定性**: tkinter 執行緒不安全操作導致不可預測的錯誤
- **觸發場景**:
  - 批次搜尋 100+ 個影片
  - 用戶在搜尋期間關閉視窗
  - 多個搜尋任務並行執行

### 修正方案

#### 方案 1: 增強 try-except 保護（快速修正）

```python
def safe_gui_update(self, callback):
    """安全的 GUI 更新包裝器"""
    def wrapped_callback():
        try:
            if self.is_running and hasattr(self, 'result_text'):
                if self.result_text.winfo_exists():
                    callback()
        except tk.TclError as e:
            logger.warning(f"⚠️ GUI 元件已銷毀: {e}")
        except Exception as e:
            logger.error(f"❌ GUI 更新失敗: {e}")

    self.root.after(0, wrapped_callback)
```

**修正步驟**:
1. 在 `main_gui.py` 中新增 `safe_gui_update()` 方法
2. 將所有 GUI 更新操作改用此方法包裝
3. 替換現有的 `self.root.after(0, ...)` 呼叫

**檔案修改**:
- [ ] `src/ui/main_gui.py` (新增 `safe_gui_update` 方法)
- [ ] `src/ui/main_gui.py` (修改約 15 處 GUI 更新點)

#### 方案 2: 使用 Queue 實現執行緒間通訊（徹底解決）

```python
import queue
from dataclasses import dataclass
from enum import Enum

class GUIMessageType(Enum):
    INFO = "info"
    ERROR = "error"
    PROGRESS = "progress"
    COMPLETE = "complete"

@dataclass
class GUIMessage:
    msg_type: GUIMessageType
    content: str
    data: dict = None

class UnifiedActressClassifierGUI:
    def __init__(self, root):
        self.gui_queue = queue.Queue()
        self._start_queue_processor()

    def _start_queue_processor(self):
        """定期處理 GUI 訊息佇列"""
        try:
            while True:
                msg = self.gui_queue.get_nowait()
                self._process_gui_message(msg)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self._start_queue_processor)  # 每 100ms 檢查一次

    def _process_gui_message(self, msg: GUIMessage):
        """處理單一 GUI 訊息"""
        try:
            if msg.msg_type == GUIMessageType.INFO:
                self.result_text.insert(tk.END, msg.content)
            elif msg.msg_type == GUIMessageType.ERROR:
                self.result_text.insert(tk.END, f"❌ {msg.content}\n", "error")
            # ... 其他訊息類型
        except Exception as e:
            logger.error(f"❌ 處理 GUI 訊息失敗: {e}")
```

**修正步驟**:
1. 新增 `GUIMessage` 和 `GUIMessageType` 資料結構
2. 在 `__init__` 中建立 `queue.Queue()`
3. 實作 `_start_queue_processor()` 和 `_process_gui_message()`
4. 修改所有背景執行緒改為發送訊息到 queue
5. 移除所有直接的 `self.root.after(0, ...)` 呼叫

**檔案修改**:
- [ ] `src/ui/main_gui.py` (新增 Queue 機制，約 100 行)
- [ ] `src/services/web_searcher.py` (修改 callback 使用方式)
- [ ] `src/services/classifier_core.py` (修改 progress_callback)

### 測試計畫

- [ ] 單元測試：測試 `safe_gui_update()` 在各種情況下的行為
- [ ] 壓力測試：批次搜尋 500 個影片，中途關閉視窗
- [ ] 並行測試：同時執行多個搜尋任務
- [ ] 回歸測試：確保現有功能正常運作

### 參考資料

- [Tkinter Threading Best Practices](https://docs.python.org/3/library/tkinter.html#thread-safety)
- [Python Queue Documentation](https://docs.python.org/3/library/queue.html)

---

## 4. 統一資料庫使用策略 💾

**嚴重程度**: 🔴 高
**優先順序**: P1 (最高)
**預估工作量**: 6-8 小時

### 問題描述

專案中同時存在兩個資料庫管理器（`JSONDBManager` 和 `IncrementalJSONDB`），造成使用不一致和潛在的資料同步問題。

### 影響範圍

**檔案位置**:
- `src/models/json_database.py` - JSONDBManager (標準版)
- `src/models/incremental_json_database.py` - IncrementalJSONDB (增量版)
- `src/services/classifier_core.py:38` - 使用 IncrementalJSONDB
- `tools/` 目錄下多個腳本 - 使用 JSONDBManager

**使用情況統計**:
```bash
IncrementalJSONDB 使用：
- src/services/classifier_core.py
- .claude/skills/actress-classifier/SKILL.md
- tests/test_incremental_db.py

JSONDBManager 使用：
- tools/verify/verify_fixes.py
- tools/studio_updates/*.py (4 個檔案)
- tools/diagnostics/*.py (2 個檔案)
- tests/test_json_statistics.py
```

### 問題分析

#### 1. 資料不一致風險

**場景**: 主程式使用 IncrementalJSONDB，工具腳本使用 JSONDBManager

```python
# 主程式 (classifier_core.py)
db = IncrementalJSONDB('data/json_db')
db.update_video('STARS-707', {'title': '新標題'})  # 寫入 journal

# 工具腳本 (tools/studio_updates/update_s1_studio.py)
db = JSONDBManager('data/json_db')
videos = db.get_all_videos()  # ⚠️ 讀取主檔案，journal 未合併！
```

**結果**: 工具腳本讀不到最新的資料

#### 2. Journal 合併時機不確定

IncrementalJSONDB 的合併條件：
- Journal 超過 1000 條記錄
- Journal 年齡超過 1 小時

如果用戶在合併前關閉程式，工具腳本會讀到過期資料。

### 修正方案

#### 方案 1: 全面採用 IncrementalJSONDB（推薦）

**優勢**:
- 統一 API，減少混淆
- 保留 40x 寫入加速優勢
- IncrementalJSONDB 已包含 JSONDBManager 的所有功能

**步驟**:

1. **修改所有工具腳本**

```python
# 修改前
from models.json_database import JSONDBManager
db = JSONDBManager('data/json_db')

# 修改後
from models.incremental_json_database import IncrementalJSONDB
db = IncrementalJSONDB('data/json_db')
db.compact_if_needed()  # 讀取前先合併 journal
```

2. **在 IncrementalJSONDB 中新增自動合併**

```python
class IncrementalJSONDB:
    def __init__(self, data_dir: str, auto_compact: bool = True):
        # ... 現有初始化代碼

        if auto_compact:
            # 啟動時自動合併（確保工具腳本讀到最新資料）
            self.compact_if_needed()
```

3. **新增相容性警告**

在 `json_database.py` 頂部新增：

```python
import warnings

warnings.warn(
    "JSONDBManager 已被 IncrementalJSONDB 取代，請更新程式碼。\n"
    "建議使用: from models.incremental_json_database import IncrementalJSONDB",
    DeprecationWarning,
    stacklevel=2
)
```

**修正檔案清單**:
- [ ] `tools/verify/verify_fixes.py`
- [ ] `tools/verify/verify_double_search_logic.py`
- [ ] `tools/studio_updates/update_s1_studio.py`
- [ ] `tools/studio_updates/update_moodyz_studio.py`
- [ ] `tools/studio_updates/update_mida101.py`
- [ ] `tools/studio_updates/update_faleno_studio.py`
- [ ] `tools/diagnostics/check_s1_actresses.py`
- [ ] `tools/diagnostics/check_faleno_studio.py`
- [ ] `tools/manual_tests/test_double_search.py`
- [ ] `tests/test_json_statistics.py`
- [ ] `src/models/json_database.py` (新增 DeprecationWarning)
- [ ] `src/models/incremental_json_database.py` (新增 auto_compact 參數)

#### 方案 2: 保留兩者，但強制同步

**適用場景**: 如果工具腳本需要純粹的 JSONDBManager 特性

**步驟**:

1. 在程式關閉時強制合併：

```python
# main_gui.py
def on_closing(self):
    """視窗關閉事件"""
    if self.is_running:
        if not messagebox.askokcancel("確認", "搜尋正在進行中，確定要關閉嗎？"):
            return
        self.stop_event.set()

    # ✅ 新增：強制合併 journal
    try:
        if hasattr(self.classifier, 'db_manager'):
            logger.info("🔄 關閉前合併資料庫...")
            self.classifier.db_manager.compact()
            logger.info("✅ 資料庫合併完成")
    except Exception as e:
        logger.error(f"❌ 資料庫合併失敗: {e}")

    self.root.destroy()
```

2. 工具腳本新增同步檢查：

```python
# tools/studio_updates/update_s1_studio.py
from pathlib import Path

def check_journal_sync(data_dir):
    """檢查 journal 是否需要合併"""
    journal_file = Path(data_dir) / "data.journal"
    if journal_file.exists() and journal_file.stat().st_size > 0:
        print("⚠️ 警告：發現未合併的 journal 檔案")
        print("建議執行: python -c 'from models.incremental_json_database import IncrementalJSONDB; db=IncrementalJSONDB(\"data/json_db\"); db.compact()'")
        response = input("是否自動合併? (y/n): ")
        if response.lower() == 'y':
            from models.incremental_json_database import IncrementalJSONDB
            db = IncrementalJSONDB(data_dir)
            db.compact()
            print("✅ Journal 已合併")

# 在主程式開頭呼叫
check_journal_sync('data/json_db')
```

### 測試計畫

- [ ] 測試 1: 主程式更新資料 → 工具腳本讀取 → 驗證資料一致性
- [ ] 測試 2: 大批量更新 (1000+ 條) → 自動觸發合併 → 驗證效能
- [ ] 測試 3: 程式異常關閉 → 重啟 → 驗證資料完整性
- [ ] 測試 4: 所有工具腳本逐一測試

### 決策建議

✅ **推薦方案 1**: 全面採用 IncrementalJSONDB
- 更簡潔的架構
- 統一的 API
- 更好的效能

---

## 5. 改善異常處理和日誌記錄 📝

**嚴重程度**: 🟡 中
**優先順序**: P2 (高)
**預估工作量**: 8-10 小時

### 問題描述

專案中存在 **22 處「空 pass」語句**，這些靜默的異常處理隱藏了潛在錯誤，增加除錯難度。

### 影響範圍

**統計**:
- `src/models/json_database.py`: 20 處
- `src/models/incremental_json_database.py`: 19 處
- `src/models/config.py`: 多處

**嚴重案例**:

```python
# json_database.py:218
if self.data_file.exists():
    try:
        self.data_file.unlink()
    except Exception:
        pass  # ❌ 靜默忽略，可能導致檔案鎖定問題未被發現
```

**在 OneDrive 環境下的風險**:
- OneDrive 同步可能鎖定檔案
- 檔案刪除失敗但被靜默忽略
- 導致資料殘留或同步衝突

### 修正方案

#### 階段 1: 添加日誌記錄（快速修正）

**修正前**:
```python
try:
    self.data_file.unlink()
except Exception:
    pass  # ❌ 無法追蹤錯誤
```

**修正後**:
```python
try:
    self.data_file.unlink()
except PermissionError as e:
    logger.warning(f"⚠️ 檔案刪除失敗（權限不足）: {self.data_file}, 錯誤: {e}")
except OSError as e:
    logger.warning(f"⚠️ 檔案刪除失敗（系統錯誤）: {self.data_file}, 錯誤: {e}")
except Exception as e:
    logger.error(f"❌ 未預期的錯誤: {e}", exc_info=True)
```

#### 階段 2: 使用具體異常類型

**現況**:
```python
# config.py:77
try:
    with open(self.preference_file, 'r', encoding='utf-8') as f:
        self.preferences = json.load(f)
except Exception as e:
    logger.warning(f"載入偏好設定失敗: {e}")
```

**改善後**:
```python
try:
    with open(self.preference_file, 'r', encoding='utf-8') as f:
        self.preferences = json.load(f)
except FileNotFoundError:
    logger.info(f"ℹ️ 偏好設定檔案不存在，使用預設值: {self.preference_file}")
    self.preferences = {}
except json.JSONDecodeError as e:
    logger.error(f"❌ 偏好設定 JSON 格式錯誤: {e}")
    self.preferences = {}
except PermissionError as e:
    logger.error(f"❌ 無權限讀取偏好設定: {e}")
    raise  # 權限問題應該向上傳播
except Exception as e:
    logger.error(f"❌ 載入偏好設定時發生未預期錯誤: {e}", exc_info=True)
    raise
```

#### 階段 3: 添加錯誤恢復機制

**資料庫操作範例**:
```python
def _save_all_data(self, data: JSONDatabaseDict, max_retries: int = 3):
    """儲存資料到檔案（帶重試機制）"""
    for attempt in range(1, max_retries + 1):
        try:
            # 1. 寫入臨時檔案
            temp_file = self.data_file.with_suffix('.tmp')
            with open(temp_file, 'wb') as f:
                f.write(orjson.dumps(data, option=orjson.OPT_INDENT_2))

            # 2. 原子性替換
            temp_file.replace(self.data_file)
            logger.info(f"✅ 資料儲存成功")
            return

        except PermissionError as e:
            if attempt < max_retries:
                logger.warning(f"⚠️ 第 {attempt} 次儲存失敗（權限不足），{2**attempt} 秒後重試...")
                time.sleep(2 ** attempt)  # 指數退避
            else:
                logger.error(f"❌ 儲存失敗（已重試 {max_retries} 次）: {e}")
                raise

        except Exception as e:
            logger.error(f"❌ 儲存時發生未預期錯誤: {e}", exc_info=True)
            raise
```

### 修正檔案清單

#### 高優先級（影響核心功能）
- [ ] `src/models/json_database.py` (20 處空 pass)
  - `_save_all_data()` - 資料儲存失敗處理
  - `_load_data()` - 資料載入失敗處理
  - `backup_database()` - 備份失敗處理

- [ ] `src/models/incremental_json_database.py` (19 處)
  - `_append_journal()` - Journal 寫入失敗
  - `compact()` - 合併失敗處理
  - `_replay_journal()` - Journal 重播錯誤

- [ ] `src/models/config.py`
  - `load_config()` - 設定檔載入
  - `save_preferences()` - 偏好設定儲存

#### 中優先級（影響使用者體驗）
- [ ] `src/ui/main_gui.py`
  - GUI 更新錯誤處理
  - 檔案對話框異常處理

- [ ] `src/services/web_searcher.py`
  - 網路請求錯誤處理
  - 快取存取錯誤處理

#### 低優先級（工具腳本）
- [ ] `tools/` 目錄下所有腳本

### 異常處理最佳實踐

#### 1. 異常類型優先順序

```python
try:
    # 操作
    pass
except SpecificError1:  # 最具體的錯誤
    # 處理
except SpecificError2:  # 次具體
    # 處理
except Exception as e:  # 最後才用通用捕捉
    logger.error(f"未預期錯誤: {e}", exc_info=True)
    raise  # 重新拋出，除非有明確理由吞掉
```

#### 2. 日誌級別使用

- `logger.debug()`: 除錯資訊（正常流程）
- `logger.info()`: 重要操作（啟動、完成）
- `logger.warning()`: 可恢復的錯誤（重試成功、使用預設值）
- `logger.error()`: 嚴重錯誤但程式可繼續
- `logger.critical()`: 致命錯誤，程式無法繼續

#### 3. 異常資訊記錄

```python
# ✅ 好的做法
try:
    result = process_data(file_path)
except ValueError as e:
    logger.error(
        f"❌ 資料處理失敗\n"
        f"   檔案: {file_path}\n"
        f"   錯誤: {e}\n"
        f"   行號: {e.__traceback__.tb_lineno}",
        exc_info=True  # 包含完整堆疊追蹤
    )

# ❌ 不好的做法
except Exception:
    pass  # 無法追蹤
```

### 測試計畫

- [ ] 單元測試：針對每種異常情況寫測試
- [ ] 錯誤注入：模擬檔案鎖定、權限不足、磁碟滿等情況
- [ ] 日誌檢查：確保所有錯誤都有適當日誌
- [ ] OneDrive 測試：在同步環境下測試檔案操作

---

## 🟢 中等嚴重性問題

### 6. ~~config.ini 配置管理不一致~~

**狀態**: ✅ 已完成 (2025-12-13)
**預估工作量**: 2-3 小時

**修正內容**:
- 新增 `normalize_path()` 函式，統一使用 POSIX 風格路徑 (/)
- 新增 `VALIDATION_RULES` 驗證規則字典，支援類型、範圍驗證
- 新增 `_normalize_path_settings()` 方法，自動標準化路徑設定
- 新增 `_validate_config()` 方法，驗證配置值有效性
- 新增 `getpath()`, `set()`, `get_all_settings()` 方法
- 新增 `cache` section 預設配置

**修正檔案**:
- `src/models/config.py`

---

### 7. 重複的 sys.path 操作

**狀態**: 📝 待修正（較低優先級）
**預估工作量**: 1-2 小時

**問題**: 多個模組重複執行 `sys.path.insert(0, ...)`

**備註**: 工具腳本需要保持獨立運行能力，這是 Python 專案的常見模式。
此問題優先級較低，不影響功能。

---

### 8. ~~快取機制未整合~~

**狀態**: ✅ 已完成 (2025-12-13)
**預估工作量**: 4-5 小時

**修正內容**:
- 建立 `UnifiedCacheManager` 類別，整合 3 個獨立快取系統
- 實現統一的快取介面：`get()`, `set()`, `delete()`
- 實現 `cleanup_all()` 方法，支援 TTL 和大小限制
- 實現 `get_stats()` 方法，提供快取統計
- 提供 `get_cache_manager()` 單例函式
- 整合到 `WebSearcher` 和 `main_gui.py`

**修正檔案**:
- `src/services/unified_cache.py` (新建)
- `src/services/web_searcher.py`
- `src/ui/main_gui.py`

---

## 🟡 低嚴重性問題

### 9. 未使用的變數和函式

**狀態**: 📝 待修正
**預估工作量**: 1-2 小時

**修正步驟**:
1. 使用 `pylint` 或 `flake8` 掃描
2. 刪除或實現 TODO 標記的程式碼

---

### 10. 代碼風格不一致

**狀態**: 📝 待修正
**預估工作量**: 1 小時

**修正步驟**:
1. 使用 `black` 自動格式化
2. 配置 `.editorconfig`
3. 添加 pre-commit hook

---

## 📊 修正進度追蹤

### 總體進度

| 類別 | 總數 | 已完成 | 進行中 | 待處理 |
|------|------|--------|--------|--------|
| 🔴 高嚴重性 | 5 | 5 | 0 | 0 |
| 🟢 中嚴重性 | 3 | 2 | 0 | 1 |
| 🟡 低嚴重性 | 2 | 0 | 0 | 2 |
| **總計** | **10** | **7** | **0** | **3** |

### 時程規劃

#### 第一週（已完成）
- [x] 問題 1: 移除廢棄的 database.py
- [x] 問題 2: 修正匯入重複

#### 第二週（已完成）
- [x] 問題 3: 改善 GUI 執行緒安全性（4-6 小時）
- [x] 問題 4: 統一資料庫使用策略（6-8 小時）
- [x] 問題 5: 改善異常處理（部分完成 - 空 pass 改進）
- [x] 問題 6: config.ini 配置管理
- [x] 問題 8: 快取機制整合

#### 待處理
- [ ] 問題 7: 重複的 sys.path 操作（較低優先級）
- [ ] 問題 9: 未使用的變數和函式
- [ ] 問題 10: 代碼風格不一致

#### 第四週（建議）
- [ ] 問題 6-10: 中低優先級問題（8-10 小時）

---

## 🎯 建議修正順序

### 快速勝利（Quick Wins）
1. ✅ 問題 1: 移除廢棄檔案（已完成）
2. ✅ 問題 2: 修正匯入重複（已完成）
3. 問題 10: 代碼格式化（1 小時）
4. 問題 9: 清理未使用程式碼（2 小時）

### 關鍵修正（Critical Fixes）
5. 問題 3: GUI 執行緒安全性（影響穩定性）
6. 問題 4: 統一資料庫策略（影響資料一致性）
7. 問題 5: 改善異常處理（影響可維護性）

### 優化改善（Improvements）
8. 問題 6: 配置管理
9. 問題 7: sys.path 優化
10. 問題 8: 快取整合

---

## 📚 參考資源

### Python 最佳實踐
- [PEP 8 -- Style Guide for Python Code](https://peps.python.org/pep-0008/)
- [Python Threading Best Practices](https://docs.python.org/3/library/threading.html)
- [Effective Python (2nd Edition)](https://effectivepython.com/)

### Tkinter 執行緒安全
- [Tkinter Thread Safety](https://docs.python.org/3/library/tkinter.html#thread-safety)
- [Threading with Tkinter](https://www.pythontutorial.net/tkinter/tkinter-thread/)

### 異常處理
- [Python Exception Handling](https://docs.python.org/3/tutorial/errors.html)
- [Best Practices for Exception Handling](https://realpython.com/python-exceptions/)

---

## 🤝 貢獻指南

如果您要協助修正這些問題：

1. **選擇任務**: 從上方清單選擇一個待處理項目
2. **建立分支**: `git checkout -b fix/issue-{number}-{brief-description}`
3. **執行修正**: 按照文件中的步驟進行
4. **測試**: 執行相關測試確保功能正常
5. **提交**:
   ```bash
   git add .
   git commit -m "fix: 修正問題 #{number} - {簡短描述}

   - 修正內容 1
   - 修正內容 2

   相關 Issue: #{number}"
   ```
6. **更新此文件**: 將對應項目標記為已完成

---

**最後更新**: 2025-12-11
**維護者**: Claude Code
**專案**: 女優分類系統 (PornActressDB-Golang-Migration)
