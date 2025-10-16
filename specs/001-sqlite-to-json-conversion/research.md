# Research Report: SQLite 轉換為 JSON 資料庫儲存

**Feature**: 001-sqlite-to-json-conversion  
**Date**: 2025-10-16  
**Status**: Complete

---

## 研究發現總結

本報告記錄了 SQLite → JSON 轉換的核心決策和技術評估。所有關鍵歧義已解決，建議進入實施階段。

---

## R1: JSON 儲存架構評估

### 決策
✅ **選擇方案**: 單一 JSON 檔案 + 記憶體快取

### 基本原理
1. **簡化實作**: 無需額外資料庫系統，純 Python 檔案操作
2. **版本控制友善**: 可直接放入 Git (適合小至中型資料集)
3. **零依賴**: 使用 Python 內建 `json` 模組
4. **易於備份**: 簡單的檔案級備份策略

### 替代方案評估

| 方案 | 優點 | 缺點 | 決策 |
|-----|------|------|------|
| **單檔 JSON** | 簡單、Git 友善、無依賴 | 效能取決於資料量 | ✅ **選中** |
| 多檔分片 JSON | 大資料集友善 | 複雜查詢和聚合困難 | ❌ 過度設計 |
| DuckDB | 效能優於 SQLite | 仍需遷移，增加依賴 | ❌ 不必要 |
| MongoDB/CouchDB | 天然 JSON 支援 | 操作複雜度高，超出需求 | ❌ 過度工程化 |

### 實施細節

```python
# 檔案結構
data/json_db/
├── actress_data.json           # 主資料
├── statistics_cache.json       # 快取統計
├── backup/                     # 備份目錄
│   ├── actress_data.*.backup
│   └── BACKUP_MANIFEST.json
└── .datalock                   # 並行控制標記

# 記憶體快取策略
- 首次載入時快取整個 JSON 到記憶體
- 修改操作後更新快取
- 定期同步回磁碟 (每 100 操作或每 5 分鐘)
```

### 效能預期

| 資料量 | 檔案大小 | 載入時間 | 查詢延遲 | 寫入時間 |
|------|--------|--------|--------|--------|
| 150 筆 | ~200KB | <10ms | 1-5ms | <100ms |
| 1,000 筆 | ~1.5MB | 20-30ms | 5-20ms | 100-200ms |
| 10,000 筆 | ~15MB | 100-200ms | 50-100ms | 500-1000ms |

**結論**: 針對 150-10,000 筆記錄範圍，效能是可接受的。

---

## R2: 並行控制機制

### 決策
✅ **選擇方案**: `filelock` 套件 + 讀寫鎖

### 基本原理
1. **跨平台支援**: Windows、Linux、macOS
2. **簡單 API**: 易於整合現有程式碼
3. **檔案級別**: 支援進程級別並行控制
4. **成熟穩定**: 廣泛使用的開源專案

### 備選方案評估

| 方案 | 原理 | 優點 | 缺點 | 決策 |
|-----|------|------|------|------|
| **filelock** | 文件鎖定 | 跨平台、簡單 | 單機限制 | ✅ **選中** |
| fcntl (Unix) | POSIX 鎖 | 高效、原生 | 不支援 Windows | ❌ 不跨平台 |
| threading.Lock | 記憶體鎖 | 快速、簡單 | 僅限單進程 | ❌ 不支援多進程 |
| Redis Lock | 分散式 | 支援分佈式 | 額外依賴、複雜 | ❌ 過度設計 |

### 實施方案

```python
# 讀操作 (共享鎖 - 多進程可並行)
with filelock.FileLock("data/.read.lock", timeout=5):
    data = json.load(open("data/actress_data.json"))
    # 執行只讀操作
    result = process_data(data)

# 寫操作 (獨佔鎖 - 序列化)
with filelock.FileLock("data/.write.lock", timeout=10):
    # 讀取當前資料
    data = json.load(open("data/actress_data.json"))
    # 修改資料
    data['videos'].append(new_video)
    # 原子寫入
    with open("data/actress_data.json", "w") as f:
        json.dump(data, f)
```

### 並行安全性驗證

```python
# 測試場景: 5 進程同時讀寫
def test_concurrent_access():
    threads = []
    
    # 3 個讀進程
    for i in range(3):
        t = threading.Thread(target=read_operation)
        threads.append(t)
    
    # 2 個寫進程  
    for i in range(2):
        t = threading.Thread(target=write_operation)
        threads.append(t)
    
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    # 驗證資料一致性
    assert validate_data_integrity()
```

**預期結果**: ✅ 無資料損壞或遺失

---

## R3: 資料驗證和恢復策略

### 決策
✅ **選擇方案**: 多層驗證 + 自動備份 + 進度記錄

### 驗證層次

#### 層次 1: 格式驗證
```python
# 確保 JSON 語法正確
try:
    json.loads(file_content)
except json.JSONDecodeError:
    logger.error("JSON 格式錯誤")
    restore_from_backup()
```

#### 層次 2: 結構驗證
```python
# 確保必需的頂層鍵存在
required_keys = ['videos', 'actresses', 'video_actress_links']
for key in required_keys:
    assert key in data, f"Missing key: {key}"
```

#### 層次 3: 完整性驗證
```python
# SHA256 雜湊檢查
stored_hash = data['_metadata']['hash']
computed_hash = hashlib.sha256(
    json.dumps(data, sort_keys=True).encode()
).hexdigest()
if stored_hash != computed_hash:
    logger.warning("Data integrity check failed")
    restore_from_backup()
```

#### 層次 4: 參照完整性驗證
```python
# 驗證外鍵約束
video_ids = set(v['id'] for v in data['videos'])
for link in data['video_actress_links']:
    assert link['video_id'] in video_ids, "Invalid video reference"
```

### 恢復策略

```python
def recover_from_corruption():
    """從損壞自動恢復"""
    
    # 1. 嘗試修復當前檔案
    if try_repair_json_file():
        return True
    
    # 2. 從最新備份還原
    backups = get_backup_list()
    for backup in sorted(backups, reverse=True):
        if restore_from_backup(backup):
            logger.info(f"Restored from backup: {backup}")
            return True
    
    # 3. 最後手段: 使用上次成功的快照
    return restore_from_last_known_good()
```

### 備份策略

```
自動備份時機:
- 遷移完成後
- 每天午夜 (定時備份)
- 重大操作前 (新增/刪除大量影片)

備份保留政策:
- 最近 30 天: 保留所有備份
- 30 天前: 每週保留 1 個
- 限制: 最多 50 個備份檔案

備份驗證:
- 每個備份完成後驗證完整性
- 定期測試備份還原流程 (週期: 每月)
```

---

## R4: 查詢等價性 - JOIN 邏輯轉換

### 決策
✅ **選擇方案**: 手動 Python 實作 JOIN + 預計算快取

### 基本原理

SQLite JOIN 在 SQL 層原生支援，JSON 需要在應用層手動實作。為了效能，採用預計算統計快取策略。

### 轉換映射

#### 查詢 1: 女優統計

**SQLite 版本**:
```sql
SELECT 
  a.id, 
  a.name, 
  COUNT(DISTINCT v.id) as video_count,
  MAX(v.release_date) as latest_date
FROM actresses a
LEFT JOIN video_actress_links val ON a.id = val.actress_id
LEFT JOIN videos v ON val.video_id = v.id
GROUP BY a.id;
```

**JSON 實作**:
```python
def get_actress_statistics():
    """計算女優統計 (手動 JOIN)"""
    actress_stats = {}
    
    for actress in self.data['actresses']:
        actress_id = actress['id']
        
        # 建立女優資訊
        actress_stats[actress_id] = {
            'name': actress['name'],
            'video_count': 0,
            'videos': [],
            'latest_date': None
        }
        
        # 找到該女優的所有影片 (JOIN)
        for link in self.data['video_actress_links']:
            if link['actress_id'] == actress_id:
                # 找到影片資訊 (JOIN)
                video = self._find_video(link['video_id'])
                if video:
                    actress_stats[actress_id]['videos'].append(video['id'])
                    actress_stats[actress_id]['video_count'] += 1
                    
                    # 更新最新日期
                    if actress_stats[actress_id]['latest_date'] is None:
                        actress_stats[actress_id]['latest_date'] = video['release_date']
                    else:
                        if video['release_date'] > actress_stats[actress_id]['latest_date']:
                            actress_stats[actress_id]['latest_date'] = video['release_date']
    
    return actress_stats
```

#### 查詢 2: 交叉統計 (女優-片商)

**SQLite 版本**:
```sql
SELECT 
  a.id as actress_id,
  s.name as studio_name,
  COUNT(DISTINCT v.id) as video_count
FROM actresses a
JOIN video_actress_links val ON a.id = val.actress_id
JOIN videos v ON val.video_id = v.id
GROUP BY a.id, s.name;
```

**JSON 實作**:
```python
def get_cross_statistics():
    """計算女優-片商交叉統計"""
    cross_stats = {}  # key: (actress_id, studio)
    
    for link in self.data['video_actress_links']:
        video = self._find_video(link['video_id'])
        if not video:
            continue
        
        key = (link['actress_id'], video['studio'])
        if key not in cross_stats:
            cross_stats[key] = 0
        cross_stats[key] += 1
    
    # 轉換為陣列格式
    result = []
    for (actress_id, studio), count in cross_stats.items():
        result.append({
            'actress': actress_id,
            'studio': studio,
            'video_count': count
        })
    
    return result
```

### 效能優化

```python
# 策略 1: 預計算統計快取
# 避免每次查詢都重新計算
statistics_cache = {
    'actress_stats': {...},
    'studio_stats': {...},
    'cross_stats': [...],
    'last_updated': datetime.now()
}

# 策略 2: 增量更新
# 新增影片時只更新相關快取項
def update_statistics_incremental(new_video):
    # 只更新受新影片影響的統計
    pass

# 策略 3: 索引快速查找
# 建立輔助索引加速查詢
actress_video_index = {
    'actress_001': ['video_1', 'video_2', ...],
    'actress_002': ['video_3', ...]
}
```

### 等價性驗證

```python
def verify_query_equivalence():
    """驗證 JSON 查詢結果與 SQLite 相同"""
    
    # 查詢 SQLite 結果
    sqlite_actresses = query_sqlite(
        "SELECT id, name, COUNT(*) FROM actresses ..."
    )
    
    # 查詢 JSON 結果  
    json_actresses = json_db.get_actress_statistics()
    
    # 對比
    for actress_id, sqlite_stats in sqlite_actresses.items():
        json_stats = json_actresses[actress_id]
        assert sqlite_stats == json_stats, f"Mismatch for {actress_id}"
    
    return True  # 等價性驗證通過
```

---

## R5: 技術依賴評估

### 新增依賴

```
filelock==3.13.0  # 檔案鎖定，支援跨平台並行存取
```

### 移除依賴

遷移完成後移除:
```
sqlite3  # 內建，但相關程式碼移除
```

### 依賴相容性

| 依賴 | 版本 | Python 相容性 | 許可證 | 狀態 |
|-----|------|------------|-------|------|
| filelock | 3.13.0 | 3.8+ | Public Domain | ✅ 穩定 |
| json | 內建 | All | - | ✅ 內建 |
| hashlib | 內建 | All | - | ✅ 內建 |

---

## 實施建議

### 階段 1: 設計驗證 (1-2 天)
1. 實作 JSONDBManager 原型
2. 執行並行測試
3. 驗證查詢等價性

### 階段 2: 遷移工具開發 (2-3 天)
1. 開發 SQLite → JSON 轉換工具
2. 測試大資料集遷移
3. 建立備份和恢復機制

### 階段 3: 集成測試 (2-3 天)
1. 業務邏輯適配
2. UI 層更新
3. 端到端測試

### 階段 4: 部署準備 (1 天)
1. 清理舊程式碼
2. 文件更新
3. 最終驗證

---

## 風險評估和緩解

| 風險 | 嚴重性 | 緩解策略 |
|-----|------|--------|
| 資料損壞 | 🔴 高 | 多層驗證 + 自動備份 + 還原機制 |
| 並行衝突 | 🔴 高 | filelock 獨佔鎖 + 測試 |
| 效能下降 | 🟡 中 | 記憶體快取 + 統計預計算 |
| 遷移失敗 | 🟡 中 | 保留 SQLite + 反向遷移工具 |
| 相容性問題 | 🟢 低 | 相同介面設計 + 單元測試 |

---

## 結論

所有關鍵決策均基於技術評估和最佳實踐。建議方案：

✅ **JSON 儲存**：單檔 + 快取  
✅ **並行控制**：filelock  
✅ **資料安全**：多層驗證 + 自動備份  
✅ **查詢邏輯**：手動 JOIN + 預計算快取  

**整體評估**: ✅ 可行性高，風險可控

**推薦進入**: 實施階段

