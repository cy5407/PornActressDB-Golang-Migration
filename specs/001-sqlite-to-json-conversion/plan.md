# Implementation Plan: SQLite 轉換為 JSON 資料庫儲存

**Feature Branch**: `001-sqlite-to-json-conversion`  
**Plan Created**: 2025-10-16  
**Status**: In Planning  
**Last Updated**: 2025-10-16

---

## Technical Context

### Current Architecture

**Database Layer** (`src/models/database.py`, 457 lines):
- `SQLiteDBManager` 類別管理所有資料庫操作
- 使用 `sqlite3` 模組，支援自動型別檢測
- Schema 包含 3 個表：videos、actresses、video_actress_link
- 新增 `search_status` 和 `last_search_date` 欄位用於搜尋追蹤

**Business Logic Dependencies** (20+ 檔案):
- `classifier_core.py` (779 行): 多個 db_manager 呼叫
- `cache_manager.py`: 同時使用 SQLite 索引和 JSON 搜尋快取
- UI 層 (`main_gui.py`, `preferences_dialog.py`): 透過 db_manager 抽象存取

**Data Volume**:
- 目前: ~150 筆影片記錄
- 目標: 支援 10,000+ 筆無效能下降

### Technology Choices

**JSON 儲存格式**:
- **檔案結構**: 單一 `data.json` 檔案 (原始資料層) + 分組快取 (效能優化)
- **序列化**: Python `json` 模組 (內建，無額外依賴)
- **編碼**: UTF-8 (支援中文、特殊字元)

**並行控制**:
- **方案**: `filelock` 套件用於檔案級鎖定
- **讀操作**: 共享鎖 (多個讀者可並行)
- **寫操作**: 獨佔鎖 (單一寫者)
- **備選**: `fcntl` (Unix/Linux) + `msvcrt` (Windows)

**效能優化**:
- **記憶體快取**: 讀取時快取整個 JSON 以避免重複 I/O
- **延遲寫入**: 批次寫入，減少 I/O 操作
- **索引層**: 快速查找而無需全表掃描

**資料驗證**:
- **格式檢查**: JSON 結構驗證 (無效檔案自動重建)
- **完整性檢查**: SHA256 雜湊驗證
- **版本控制**: 在 JSON 中記錄 Schema 版本

---

## Constitution Check

### Compliance Requirements (from constitution.md)

| 需求 | 項目 | 狀態 |
|-----|------|------|
| **通信標準** | 所有文件使用繁體中文 | ✅ 規劃中已符合 |
| **通信標準** | 程式碼註解用繁體中文 | ✅ 將在實作中確保 |
| **通信標準** | Git 提交用英文 | ✅ 已執行 |
| **品質標準** | Python 3.8+ | ✅ 專案已使用 Python 3.8+ |
| **品質標準** | 程式碼風格一致性 | ✅ 將使用 black + pylint |
| **品質標準** | 型別檢查** | ✅ 將使用 mypy |
| **品質標準** | 錯誤處理 | ✅ 所有錯誤需要上下文包裝 |
| **品質標準** | 結構化日誌** | ✅ 使用 Python `logging` 模組 |
| **品質標準** | 測試覆蓋** | ✅ 目標 ≥70% 單元測試 |

**Gate 評估**: ✅ **PASS** - 所有憲法要求已定義並可達成

---

## Data Model

### Entity Definitions

#### Video (影片)
```python
{
    "id": str,                      # 唯一識別符 (例: "123abc")
    "title": str,                   # 片名
    "studio": str,                  # 片商名稱
    "release_date": str,            # 發行日期 (ISO 8601: YYYY-MM-DD)
    "url": str,                     # 線上連結
    "actresses": [str],             # 女優 ID 清單
    "search_status": str,           # "success" | "partial" | "failed"
    "last_search_date": str,        # 最後搜尋日期 (ISO 8601)
    "created_at": str,              # 建立時間
    "updated_at": str,              # 更新時間
    "metadata": {                   # 額外資訊
        "source": str,              # 資料來源
        "confidence": float         # 資訊置信度 (0.0-1.0)
    }
}
```

#### Actress (女優)
```python
{
    "id": str,                      # 唯一識別符
    "name": str,                    # 女優名字
    "aliases": [str],               # 別名清單
    "video_count": int,             # 出演部數 (快取欄位)
    "created_at": str,              # 建立時間
    "updated_at": str               # 更新時間
}
```

#### VideoActressLink (關聯表)
```python
{
    "video_id": str,                # 影片 ID
    "actress_id": str,              # 女優 ID
    "role_type": str,               # 角色類型 (主演/配角)
    "created_at": str               # 關聯建立時間
}
```

#### Statistics (統計快取)
```python
{
    "actress_stats": {
        "<actress_id>": {
            "name": str,
            "video_count": int,
            "studios": [str],
            "date_range": {"start": str, "end": str}
        }
    },
    "studio_stats": {
        "<studio_name>": {
            "video_count": int,
            "actresses": [str],
            "date_range": {"start": str, "end": str}
        }
    },
    "cross_stats": [
        {
            "actress": str,
            "studio": str,
            "video_count": int
        }
    ],
    "last_updated": str             # 最後計算時間
}
```

### JSON 檔案結構

```
data/
├── actress_data.json              # 主資料檔 (Video + Actress + Links)
├── statistics_cache.json          # 統計快取 (快速查詢)
├── backup/
│   ├── actress_data.2025-10-16.backup
│   └── actress_data.2025-10-15.backup
└── .datalock                       # 檔案鎖定標記
```

---

## Phase 0: Research & Analysis

### Research Topics

#### R1: 最佳效能最佳實踐 - JSON 資料庫在 Python 中
**決策**: 使用單檔 JSON + 記憶體快取架構
**基本原理**: 
- 簡單實作，無需額外 DB 系統
- 支援版本控制 (Git 友善)
- 記憶體快取解決效能問題 (典型 JSON 檔案 <10MB)

**替代方案考量**:
- ❌ 多檔 JSON: 複雜性高，查詢困難
- ❌ SQLite 替代品 (如 DuckDB): 超出需求，仍需遷移

#### R2: 並行存取安全性
**決策**: `filelock` 套件 + 讀寫鎖機制
**基本原理**:
- 跨平台支援 (Windows/Linux/macOS)
- 簡單 API，易於整合
- 原子寫入確保資料一致性

**實作策略**:
```python
# 讀操作: 共享鎖
with filelock.FileLock("data/.read.lock", timeout=5):
    data = load_json()
    
# 寫操作: 獨佔鎖
with filelock.FileLock("data/.write.lock", timeout=10):
    data = load_json()
    data.update(changes)
    save_json(data)  # 原子操作
```

#### R3: 資料驗證和恢復策略
**決策**: 多層驗證 + 自動備份
**基本原理**:
- 偵測損壞: JSON 語法檢查
- 完整性檢查: SHA256 雜湊
- 自動修復: 從最新備份還原

**實作細節**:
```python
# 1. JSON 格式驗證
try:
    data = json.loads(content)
except json.JSONDecodeError:
    # 從備份還原
    restore_from_backup()

# 2. 完整性檢查
stored_hash = data.get("_metadata", {}).get("hash")
computed_hash = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
if stored_hash != computed_hash:
    # 資料損壞，從備份還原
    restore_from_backup()
```

#### R4: 查詢等價性 - JOIN 邏輯轉換
**決策**: 手動實作 JOIN 邏輯在 Python 層
**基本原理**:
- SQLite 原生 JOIN → Python dict/list 操作
- 通過預計算統計快取優化

**複雜查詢轉換示例**:
```sql
-- SQLite 原始查詢
SELECT a.name, COUNT(DISTINCT v.id) as video_count
FROM actresses a
LEFT JOIN video_actress_link val ON a.id = val.actress_id
LEFT JOIN videos v ON val.video_id = v.id
GROUP BY a.id
```

```python
# 轉換為 Python
actress_stats = {}
for actress in actresses:
    video_ids = set()
    for link in video_actress_links:
        if link['actress_id'] == actress['id']:
            video_ids.add(link['video_id'])
    actress_stats[actress['id']] = {
        'name': actress['name'],
        'video_count': len(video_ids)
    }
```

---

## Phase 1: Design & Implementation Structure

### 1.1 資料層重構 (15-20 小時)

#### Task 1.1.1: JSONDBManager 類別開發 (8-10 小時)
**檔案**: `src/models/database.py`

**核心方法**:
```python
class JSONDBManager:
    def __init__(self, data_dir: str):
        """初始化，建立目錄結構和檔案鎖"""
        
    def _load_all_data(self) -> dict:
        """從 JSON 檔案載入全部資料，含驗證和修復"""
        
    def _save_all_data(self, data: dict) -> None:
        """原子性寫入全部資料，含備份"""
        
    def add_or_update_video(self, video_info: dict) -> bool:
        """新增或更新影片 (並發安全)"""
        
    def get_video_info(self, video_id: str) -> dict:
        """查詢單部影片資訊"""
        
    def get_all_videos(self, filter_dict: dict = None) -> list:
        """取得全部影片，支援篩選"""
        
    def get_actress_statistics(self) -> dict:
        """女優統計 (手動 JOIN)"""
        
    def get_studio_statistics(self) -> dict:
        """片商統計"""
        
    def get_enhanced_actress_studio_statistics(self) -> dict:
        """增強版交叉統計"""
        
    def create_backup(self) -> str:
        """建立備份快照"""
        
    def delete_video(self, video_id: str) -> bool:
        """刪除影片"""
```

**複雜性分析**:
- 需實作 JOIN 邏輯 (手動關聯表查詢)
- 需實作並發鎖機制
- 需實作資料驗證和修復

#### Task 1.1.2: 遷移工具開發 (5-7 小時)
**檔案**: `scripts/migrate_sqlite_to_json.py`

**功能**:
```python
def export_sqlite_to_json():
    """將 SQLite 完整轉換至 JSON"""
    # 1. 讀取全部 SQLite 資料
    # 2. 構建 JSON 結構
    # 3. 驗證記錄計數、雜湊
    # 4. 寫入 JSON 檔案
    # 5. 生成遷移報告

def validate_migration() -> dict:
    """驗證遷移成功"""
    # 對比 SQLite 和 JSON 的記錄計數
    # 對比統計結果
    # 驗證資料完整性
```

### 1.2 業務邏輯適配 (8-12 小時)

#### Task 1.2.1: classifier_core.py 適配 (5-7 小時)
**檔案**: `src/services/classifier_core.py`

**變更方式**:
```python
# 舊
self.db_manager = SQLiteDBManager(...)

# 新
self.db_manager = JSONDBManager(...)  # 相同介面，不同實作
```

**受影響的方法** (需適配):
- `process_and_search_javdb()` - 7+ 行邏輯
- `process_and_search_with_sources()` - 4+ 行邏輯
- 統計方法呼叫 - 無變更 (相同介面)

#### Task 1.2.2: 其他服務層適配 (1-2 小時)
**檔案**: 
- `src/services/studio_classifier.py`
- `src/services/interactive_classifier.py`

**變更**: 初始化參數傳遞

### 1.3 UI 層改造 (3-4 小時)

#### Task 1.3.1: main_gui.py 更新
**變更**:
- 移除舊 SQLite 路徑配置
- 新增 JSON 資料目錄配置
- 無功能變更 (透過 db_manager 抽象)

#### Task 1.3.2: preferences_dialog.py 簡化
**變更**:
- 移除資料庫選擇對話框
- 移除相關 UI 元素

### 1.4 快取層改造 (2-3 小時)

**檔案**: `src/scrapers/cache_manager.py`
- 移除 SQLite 索引層
- 改用 JSON 搜尋快取

---

## Phase 2: Testing & Validation

### 2.1 單元測試 (4-6 小時)
**檔案**: `tests/test_json_database.py`

**測試項目**:
```python
# 基礎操作
test_add_video()
test_get_video()
test_update_video()
test_delete_video()

# 複雜查詢
test_actress_statistics_accuracy()
test_studio_statistics_accuracy()
test_cross_statistics_accuracy()

# 並行存取
test_concurrent_reads()
test_concurrent_writes()
test_read_write_conflict()

# 資料驗證
test_data_corruption_recovery()
test_backup_restore()
test_validation_check()
```

### 2.2 集成測試 (2-3 小時)
- 遷移工具端到端測試
- 系統功能完整性測試
- 效能基準測試

---

## Phase 3: Cleanup & Deployment

### 3.1 SQLite 程式碼移除 (2-3 小時)
**檔案**:
- 刪除 `SQLiteDBManager` 類別
- 刪除 SQLite 相關程式碼
- 更新配置檔案

### 3.2 文件和清理 (1-2 小時)
- 更新 README 和遷移指南
- 清理備份檔案
- 最終驗證

---

## Artifacts to Generate

### Phase 1 Deliverables

- [x] `research.md` - 研究結果和決策
- [ ] `data-model.md` - 資料模型詳細定義
- [ ] `contracts/` - API 約束 (不適用此專案)
- [ ] `quickstart.md` - 快速開始指南

### Implementation Files

- [ ] `src/models/database.py` (更新 - 新增 JSONDBManager)
- [ ] `src/models/json_database.py` (新增 - 專用實作)
- [ ] `scripts/migrate_sqlite_to_json.py` (新增)
- [ ] `tests/test_json_database.py` (新增)

---

## Success Metrics

| 標準 | 目標 | 驗證方法 |
|-----|------|--------|
| 資料完整性 | 100% | 遷移工具驗證 + 記錄計數檢查 |
| 查詢等價性 | 100% | 統計結果對比 (SQLite vs JSON) |
| 並行安全性 | 0 資料損壞 | 並行測試 (5 進程) |
| 效能 | <5分鐘遷移 500+ | 遷移工具測時 |
| 程式碼覆蓋 | ≥70% | Coverage 報告 |
| 移除完整性 | 0 SQLite 相依性 | 程式碼掃描 |

---

## Next Steps

1. ✅ **Phase 0**: 研究決策 (完成)
2. 📋 **Phase 1**: 設計和建構
   - 開發 JSONDBManager
   - 開發遷移工具
   - 適配業務邏輯
3. 🧪 **Phase 2**: 測試和驗證
4. 🧹 **Phase 3**: 清理和部署

**預計時程**: 40-60 小時 (2-3 週全職開發)

