# Feature Specification: SQLite 轉換為 JSON 資料庫儲存

**Feature Branch**: `feature/sqlite-to-json-migration`  
**Created**: 2025-10-16  
**Status**: Assessment & Planning  
**Input**: User description: "評估從 SQLite 轉換為 JSON 儲存的工作量和風險"

---

## 🎯 Executive Summary

本規格文件詳細評估**將現有 SQLite 資料庫系統轉換為 JSON 檔案儲存**的工作量、複雜度和實施策略。

### 核心發現
- **影響範圍**: 15+ 個 Python 檔案需要修改
- **預計工時**: **40-60 小時** (含測試和驗證)
- **複雜度**: **高** (因架構級別的改動)
- **關鍵風險**: 資料完整性、並行存取、性能
- **轉換方式**: 建議**雙層並行** (SQLite + JSON) 而非直接替換

---

## 📊 詳細工作量分析

### 1. **資料層改造** (15-20 小時) ⚠️ 關鍵路徑

#### 1.1 建立 JSON 資料庫管理器 (8-10 小時)
**檔案**: `src/models/database.py` → 新增 `JSONDBManager` 類別

**任務清單**:
```python
# 需要實現的核心方法
class JSONDBManager:
    def __init__(self, data_dir: str)           # 初始化，建立目錄結構
    def _load_all_data()                        # 從 JSON 檔案載入全部資料
    def _save_all_data()                        # 原子性寫入全部資料
    def _ensure_data_file_exists()              # 檔案存在性檢查
    def add_or_update_video()                   # 新增/更新影片（需併發鎖）
    def get_video_info()                        # 查詢影片
    def get_all_videos()                        # 取得全部影片
    def get_actress_statistics()                # 女優統計（JOIN 邏輯重寫）
    def get_studio_statistics()                 # 片商統計（JOIN 邏輯重寫）
    def get_enhanced_actress_studio_statistics()# 增強版統計
    def delete_video()                          # 刪除影片（新增）
    def create_backup()                         # 備份機制（新增）
```

**複雜性分析**:
- ✅ **新增複雜度**: 須實現 JOIN 查詢邏輯 (SQLite 原生支持，JSON 需手動)
- ✅ **並發處理**: 須加入讀寫鎖 (threading.Lock / filelock)
- ✅ **性能**: 全量載入→修改→全量寫入 (需優化策略)
- ⚠️ **資料一致性**: 需幕等性設計 (操作失敗時的恢復)

#### 1.2 資料遷移工具 (5-7 小時)
**檔案**: 新增 `scripts/migrate_sqlite_to_json.py`

**任務**:
```python
# 需要實現的遷移邏輯
def export_sqlite_to_json():
    # 1. 連接 SQLite，讀取全部資料
    # 2. 構建正規化的 JSON 結構
    # 3. 寫入 JSON 檔案 (含備份)
    # 4. 驗證資料完整性 (計數、雜湊檢查)
    # 5. 記錄遷移日誌

def import_json_to_sqlite():
    # 反向遷移（安全回退）
    pass

def validate_migration():
    # 驗證遷移成功
    pass
```

**複雜性**:
- 需處理 NULL 值、關聯表 (video_actress_link)
- 需驗證資料型別轉換 (TIMESTAMP → ISO 字串)
- 需生成遷移報告

### 2. **業務邏輯層改造** (8-12 小時)

#### 2.1 Classifier Core 適配 (5-7 小時)
**檔案**: `src/services/classifier_core.py`

**變更點**:
```python
# 舊方式
self.db_manager = SQLiteDBManager(config.get('database', 'database_path'))

# 新方式
if config.get('database', 'type') == 'json':
    self.db_manager = JSONDBManager(config.get('database', 'data_dir'))
else:
    self.db_manager = SQLiteDBManager(config.get('database', 'database_path'))
```

**需要修改的方法**:
- `process_and_search_javdb()` - L260-370 (10+ 行邏輯)
- `process_and_search_with_sources()` - L196-240
- `interactive_move_files()` - L385-450
- `smart_classify_by_actress()` - L500+

**影響**: 無實質改變，只是資料庫 API 呼叫

#### 2.2 其他服務適配 (3-5 小時)
**檔案**: 
- `src/services/studio_classifier.py` - 使用 `db_manager.get_all_videos()`
- `src/services/interactive_classifier.py` - 統計查詢
- `src/ui/main_gui.py` - GUI 整合

**變更類型**: 大多是類別初始化參數修改

### 3. **快取管理改造** (5-8 小時)

#### 3.1 Cache Manager 遷移 (3-5 小時)
**檔案**: `src/scrapers/cache_manager.py`

**現狀**:
```python
# 目前使用 SQLite 快取
self.db_file = "cache_index.db"
with sqlite3.connect(str(self.db_path)) as conn:
    cursor = conn.cursor()
    # SQL 操作...
```

**改造方案**: JSON 快取 (已部分支持)
- 將索引快取改為 JSON
- 保持搜尋快取 JSON 格式 (不變)

#### 3.2 快取序列化 (2-3 小時)
**檔案**: `src/scrapers/cache_manager.py`

**任務**:
- 實現 JSON 快取索引的序列化
- 處理快取過期邏輯

### 4. **UI 層改造** (3-5 小時)

#### 4.1 GUI 更新
**檔案**: `src/ui/main_gui.py`, `src/ui/preferences_dialog.py`

**變更**:
- 新增資料庫類型選擇 (設定對話框)
- 新增資料遷移界面 (進度條、日誌)
- 新增效能監視 (JSON 載入時間等)

### 5. **測試**  (8-12 小時)

#### 5.1 單元測試 (4-6 小時)
**檔案**: `tests/test_json_database.py` (新增)

**測試覆蓋**:
```python
class TestJSONDBManager:
    def test_add_or_update_video()          # CRUD 基本操作
    def test_get_video_info()               # 查詢
    def test_get_all_videos()               # 批量查詢
    def test_concurrent_updates()           # 並發測試
    def test_actress_statistics()           # JOIN 邏輯
    def test_data_persistence()             # 持久化驗證
    def test_json_file_corruption_recovery()# 容錯
    def test_migration_data_integrity()     # 遷移驗證
```

#### 5.2 整合測試 (2-3 小時)
- 完整搜尋流程
- GUI 互動測試
- 效能基準測試

#### 5.3 迴歸測試 (2-3 小時)
- 現有功能驗證
- 邊界案例

### 6. **文件與部署** (3-5 小時)

- 遷移指南
- API 文件更新
- 效能基準報告
- 部署腳本

---

## 🔄 影響檔案清單

### 直接修改 (15 個檔案)
| 檔案 | 修改類型 | 複雜度 | 時間 |
|------|---------|--------|------|
| `src/models/database.py` | 重構 + 新類別 | 🔴 高 | 8-10h |
| `src/services/classifier_core.py` | 適配 | 🟠 中 | 3-4h |
| `src/services/studio_classifier.py` | 適配 | 🟢 低 | 1h |
| `src/services/interactive_classifier.py` | 適配 | 🟢 低 | 1h |
| `src/ui/main_gui.py` | 擴展 + 適配 | 🟠 中 | 2-3h |
| `src/ui/preferences_dialog.py` | 擴展 | 🟠 中 | 1-2h |
| `src/scrapers/cache_manager.py` | 遷移 | 🟠 中 | 3h |
| `src/models/config.py` | 擴展 | 🟢 低 | 0.5h |
| `run.py` | 適配 | 🟢 低 | 0.5h |
| `tests/test_*.py` | 新增 + 修改 | 🟠 中 | 8-10h |
| `scripts/migrate_sqlite_to_json.py` | 新增 | 🟠 中 | 5-7h |
| `setup_github.ps1` | 無改 | - | - |
| `example_*.py` | 更新 | 🟢 低 | 1h |
| `config.ini` | 擴展 | 🟢 低 | 0.5h |
| `requirements.txt` | 可能新增 | 🟢 低 | 0.5h |

### 間接相關 (5+ 檔案)
- `src/services/web_searcher.py` - 檢查相容性
- `src/services/safe_*.py` - 檢查相容性
- `docs/*.md` - 文件更新

---

## ⚠️ 關鍵風險與挑戰

### 1. **並發存取** (高風險) 🔴
**問題**: JSON 檔案是單檔案，不支援原生並發
- SQLite 有 VACUUM, PRAGMA 等機制
- JSON 需要檔案鎖 (file lock)

**解決方案**:
```python
import filelock

class JSONDBManager:
    def __init__(self):
        self.lock = filelock.FileLock(f"{self.data_file}.lock")
    
    def add_or_update_video(self, code, info):
        with self.lock:  # 排他性鎖
            data = self._load()
            # 修改資料
            self._save(data)
```

**成本**: +3-5 小時

### 2. **性能下降** (中風險) 🟠
**問題**: JSON 全量載入 vs SQLite 部分查詢
- 載入 10,000 個影片: ~500ms (vs SQLite <10ms)
- 單次修改需重新寫入整個檔案

**解決方案**:
1. **記憶體快取** - 在記憶體保持副本，定時同步
2. **分片儲存** - 按首字母分成 26 個 JSON 檔案
3. **異步寫入** - 後台執行緒定期 flush

**成本**: +10-15 小時 (效能優化)

### 3. **資料完整性** (高風險) 🔴
**問題**: 寫入過程中斷可能導致檔案損壞
- SQLite 有事務 (ACID)
- JSON 無原生事務

**解決方案**:
```python
# 原子性寫入策略
def _save(self, data):
    temp_file = f"{self.data_file}.tmp"
    with open(temp_file, 'w') as f:
        json.dump(data, f)
    os.replace(temp_file, self.data_file)  # 原子操作
```

**成本**: +2-3 小時

### 4. **統計查詢複雜度** (中風險) 🟠
**問題**: JOIN 查詢需要手動實現
```python
# SQLite 簡單
SELECT a.name, COUNT(*) FROM actresses a 
JOIN video_actress_link va ON ...
GROUP BY a.name

# JSON 複雜
actresses = {}
for video_id, actresses_list in video_actress_links.items():
    for actress_name in actresses_list:
        actresses[actress_name] = actresses.get(...) + 1
```

**成本**: +3-5 小時

### 5. **測試覆蓋** (中風險) 🟠
**問題**: 需要大量並發、邊界、容錯測試

**成本**: +8-10 小時

---

## 📈 工作量總結表

| 階段 | 工項 | 預計小時 | 關鍵風險 |
|------|------|---------|---------|
| **1. 資料層** | JSON 管理器 | 8-10 | 並發、完整性 |
| | 遷移工具 | 5-7 | 資料驗證 |
| **2. 業務層** | Core 適配 | 5-7 | 邏輯一致性 |
| | 其他適配 | 3-5 | 兼容性 |
| **3. 快取層** | 快取遷移 | 5-8 | 序列化 |
| **4. UI 層** | 介面擴展 | 3-5 | 使用體驗 |
| **5. 測試** | 單元 + 整合 | 8-12 | 覆蓋度 |
| **6. 文件/部署** | 文件 + 腳本 | 3-5 | 清晰度 |
| **總計** | | **40-60 小時** | |

### 時間估計範圍解讀
- **快速路徑** (40 小時): 基本轉換，部分功能未優化
- **完整路徑** (60 小時): 含性能優化、全面測試

---

## 🎯 推薦方案：漸進式轉換策略

### 階段 1: 並行雙層 (第 1-2 週)
```
配置文件選擇
├─ "database.type": "sqlite"  (現有)
└─ "database.type": "json"    (新增)

代碼適配層
├─ SQLiteDBManager (保留)
└─ JSONDBManager  (新增)

切換邏輯
```

**優點**:
- ✅ 可隨時切換回 SQLite
- ✅ 並行測試
- ✅ 無風險驗證

**成本**: 40-50 小時

### 階段 2: 性能優化 (第 3 週)
- 記憶體快取
- 分片儲存
- 異步寫入

**成本**: +10-15 小時

### 階段 3: 完全遷移 (第 4 週)
- 移除 SQLite 代碼
- 清理相容層
- 最終測試

**成本**: +5-10 小時

**總時程**: **3-4 週** (預計 60-75 小時)

---

## 📋 User Scenarios & Testing (Priority-Ordered)

### User Story 1 - 轉換現有資料 (Priority: P1)
**使用者角色**: 系統管理員
**場景**:
1. 執行遷移工具
2. 看到進度條 (已處理 X/N 記錄)
3. 遷移完成，生成驗證報告
4. 驗證資料一致性 (行數、女優數等)

**Why P1**: 無法轉換資料意味著整個功能無法使用

**Independent Test**: 執行遷移腳本 → 驗證輸出檔案內容 → 對比 SQLite 資料

### User Story 2 - 系統自動切換資料庫 (Priority: P1)
**使用者角色**: 使用者
**場景**:
1. 編輯 config.ini，設定 `database.type=json`
2. 啟動應用程式
3. 應用程式自動使用 JSON 資料庫

**Why P1**: 無法切換表示架構適配失敗

**Independent Test**: 改變配置 → 重啟 → 驗證資料可讀寫

### User Story 3 - 搜尋功能正常運作 (Priority: P1)
**使用者角色**: 終端使用者
**場景**:
1. 選擇影片資料夾
2. 執行搜尋 (使用 JSON 資料庫)
3. 結果儲存成功
4. 下次啟動時可讀取

**Why P1**: 核心功能必須工作

**Independent Test**: 完整搜尋流程 → 驗證 JSON 檔案 → 重啟驗證資料

### User Story 4 - 效能可接受 (Priority: P2)
**使用者角色**: 使用者
**場景**:
1. 載入 10,000+ 影片
2. 介面響應時間 < 2s
3. 搜尋結果 < 3s

**Why P2**: 基本功能正常後才關注性能

**Independent Test**: 記錄各操作耗時 → 對比基準

### User Story 5 - 資料備份與復原 (Priority: P2)
**使用者角色**: 系統管理員
**場景**:
1. 系統自動建立備份 (每日)
2. 遇到損壞可復原
3. 提供復原日誌

**Why P2**: 容災但非首要

**Independent Test**: 刪除 JSON 檔案 → 復原 → 驗證

### User Story 6 - 並發操作無衝突 (Priority: P3)
**使用者角色**: 多使用者環境
**場景**:
1. 兩個進程同時修改資料
2. 無資料遺失/損壞
3. 操作序列化正確

**Why P3**: 當前單用戶，多用戶為未來

**Independent Test**: 多執行緒測試

---

## ✅ Success Criteria

### 功能性成功標準
1. **資料完整性**: 
   - ✅ 遷移後記錄數 = 遷移前記錄數
   - ✅ 所有關聯關係保留
   - ✅ 時間戳記精度保留 (秒級)

2. **API 相容性**:
   - ✅ JSONDBManager 提供與 SQLiteDBManager 相同的公開介面
   - ✅ 現有代碼無需修改可使用
   - ✅ 單元測試通過率 ≥ 95%

3. **搜尋功能**:
   - ✅ 搜尋成功率與 SQLite 相同
   - ✅ 資料儲存正確
   - ✅ 統計查詢結果準確

### 性能標準
4. **載入時間**:
   - ✅ 初始載入 10,000 條記錄 < 1s (記憶體快取後)
   - ✅ 單次查詢 < 100ms
   - ✅ 不因資料量增加而線性下降

5. **寫入操作**:
   - ✅ 新增影片 < 500ms
   - ✅ 批量更新 < 2s (for 100 records)
   - ✅ 檔案大小 vs SQLite 在 10% 內

### 可靠性標準
6. **資料安全**:
   - ✅ 寫入失敗自動回復
   - ✅ 並發操作無資料遺失
   - ✅ 損壞檔案可復原

7. **測試覆蓋**:
   - ✅ 核心方法覆蓋率 ≥ 85%
   - ✅ 邊界案例覆蓋 ≥ 80%
   - ✅ 無回歸缺陷

---

## 📝 Assumptions & Constraints

### 假設
1. ✅ 使用者接受短期性能不如 SQLite (後期優化)
2. ✅ 資料量不超過 100,000 條記錄
3. ✅ 單一使用者或低並發環境
4. ✅ 磁碟空間充足 (JSON > SQLite 5-10%)

### 限制
1. 🔴 **並發限制**: 需要檔案鎖實現序列化
2. 🔴 **複雜查詢**: JOIN 需要手動實現 (可能產生性能問題)
3. 🟠 **版本相容性**: 需要向後相容 SQLite 資料

### 相依性
- `filelock` 套件 (新增依賴)
- Python 3.7+ (pathlib)
- 現有 JSON 快取結構

---

## 🚀 建議的進度

### 第 1 週: 核心構建
- ✅ 實現 JSONDBManager 基礎類別
- ✅ 實現資料遷移工具
- ✅ 基本單元測試

**時間**: 15-20 小時

### 第 2 週: 整合與測試
- ✅ 業務層適配 (Classifier Core 等)
- ✅ 整合測試
- ✅ 並發測試

**時間**: 15-20 小時

### 第 3 週: 優化與驗證
- ✅ 性能優化 (可選)
- ✅ GUI 擴展 (可選)
- ✅ 完整迴歸測試

**時間**: 10-15 小時

### 第 4 週: 部署與文件
- ✅ 部署腳本
- ✅ 遷移指南
- ✅ 最終驗收

**時間**: 5-10 小時

---

## 📋 Key Entities (Data Model)

### JSON 資料結構設計

```json
{
  "metadata": {
    "version": "1.0",
    "created": "2025-10-16T22:00:00Z",
    "last_updated": "2025-10-16T23:00:00Z",
    "record_count": 150
  },
  "videos": {
    "SONE-909": {
      "id": 1,
      "code": "SONE-909",
      "original_filename": "SONE-909.mp4",
      "file_path": "/videos/SONE-909.mp4",
      "studio": "S1",
      "studio_code": "SONE",
      "release_date": "2024-06-26",
      "search_method": "JAVDB",
      "last_updated": "2025-10-16T10:30:00Z",
      "search_status": "searched_found",
      "last_search_date": "2025-10-16T10:30:00Z",
      "actress_ids": [1, 2]  // 關聯女優 ID
    }
  },
  "actresses": {
    "1": {
      "id": 1,
      "name": "白上咲花"
    },
    "2": {
      "id": 2,
      "name": "其他女優"
    }
  },
  "studios": {
    "SONE": {
      "code": "SONE",
      "name": "S1 NO.1 STYLE"
    }
  },
  "video_actress_links": {
    "1": {
      // video_id: 1
      "actress_ids": [1, 2],
      "association_types": ["primary", "collaboration"]
    }
  }
}
```

### 關鍵實體關係
- **Videos** ↔ **Actresses**: 多對多 (via video_actress_links)
- **Videos** ↔ **Studios**: 多對一
- 所有時間戳統一為 ISO 8601 格式

---

## [NEEDS CLARIFICATION: 1] 是否需要完全替換 SQLite，還是並行支持?

**Context**: 目前系統完全依賴 SQLite。轉換方式會影響工作量和風險。

**What we need to know**: 轉換策略的優先級

| 選項 | 做法 | 優點 | 缺點 | 工時差異 |
|------|------|------|------|---------|
| A | **完全替換** - 移除所有 SQLite 代碼 | 代碼簡潔 | 無回退方案，風險高 | 基準 |
| B | **並行雙層** (推薦) - SQLite + JSON 並存 | 可隨時切換，風險低 | 代碼複雜度增加 | +2-3h |
| C | **漸進遷移** - 先 SQLite，定期同步到 JSON | 最安全 | 最複雜 | +5-8h |

**Suggested Answer**: 
- 推薦 **B (並行雙層)**: 可通過配置文件切換，實驗性功能
- 實現順序: B → C (如需完整遷移)

---

## [NEEDS CLARIFICATION: 2] 效能如何重新定義? 是否可接受初期的性能下降?

**Context**: JSON 全量載入必然比 SQLite 慢。需要確認可接受的性能指標。

| 指標 | SQLite 基線 | JSON 初期 | JSON 優化後 |
|------|-----------|---------|----------|
| 載入 10k 記錄 | 5-10ms | 500ms | 50ms (快取後) |
| 查詢單筆 | < 5ms | 50-100ms | < 10ms (快取) |
| 新增記錄 | 20-50ms | 500-1000ms | 100-200ms |

**Your choice**: _依賴於用戶容忍度_

---

## [NEEDS CLARIFICATION: 3] 資料量規模預期? 影響分片策略

**Context**: 100 條 vs 100,000 條記錄影響 JSON 分片是否必要。

| 規模 | 單檔案策略 | 建議分片 | JSON 檔案大小 |
|------|----------|---------|------------|
| < 1,000 | ✅ 可行 | 不需要 | < 1 MB |
| 1-10k | ⚠️ 可行 | 考慮 | 1-10 MB |
| 10-100k | ❌ 不建議 | ✅ 必須 | 10-100 MB |

**Your choice**: _估計當前資料量和成長率_

---

## 結論與建議

### ✅ 本規格適合以下情況
- 想要**評估轉換工作量**
- 想要**理解技術風險**
- 計劃**長期 Go 重構** (JSON 是目標)
- 需要**詳細的工作分解**

### 🎯 建議的下一步
1. **確認決策**: 選擇並行雙層還是完全替換
2. **定義性能目標**: 可接受的性能水準
3. **開始第 1 週**: 實現 JSONDBManager 基礎類別
4. **進行 POC**: 小規模資料遷移驗證

### 📊 工作評估總結
| 項目 | 評估 |
|------|------|
| **總工時** | **40-60 小時 (依策略)** |
| **修改檔案** | **15 個直接修改 + 5 個查核** |
| **複雜度** | **高 (架構級別改動)** |
| **風險** | **中-高 (需充分測試)** |
| **推薦進度** | **3-4 週 (全職)** |
| **建議優先級** | **P3 (Go 重構前進行)** |

---

**Specification Status**: ✅ Ready for Clarification → Planning Phase

