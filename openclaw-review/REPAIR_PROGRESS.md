# 自動修復進度追蹤

建立時間：2026-03-21 19:17 Asia/Taipei

## 修復項目清單（依優先順序）

### 高優先 P0

- [DONE] FIX-1: `pkg/cache/cache.go` — saveIndex() 改為 tmp+rename 原子寫入
- [DONE] FIX-2: `src/services/go_bridge.py` — db_* 函式將 -data-dir 移到 positional arg 前面
- [DONE] FIX-3: `pkg/mover/mover.go` — Overwrite 分支改為 tmp+rename，rollback 補強回報
- [DONE] FIX-4: `pkg/database/journal.go` + `pkg/database/jsondb.go` — 統一 UpdateVideo journal 語義與 replay，修正 DeleteVideo dirty tracking
- [DONE] FIX-5: `src/models/go_accelerated_db.py` — Go CRUD 成功後重建 IncrementalJSONDB 而非手動 patch dict

### 中優先 P1

- [DONE] FIX-6: `src/models/extractor.py` — 刪除重複的 _should_skip_file()，接入 skip_prefixes 實際使用
- [DONE] FIX-7: `src/models/json_types.py` + `src/services/classifier_core.py` — 同步 statistics key 名稱，改讀 config 路徑而非硬寫 data/json_db

### 低優先 P2

- [DONE] FIX-8: `src/services/go_bridge.py` — 改善錯誤分類（業務失敗 vs bridge 故障 vs 解析失敗），僅在 P0+P1 全完成後才做

---

REPAIR_COMPLETE
完成時間：2026-03-21 21:35 Asia/Taipei
