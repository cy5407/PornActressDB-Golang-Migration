---
name: database-operations
description: 增量 JSON 資料庫操作指引 - 用於新增影片記錄、批次更新、Journal 合併、資料查詢與備份還原
argument-hint: "[operation]"
---

# 資料庫操作 Skill

## 何時使用此 Skill

當需要：
1. **新增或更新影片記錄**（單筆或批次）
2. **查詢資料庫**（女優名稱、番號、片商）
3. **效能優化**（Journal 合併、索引重建）
4. **資料備份與還原**
5. **修復資料庫問題**（Journal 損壞、資料不一致）

## 核心概念

### 增量資料庫架構 (IncrementalJSONDB)

```
data/json_db/
├── data.json          # 主資料檔案（完整資料）
├── data.journal       # 增量日誌（JSON Lines 格式）
└── data.index         # Dirty keys 索引（需合併的 keys）
```

### 運作原理

1. **寫入操作** → 只寫入 Journal（超快！）
2. **讀取操作** → 合併 data.json + Journal（透明）
3. **自動合併** → Journal 超過閾值時自動執行

## 相關檔案

- `src/models/incremental_json_database.py` - 增量資料庫實作
- `src/models/json_database.py` - 標準資料庫實作
- `data/json_db/` - 資料庫檔案目錄
- `tools/check_database.py` - 資料庫檢查工具
