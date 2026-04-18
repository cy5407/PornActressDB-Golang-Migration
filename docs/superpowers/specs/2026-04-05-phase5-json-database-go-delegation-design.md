# Phase 5: JSONDBManager Go 完整委派設計

**日期**: 2026-04-05  
**狀態**: 已核准，待實作  
**目標模組**: `src/models/json_database.py` (JSONDBManager, 1569 行)

---

## 背景

### 現有架構

```
應用程式
├── classifier_core.py
│   ├── [主路徑] IncrementalJSONDB  ← Phase 4B-1 (workflow 執行中)
│   └── [備援路徑] JSONDBManager    ← Phase 5 目標
└── go_api/db.py
    ├── db_get_video()      ✅ 已建
    ├── db_update_video()   ✅ 已建
    ├── db_delete_video()   ✅ 已建
    ├── db_list_videos()    ✅ 已建（返回 code 陣列）
    ├── db_get_stats()      ✅ 已建
    └── db_compact_journal() ✅ 已建
```

### 問題

`JSONDBManager` 目前所有操作純用 Python（orjson + filelock），沒有委派 Go。每次 `add_or_update_video()` 都需要讀取整個 JSON 檔案並重寫。Go 的等效操作（`db update`）速度快 ~1300x。

### 目標

讓 `JSONDBManager` 的 video CRUD 委派 Go CLI，保留 Python fallback，符合既有 Adapter Pattern。

---

## 設計

### 委派範圍

**委派 Go（高頻 / I/O 密集）**:
- `get_video_info(code)` → `db_get_video(code)`
- `add_or_update_video(video_info)` → `db_update_video(code, video_info)`
- `delete_video(code)` → `db_delete_video(code)`
- `get_all_videos()` → `db_get_all_videos()`（新建）

**保留 Python（低頻 / 複雜邏輯）**:
- `get_actress_statistics()`, `get_studio_statistics()` — 聚合計算
- `get_enhanced_actress_studio_statistics()` — 複雜分析
- `analyze_actress_primary_studio()` — 分析邏輯
- `create_backup()`, `restore_from_backup()`, `get_backup_list()`, `cleanup_old_backups()` — 低頻
- `validate_data()` — 診斷用途
- `add_or_update_actress()`, `get_actress_info()`, `delete_actress()` — 女優 CRUD（頻率較低，暫保留）

---

## 任務拆分

### Task 5-1：Go CLI 補 `db list --full`

**檔案**: `cmd/scanner/db_cmd.go`

在現有 `case "list":` 區塊擴充，支援 `--full` flag：

```go
// 現有: db list → 返回 []string (code 陣列)
// 新增: db list --full → 返回 []VideoDict (完整影片物件陣列)

fullOutput := fs.Bool("full", false, "返回完整影片物件")
// ...
if *fullOutput {
    videos, err := db.GetAllVideos()
    outputJSON(videos)
} else {
    codes, err := db.ListVideoCodes()
    outputJSON(codes)
}
```

Go `pkg/database` 需要確認 `GetAllVideos()` 方法存在（或新增）。

**CLI 呼叫範例**:
```bash
classifier.exe db list --full -data-dir data/json_db
# 輸出: [{"code":"STARS-001","title":"..."},...]
```

### Task 5-2：`go_api/db.py` 新增 `db_get_all_videos()`

**檔案**: `src/services/go_api/db.py`

```python
def db_get_all_videos(
    data_dir: str = "data/json_db",
    *,
    runner: GoCommandRunner | None = None,
) -> list[dict]:
    """取得所有影片完整資訊。"""
    r = _get_runner(runner)
    try:
        cmd = ["db", "list", "--full"]
        if data_dir != "data/json_db":
            cmd.extend(["-data-dir", data_dir])
        result = r.run(cmd)
        data = r.parse_json(result.stdout)
        return data if isinstance(data, list) else []
    except GoBridgeError as e:
        logger.error(f"❌ Go CLI 執行失敗，取得所有影片失敗: {e}")
        return []
```

### Task 5-3：`JSONDBManager` 委派 video CRUD

**檔案**: `src/models/json_database.py`

**模組頂層加入 import guard**:
```python
try:
    from services.go_api.db import (
        db_get_video,
        db_update_video,
        db_delete_video,
        db_get_all_videos,
    )
    _GO_DB_API_OK = True
except ImportError:
    _GO_DB_API_OK = False
```

**`__init__` 加入旗標**:
```python
self._GO_DB_AVAILABLE = _GO_DB_API_OK and _check_go_available()
```

**委派方法範例（`get_video_info`）**:
```python
def get_video_info(self, code: str) -> VideoDict | None:
    if self._GO_DB_AVAILABLE:
        try:
            return db_get_video(code, data_dir=str(self.data_dir))
        except Exception as e:
            logger.warning(f"⚠️ Go DB 查詢失敗，降級 Python: {e}")
    # Python fallback（原有邏輯）
    return self._get_video_info_python(code)
```

同樣模式套用至 `add_or_update_video` 和 `delete_video`。

### Task 5-4：委派 `get_all_videos()` + 測試

**`get_all_videos()` 委派**:
```python
def get_all_videos(self, ...) -> list[VideoDict]:
    if self._GO_DB_AVAILABLE:
        try:
            videos = db_get_all_videos(data_dir=str(self.data_dir))
            # 套用 Python 側的過濾條件
            return self._apply_video_filters(videos, ...)
        except Exception as e:
            logger.warning(f"⚠️ Go DB 列表失敗，降級 Python: {e}")
    return self._get_all_videos_python(...)
```

**測試檔案**: `tests/test_json_db_go_delegation.py`
- Mock runner 測試 Go 路徑
- 整合測試：實際呼叫並比對結果
- Fallback 測試：Go 不可用時降級 Python

---

## 資料流

```
呼叫端
  │
  ▼
JSONDBManager.get_video_info(code)
  │
  ├── [_GO_DB_AVAILABLE=True] → db_get_video(code) → GoCommandRunner
  │                               → classifier.exe db get <code>
  │                               → pkg/database/JSONDatabase.GetVideo()
  │                               ← JSON stdout ← 解析 ← 返回
  │
  └── [_GO_DB_AVAILABLE=False] → _get_video_info_python(code)
                                  → filelock → orjson.load → 返回
```

---

## 錯誤處理

- Go CLI 失敗（非零 exit code）→ `GoBridgeError`
- JSON 解析失敗 → `GoBridgeError`
- 任何 Exception → warning log + Python fallback
- Fallback 成功 → 正常返回（對呼叫端透明）

---

## 測試策略

1. **單元測試（mock runner）**：
   - `_GO_DB_AVAILABLE=True` 時確認呼叫 Go 路徑
   - `_GO_DB_AVAILABLE=False` 時確認使用 Python 路徑
   - Go 失敗時確認 fallback 到 Python

2. **整合測試（實際 Go CLI）**：
   - 只在 `classifier.exe` 可用時執行（`@pytest.mark.skipif`）
   - 比對 Go 路徑與 Python 路徑結果一致

---

## 預期效益

| 操作 | Python | Go | 提升 |
|------|--------|----|------|
| `get_video_info` | ~5ms | ~64ns | **78,000x** |
| `add_or_update_video` | ~250ms | ~182μs | **1,300x** |
| `delete_video` | ~250ms | ~182μs | **1,300x** |
| `get_all_videos` (1000 筆) | ~2s | ~10ms | **200x** |

---

## 不在此設計範圍

- 女優 CRUD（`add_or_update_actress` 等）— 留待未來 Phase 6
- 統計分析方法 — 複雜 Python 邏輯，ROI 低
- 備份操作 — 低頻，不影響效能
- 爬蟲模組（avwiki / javdb）— 另行評估
