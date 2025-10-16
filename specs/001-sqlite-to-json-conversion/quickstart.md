# Quick Start: JSONDBManager 使用指南

**Feature**: 001-sqlite-to-json-conversion  
**Created**: 2025-10-16

---

## 概述

`JSONDBManager` 是 `SQLiteDBManager` 的 JSON 替代實作，提供相同的介面但使用 JSON 檔案儲存。遷移過程無需修改業務邏輯程式碼。

---

## 安裝和設定

### 1. 安裝依賴套件

```bash
pip install filelock  # 並行存取控制
```

### 2. 初始化 JSONDBManager

```python
from src.models.database import JSONDBManager

# 建立 manager 實例
db_manager = JSONDBManager(
    data_dir="data/json_db"  # JSON 資料目錄
)
```

### 3. 驗證初始化

```python
# 檢查資料目錄
import os
assert os.path.exists("data/json_db"), "資料目錄未建立"
assert os.path.exists("data/json_db/actress_data.json"), "資料檔不存在"

print("✅ JSONDBManager 初始化完成")
```

---

## 基本使用

### 新增影片

```python
video_info = {
    "id": "jav_001",
    "title": "Sample Video",
    "studio": "Studio A",
    "release_date": "2023-10-15",
    "url": "https://example.com/video/001",
    "actresses": ["actress_001", "actress_002"],
    "search_status": "success",
    "last_search_date": "2025-10-16T08:30:00Z"
}

success = db_manager.add_or_update_video(video_info)
print(f"影片新增: {success}")
```

### 查詢影片

```python
# 查詢單部影片
video = db_manager.get_video_info("jav_001")
if video:
    print(f"片名: {video['title']}")
    print(f"片商: {video['studio']}")

# 取得所有影片
all_videos = db_manager.get_all_videos()
print(f"總影片數: {len(all_videos)}")

# 篩選查詢
studio_videos = db_manager.get_all_videos({"studio": "Studio A"})
print(f"Studio A 的影片數: {len(studio_videos)}")
```

### 新增女優

```python
actress_info = {
    "id": "actress_001",
    "name": "女優名字",
    "aliases": ["別名1", "別名2"]
}

# 透過內部方法新增
# (通常透過 add_or_update_video 自動建立)
```

### 查詢統計資訊

```python
# 女優統計
actress_stats = db_manager.get_actress_statistics()
for actress_id, stats in actress_stats.items():
    print(f"{stats['name']}: {stats['video_count']} 部")

# 片商統計
studio_stats = db_manager.get_studio_statistics()
for studio, stats in studio_stats.items():
    print(f"{studio}: {stats['video_count']} 部")

# 交叉統計
cross_stats = db_manager.get_enhanced_actress_studio_statistics()
for stat in cross_stats['cross_stats']:
    print(f"{stat['actress']} - {stat['studio']}: {stat['video_count']} 部")
```

---

## 進階用法

### 並行存取

```python
import threading
from concurrent.futures import ThreadPoolExecutor

def add_videos_concurrent():
    """多執行緒新增影片"""
    
    def add_video(video_id):
        db_manager.add_or_update_video({
            "id": f"video_{video_id}",
            "title": f"Video {video_id}",
            "studio": "Test Studio",
            "release_date": "2025-10-16",
            "url": f"https://example.com/{video_id}",
            "actresses": [],
            "search_status": "success",
            "last_search_date": "2025-10-16T00:00:00Z"
        })
    
    # 使用 ThreadPoolExecutor 管理並行
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(add_video, i) for i in range(100)]
        results = [f.result() for f in futures]
    
    print(f"✅ 並行新增 {len(results)} 部影片")
```

### 備份和恢復

```python
# 建立備份
backup_path = db_manager.create_backup()
print(f"備份位置: {backup_path}")

# 模擬資料損壞...
# data_file corrupted

# 從備份還原
db_manager.restore_from_backup(backup_path)
print("✅ 資料已還原")
```

### 資料驗證

```python
# 驗證資料完整性
is_valid = db_manager.validate_data()
if is_valid:
    print("✅ 資料完整性檢查通過")
else:
    print("⚠️ 發現資料問題，已嘗試修復")
    
# 取得驗證報告
report = db_manager.get_validation_report()
print(f"記錄數: {report['record_count']}")
print(f"資料雜湊: {report['hash']}")
```

### 資料遷移

```python
from scripts.migrate_sqlite_to_json import export_sqlite_to_json, validate_migration

# 1. 執行遷移
migration_result = export_sqlite_to_json(
    sqlite_path="data/actress_classifier.db",
    json_path="data/json_db/actress_data.json"
)
print(f"遷移結果: {migration_result}")

# 2. 驗證遷移
validation = validate_migration()
if validation['status'] == 'success':
    print(f"✅ 遷移驗證通過")
    print(f"   - SQLite 記錄: {validation['sqlite_count']}")
    print(f"   - JSON 記錄: {validation['json_count']}")
else:
    print(f"❌ 遷移驗證失敗: {validation['error']}")
```

---

## 效能最佳實踐

### 1. 批次操作

```python
# ❌ 效率低 (100 次 I/O)
for video in videos:
    db_manager.add_or_update_video(video)

# ✅ 效率高 (將操作合併)
# 實作批次方法
def add_videos_batch(videos_list):
    """批次新增影片，減少 I/O"""
    # 一次性讀取、更新、寫入
```

### 2. 快取統計資訊

```python
# 快取統計結果，避免重複計算
actress_stats = db_manager.get_actress_statistics()
# 快取此結果

# 若資料無變更，直接使用快取
# 若資料有變更，重新計算
```

### 3. 連接池管理

```python
# 單一全域實例 (無連接池概念，但保持實例重用)
_db_manager = None

def get_db_manager():
    global _db_manager
    if _db_manager is None:
        _db_manager = JSONDBManager("data/json_db")
    return _db_manager

# 使用全域實例
db = get_db_manager()
db.add_or_update_video(...)
```

---

## 錯誤處理

### 常見錯誤

```python
from src.models.database import (
    JSONDatabaseError,
    ValidationError,
    LockError
)

try:
    db_manager.add_or_update_video(video)
except ValidationError as e:
    print(f"資料驗證失敗: {e}")
    # 檢查欄位格式
except LockError as e:
    print(f"檔案鎖定超時: {e}")
    # 稍候重試
except JSONDatabaseError as e:
    print(f"資料庫錯誤: {e}")
    # 檢查檔案權限和磁碟空間
```

### 日誌記錄

```python
import logging

# 設定日誌等級
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# JSONDBManager 自動記錄操作
logger.info("正在新增影片...")
db_manager.add_or_update_video(video)
logger.info("影片新增完成")
```

---

## 遷移檢查清單

進行 SQLite → JSON 遷移時的檢查清單:

- [ ] 安裝 `filelock` 依賴
- [ ] 初始化 JSONDBManager
- [ ] 執行 `export_sqlite_to_json()` 遷移工具
- [ ] 驗證遷移: `validate_migration()`
- [ ] 測試並行存取: 5+ 進程同時讀寫
- [ ] 測試備份恢復: 建立備份並還原
- [ ] 更新業務邏輯指向 JSONDBManager
- [ ] 更新單元測試
- [ ] 更新 UI 移除資料庫選擇
- [ ] 執行集成測試
- [ ] 刪除舊 SQLite 程式碼
- [ ] 更新文件
- [ ] 最終驗證: `validate_data()`

---

## 常見問題 (FAQ)

### Q: JSONDBManager 相比 SQLite 慢多少？
**A**: 初期約 10-100 倍慢 (取決於資料量)。透過記憶體快取和預計算統計，典型效能在可接受範圍內 (<100ms 查詢)。

### Q: 併行操作安全嗎？
**A**: 是的。使用 `filelock` 確保讀寫一致性。但寫操作會被序列化 (同一時間只有一個寫者)。

### Q: 如何處理大資料集 (>100,000 筆)？
**A**: 建議分片儲存:
```python
# 按年份分片
data/json_db/
├── actress_data_2020.json
├── actress_data_2021.json
└── actress_data_2025.json
```

### Q: 可以回滾到 SQLite 嗎？
**A**: 可以。保持 SQLite 備份，使用 `import_json_to_sqlite()` 反向遷移。

### Q: JSON 檔案損壞怎麼辦？
**A**: 自動檢測和修復:
```python
db_manager.validate_data()  # 自動修復損壞
# 或手動從備份還原
db_manager.restore_from_backup(backup_path)
```

---

## 後續支援

- 📖 詳細 API 文件: `docs/json_database_api.md`
- 🔧 故障排除: `docs/troubleshooting.md`
- 📊 效能基準: `docs/performance_benchmarks.md`
- 🧪 測試指南: `tests/README.md`

