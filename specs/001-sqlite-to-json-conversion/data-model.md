# Data Model: SQLite 轉換為 JSON 資料庫儲存

**Feature**: 001-sqlite-to-json-conversion  
**Created**: 2025-10-16  
**Version**: 1.0

---

## 資料結構定義

### Root Level Structure

```json
{
  "schema_version": "1.0",
  "created_at": "2025-10-16T00:00:00Z",
  "last_updated": "2025-10-16T12:00:00Z",
  "_metadata": {
    "hash": "sha256_of_data",
    "record_count": 150,
    "size_bytes": 524288
  },
  "videos": [...],
  "actresses": [...],
  "video_actress_links": [...],
  "statistics": {...}
}
```

### 1. Video Entity (影片表)

#### 結構定義

```json
{
  "videos": [
    {
      "id": "abc123",
      "title": "Sample Video Title",
      "studio": "Studio Name",
      "release_date": "2023-10-15",
      "url": "https://example.com/video/abc123",
      "actresses": ["actress_id_1", "actress_id_2"],
      "search_status": "success",
      "last_search_date": "2025-10-16T08:30:00Z",
      "created_at": "2025-10-10T10:00:00Z",
      "updated_at": "2025-10-16T12:00:00Z",
      "metadata": {
        "source": "javdb",
        "confidence": 0.95,
        "tags": ["category_1", "category_2"]
      }
    }
  ]
}
```

#### 欄位定義

| 欄位 | 型別 | 必需 | 說明 | 約束 |
|------|------|------|------|------|
| id | string | ✅ | 唯一識別符 | 長度 1-50, 字英數和 - |
| title | string | ✅ | 片名 | 長度 1-500 |
| studio | string | ✅ | 片商名稱 | 長度 1-200 |
| release_date | string (ISO 8601) | ✅ | 發行日期 | 格式: YYYY-MM-DD |
| url | string (URI) | ✅ | 線上連結 | 有效 HTTP/HTTPS URL |
| actresses | string[] | ✅ | 女優 ID 清單 | 陣列，可為空 |
| search_status | string (enum) | ✅ | 搜尋狀態 | "success", "partial", "failed" |
| last_search_date | string (ISO 8601) | ✅ | 最後搜尋日期 | 格式: ISO 8601 |
| created_at | string (ISO 8601) | ✅ | 建立時間 | 自動設定 |
| updated_at | string (ISO 8601) | ✅ | 更新時間 | 自動更新 |
| metadata.source | string | ❌ | 資料來源 | "javdb", "avwiki", "other" |
| metadata.confidence | number | ❌ | 置信度 | 0.0-1.0 之間 |
| metadata.tags | string[] | ❌ | 分類標籤 | 陣列 |

#### 驗證規則

```python
# Python 驗證邏輯
{
    "id": {"type": "string", "pattern": "^[a-zA-Z0-9-]{1,50}$"},
    "title": {"type": "string", "minLength": 1, "maxLength": 500},
    "studio": {"type": "string", "minLength": 1, "maxLength": 200},
    "release_date": {"type": "string", "format": "date"},
    "url": {"type": "string", "format": "uri"},
    "actresses": {"type": "array", "items": {"type": "string"}},
    "search_status": {"enum": ["success", "partial", "failed"]},
    "metadata.confidence": {"type": "number", "minimum": 0, "maximum": 1}
}
```

### 2. Actress Entity (女優表)

#### 結構定義

```json
{
  "actresses": [
    {
      "id": "actress_001",
      "name": "女優名字",
      "aliases": ["別名1", "別名2"],
      "video_count": 42,
      "created_at": "2025-10-10T10:00:00Z",
      "updated_at": "2025-10-16T12:00:00Z"
    }
  ]
}
```

#### 欄位定義

| 欄位 | 型別 | 必需 | 說明 | 約束 |
|------|------|------|------|------|
| id | string | ✅ | 唯一識別符 | 長度 1-50 |
| name | string | ✅ | 女優名字 | 長度 1-200 |
| aliases | string[] | ❌ | 別名清單 | 可為空陣列 |
| video_count | integer | ✅ | 出演部數 (快取) | ≥0 |
| created_at | string (ISO 8601) | ✅ | 建立時間 | 自動設定 |
| updated_at | string (ISO 8601) | ✅ | 更新時間 | 自動更新 |

#### 驗證規則

```python
{
    "id": {"type": "string", "minLength": 1, "maxLength": 50},
    "name": {"type": "string", "minLength": 1, "maxLength": 200},
    "aliases": {"type": "array", "items": {"type": "string"}},
    "video_count": {"type": "integer", "minimum": 0}
}
```

### 3. VideoActressLink Entity (關聯表)

#### 結構定義

```json
{
  "video_actress_links": [
    {
      "video_id": "abc123",
      "actress_id": "actress_001",
      "role_type": "lead",
      "created_at": "2025-10-10T10:00:00Z"
    }
  ]
}
```

#### 欄位定義

| 欄位 | 型別 | 必需 | 說明 | 約束 |
|------|------|------|------|------|
| video_id | string | ✅ | 影片 ID | 必須存在於 videos 表 |
| actress_id | string | ✅ | 女優 ID | 必須存在於 actresses 表 |
| role_type | string (enum) | ❌ | 角色類型 | "lead", "supporting", "guest" |
| created_at | string (ISO 8601) | ✅ | 建立時間 | 自動設定 |

#### 驗證規則

```python
{
    "video_id": {"type": "string", "minLength": 1},
    "actress_id": {"type": "string", "minLength": 1},
    "role_type": {"enum": ["lead", "supporting", "guest"]}
}
```

**完整性約束**:
- `video_id` 必須存在於 videos 陣列
- `actress_id` 必須存在於 actresses 陣列
- 複合唯一鍵: (video_id, actress_id)

### 4. Statistics Entity (統計快取)

#### 結構定義

```json
{
  "statistics": {
    "actress_stats": {
      "actress_001": {
        "name": "女優名字",
        "video_count": 42,
        "studios": ["studio1", "studio2"],
        "date_range": {
          "start": "2020-01-01",
          "end": "2025-10-16"
        }
      }
    },
    "studio_stats": {
      "Studio Name": {
        "video_count": 150,
        "actresses": ["actress_001", "actress_002"],
        "date_range": {
          "start": "2020-01-01",
          "end": "2025-10-16"
        }
      }
    },
    "cross_stats": [
      {
        "actress": "actress_001",
        "studio": "Studio Name",
        "video_count": 15
      }
    ],
    "last_updated": "2025-10-16T12:00:00Z"
  }
}
```

#### 使用場景

**場景 1: 女優統計**
- 快速查詢女優出演部數
- 無需遍歷關聯表

**場景 2: 片商統計**
- 快速查詢片商影片數
- 支援篩選日期範圍

**場景 3: 交叉統計**
- 快速查詢女優-片商組合
- 支援推薦系統

#### 更新策略

```python
# 更新時機
- 新增影片時
- 刪除影片時
- 批次操作後

# 更新方式
def update_statistics():
    # 1. 清空舊快取
    # 2. 重新計算所有統計
    # 3. 更新 last_updated
    # 4. 原子寫入到 JSON
```

---

## 資料遷移映射

### SQLite → JSON 字段映射

```
SQLite videos 表              →  JSON videos 陣列
id (VARCHAR)                 →  id (string)
title (VARCHAR)              →  title (string)
studio (VARCHAR)             →  studio (string)
release_date (DATE)          →  release_date (string, ISO 8601)
url (VARCHAR)                →  url (string)
search_status (VARCHAR)      →  search_status (string)
last_search_date (TIMESTAMP) →  last_search_date (string, ISO 8601)
created_at (TIMESTAMP)       →  created_at (string, ISO 8601)
updated_at (TIMESTAMP)       →  updated_at (string, ISO 8601)
```

### 日期時間轉換

```python
# SQLite TIMESTAMP 格式
"2025-10-16 12:34:56"

# 轉換為 ISO 8601
"2025-10-16T12:34:56Z"

# Python 實作
from datetime import datetime
dt = datetime.strptime(sqlite_value, "%Y-%m-%d %H:%M:%S")
iso_value = dt.isoformat() + "Z"
```

---

## 查詢模式轉換

### 模式 1: 簡單篩選

**SQLite**:
```sql
SELECT * FROM videos WHERE studio = '片商名' ORDER BY release_date DESC;
```

**JSON 實作**:
```python
results = [v for v in data['videos'] 
           if v['studio'] == '片商名']
results.sort(key=lambda x: x['release_date'], reverse=True)
```

### 模式 2: JOIN 查詢 (女優統計)

**SQLite**:
```sql
SELECT a.name, COUNT(DISTINCT v.id) as video_count
FROM actresses a
LEFT JOIN video_actress_links val ON a.id = val.actress_id
LEFT JOIN videos v ON val.video_id = v.id
GROUP BY a.id;
```

**JSON 實作**:
```python
actress_stats = {}
for actress in data['actresses']:
    video_ids = set()
    for link in data['video_actress_links']:
        if link['actress_id'] == actress['id']:
            video_ids.add(link['video_id'])
    actress_stats[actress['id']] = {
        'name': actress['name'],
        'video_count': len(video_ids)
    }
```

### 模式 3: 複雜聚合 (交叉統計)

**SQLite**:
```sql
SELECT a.id, s.name, COUNT(DISTINCT v.id) as video_count
FROM actresses a
JOIN video_actress_links val ON a.id = val.actress_id
JOIN videos v ON val.video_id = v.id
JOIN studios s ON v.studio = s.name
GROUP BY a.id, s.name;
```

**JSON 實作**:
```python
cross_stats = []
for link in data['video_actress_links']:
    video = next((v for v in data['videos'] 
                 if v['id'] == link['video_id']), None)
    if video:
        entry = {
            'actress': link['actress_id'],
            'studio': video['studio'],
            'video_count': 1  # 遍歷時累加
        }
        # 合併重複項
```

---

## 資料驗證

### 驗證層次

#### 層次 1: JSON 格式驗證
```python
def validate_json_format(data):
    """確保是有效的 JSON 結構"""
    try:
        assert isinstance(data, dict)
        assert 'videos' in data
        assert 'actresses' in data
        assert 'video_actress_links' in data
        return True
    except AssertionError:
        return False
```

#### 層次 2: 欄位驗證
```python
def validate_video_fields(video):
    """驗證每個 Video 的欄位"""
    required = ['id', 'title', 'studio', 'release_date', 'url']
    for field in required:
        if field not in video:
            raise ValueError(f"Missing required field: {field}")
    
    # 型別檢查
    assert isinstance(video['id'], str)
    assert isinstance(video['actresses'], list)
```

#### 層次 3: 完整性驗證
```python
def validate_referential_integrity(data):
    """驗證外鍵約束"""
    video_ids = set(v['id'] for v in data['videos'])
    actress_ids = set(a['id'] for a in data['actresses'])
    
    for link in data['video_actress_links']:
        assert link['video_id'] in video_ids
        assert link['actress_id'] in actress_ids
```

#### 層次 4: 一致性驗證
```python
def validate_consistency(data):
    """驗證統計快取的一致性"""
    # 重新計算統計
    computed_stats = calculate_statistics(data)
    stored_stats = data.get('statistics', {})
    
    # 對比結果
    if computed_stats != stored_stats:
        logger.warning("Statistics mismatch - recomputing...")
```

---

## 備份和恢復

### 備份格式

```
backup/
├── actress_data.2025-10-16-12-00-00.backup  # 時間戳備份
├── actress_data.2025-10-15-12-00-00.backup  # 前一天備份
└── BACKUP_MANIFEST.json                      # 備份清單
```

### BACKUP_MANIFEST 結構

```json
{
  "backups": [
    {
      "filename": "actress_data.2025-10-16-12-00-00.backup",
      "created_at": "2025-10-16T12:00:00Z",
      "record_count": 150,
      "hash": "sha256_hash_of_backup"
    }
  ],
  "retention_days": 30,
  "max_backups": 10
}
```

### 恢復程序

```python
def restore_from_backup(backup_path):
    """從備份還原資料"""
    # 1. 驗證備份檔案存在
    # 2. 驗證備份完整性 (雜湊檢查)
    # 3. 載入備份資料
    # 4. 驗證資料結構
    # 5. 覆蓋現有資料
    # 6. 更新 updated_at
```

---

## 版本控制

### Schema 版本

```
版本 1.0 (初始版本)
├─ videos 表: 基本欄位 + search_status 追蹤
├─ actresses 表: 名字 + 別名
├─ video_actress_links: 多對多關聯
└─ statistics: 快取統計
```

### 遷移策略

若未來需要新增欄位:
```python
def migrate_schema(data, from_version, to_version):
    """遷移資料 schema"""
    if from_version == "1.0" and to_version == "1.1":
        # 新增欄位和預設值
        for video in data['videos']:
            video['new_field'] = default_value
```

