# OPENCLAW_AUDIT_2026-04-06

## 審閱摘要

本次審閱整合前 3 個任務的結果，結論是：**Go 端核心能力大致已完整接手，Python 端仍保留少量過渡薄層與歷史殘留，但已明顯朝 Go 單一真相來源收斂**。

已確認的部分：
- Go 端的資料庫、快取、抽碼、片商識別、搬移與 CLI 路徑都已存在，且對應單元測試也有覆蓋。
- 多數核心修正已通過前面任務檢查，包含 cache 原子寫入、mover overwrite/rollback、journal 語義一致、Go/Python 狀態同步、extractor skip 邏輯、config 路徑接線與 Python 3.10 相容性修復。
- 架構方向已明確：核心邏輯應往 Go 收斂，Python 保留 GUI、相容薄層與必要橋接，不應再維持兩套核心語意。

缺失與限制：
- **本次沒有重新執行完整 Go/Python 自動化測試或 CLI e2e 驗證**，因此「函式存在與程式碼結構完整」可以確認，但「端到端實際執行結果」仍屬未完全驗證。
- 目前可確認的是單元測試與人工讀碼層面的完整性；若要證實 `db/cache/identify/move` CLI 在真實環境中的整合打通，仍需要額外 e2e 或實機驗證。
- Python 端仍有若干方法在 Go 失敗時直接回傳 `None` / `[]` / `False` 或直接失敗，這些不應被誤解成真正的本機 fallback。

整體判斷：
- **核心功能：通過**
- **架構收斂：進行中，方向正確**
- **端到端完整性：尚有驗證缺口**

---

## 逐檔審閱

### 1) `src/models/json_database.py`

已確認：
- `Load/Save/GetVideo/UpdateVideo/UpdateVideoFields/AddVideo/DeleteVideo/ListVideos/GetAllVideos/GetVideoCount/BatchUpdate/CompactJournal/Compact/CompactIfNeeded/NeedsCompact/GetStats/GetStatsStruct/GetDeletedCodes/GetActress/UpsertActress/DeleteActress/ListActresses/MergeFromFile/GetActressStats/BackupCreate/BackupRestore/BackupList/BackupCleanup/GetStudioStats` 等核心入口都存在或已對齊 Go 端設計。
- `_validate_*`、`_normalize_*`、鎖定管理與 `__enter__/__exit__` 等內部 helper 屬合理保留。

缺失 / 疑慮：
- 多個統計與資料完整性相關方法已變成 Go-only 入口，Python 側沒有明確的本機計算回退。
- 這代表 Python 已不再是完整的業務來源，而是過渡層；若 Go bridge 出現問題，功能可能直接失效。
- `get_actress_statistics()`、`get_studio_statistics()`、`get_enhanced_actress_studio_statistics()` 的可用性高度依賴 Go。

結論：
- **確認**：核心結構存在，Go 優先路徑清楚。
- **缺失**：Python 本機 fallback 不完整。
- **疑慮**：統計與驗證邏輯長期維持雙份的風險仍在。

### 2) `src/models/incremental_json_database.py`

已確認：
- 名義上保留增量管理器角色，但實際上多數核心操作已往 Go 收斂。
- `add_video()/delete_video()` 是 journal 寫入後同步 base_db 的歷史路徑，`update_video()` 仍明顯依賴 Go。

缺失 / 疑慮：
- 這個模組在語意上仍像「完整資料層」，但實際上已接近過渡相容層。
- 若未來沒有明確清理策略，journal 與同步邏輯會持續殘留雙份維護成本。

結論：
- **確認**：增量 journal 行為存在。
- **缺失**：核心路徑仍不完全獨立於 Go。
- **疑慮**：長期應定位為過渡層，而不是第二套核心資料來源。

### 3) `src/scrapers/cache_manager.py`

已確認：
- `set/get/delete` 幾乎完全依賴 Go。
- serialization / deserialization / index 維護等 helper 還留在 Python，是合理的薄層功能。

缺失 / 疑慮：
- Go 不可用時的可用性有限，並非完整本機替代。
- 若橋接失敗，快取功能可能整體退化。

結論：
- **確認**：Go-first 已落實。
- **缺失**：本機 fallback 極弱。
- **疑慮**：這是薄層，不應再擴充成第二套核心快取實作。

### 4) `src/services/go_bridge.py`

已確認：
- Python 端的 bridge 仍是主要入口，負責把 CLI 行為包裝成 Python API。
- 前面任務已指出 `db_*` flags-first 傳遞與錯誤分類改善的方向是對的。

缺失 / 疑慮：
- bridge 的定位偏向「直接暴露 Go CLI」，本身沒有太多策略層。
- 錯誤語意仍可能混雜：業務失敗、CLI 執行失敗、JSON 解析失敗，未必總能清楚區分。
- 這使得上層 fallback 判斷容易產生誤判。

結論：
- **確認**：Go CLI 對接骨架完整。
- **缺失**：錯誤分層仍可再細化。
- **疑慮**：bridge 不能被當成真正的業務實作層。

### 5) `src/models/go_accelerated_db.py`

已確認：
- Go CRUD 成功後會重建 `_python_db`，這是目前最穩妥的狀態同步策略。
- 這比手工 patch Python dict 更接近單一真相來源。

缺失 / 疑慮：
- 這種「成功後整個重建」對批次更新的效能不佳，但功能上是正確的。
- 若 Go bridge 失敗，fallback 邏輯仍需非常小心區分「不存在」與「執行失敗」。

結論：
- **確認**：狀態同步策略正確。
- **缺失**：效能不是最佳，但可接受。
- **疑慮**：fallback 語意若不清楚，會影響可靠性判讀。

### 6) `src/models/studio.py`

已確認：
- 片商識別的 Python 路徑仍存在，但整體已朝 Go 端識別器收斂。
- 自訂規則檔、本機前綴查詢屬合理保留。

缺失 / 疑慮：
- 若 Go 端識別資料不完整，Python 的相容價值才會被測出；目前尚未看到明確的雙向一致性驗證報告。

結論：
- **確認**：本機查詢與規則保留合理。
- **缺失**：雙向一致性缺少 e2e 證據。

### 7) `src/utils/scanner.py`

已確認：
- UnifiedFileScanner 已能走 Go CLI 加速路線。
- 核心設計方向符合「Go 為主、Python 為薄層」。

缺失 / 疑慮：
- 若 Go CLI 不可用，降級路徑未必能保有完全相同行為。

結論：
- **確認**：掃描流程已收斂。
- **缺失**：完整 fallback 行為未完全證實。

### 8) `src/utils/file_mover.py`

已確認：
- FileMover 已與 Go 批次移動與回滾路徑對齊。
- Python 端主要扮演協調層。

缺失 / 疑慮：
- 仍需特別注意 rename / rollback 情境的邊界條件，尤其是不同策略之間的路徑對應。

結論：
- **確認**：核心搬移能力已交給 Go。
- **缺失**：極端案例仍是風險點。

### 9) `pkg/database/jsondb.go`

已確認：
- Go 端核心 CRUD、backup、merge、compact、actress/studio stats 等能力齊備。
- `json.MarshalIndent` 與 CLI JSON 輸出路徑存在。
- journal 寫入與 replay 語義已對齊。

缺失 / 疑慮：
- 雖然主體完整，但目前這份審閱沒有重新執行整套 Go test 或 CLI e2e。
- `MergeFromFile`、`DeleteVideo`、`BatchUpdate` 等之前已被關注的細節，前面任務已確認大致正常，但仍屬「程式碼層驗證」而不是「實跑驗證」。

結論：
- **確認**：Go 端資料庫主體完整。
- **缺失**：e2e 證據不足。
- **疑慮**：部分欄位/舊格式兼容雖可讀出，但實環境仍需驗證。

### 10) `pkg/cache/cache.go`

已確認：
- `GetStats/CleanupExpired/CleanupBySize/ClearAll/AutoCleanup/Set/Get/Delete/Exists` 都存在。
- index 讀寫、TTL/LRU 清理與乾跑模式均已實作。
- 前面任務已確認 saveIndex 原子寫入與呼叫點錯誤傳播正常。

缺失 / 疑慮：
- 本次沒有重新跑 cache integration test，只能依前次審閱結論確認設計完整。

結論：
- **確認**：快取核心完整。
- **缺失**：執行證據未重跑。

### 11) `pkg/extractor/extractor.go`

已確認：
- `NewCodeExtractor()`、`ExtractCode()` 存在。
- skip / normalize / validate 流程在同檔內完成。
- 單元測試覆蓋主要案例。

缺失 / 疑慮：
- 仍需注意 FC2/PPV 跳過規則是否會誤傷少數合法番號命名。

結論：
- **確認**：抽碼流程完整。
- **疑慮**：skip 規則仍是設計取捨。

### 12) `pkg/studio/identifier.go`

已確認：
- `NewStudioIdentifier/loadRules/loadMajorStudios/buildCodeToStudioMap/IdentifyStudio/NormalizeStudioName/IsMajorStudio/GetAllStudios/GetPrefixes` 都存在。
- 測試有涵蓋識別、別名、大片商、規則檔載入與反向 map。

缺失 / 疑慮：
- CLI 整合測試證據仍不足，只能確認函式與單元測試。

結論：
- **確認**：片商識別核心完整。
- **缺失**：CLI e2e 未證實。

### 13) `pkg/mover/*.go`

已確認：
- `MoveFile/MoveDir/BatchMove/Rollback/ListOperations` 與日誌/回滾支援都存在。
- 前面任務已確認 overwrite 安全替換與 rollback 狀態追蹤修正方向正確。

缺失 / 疑慮：
- `Rollback` 與 rename / renamed path 的對應是歷史上較敏感的點，應持續保留測試。

結論：
- **確認**：搬移與回滾主體完整。
- **疑慮**：路徑對應細節仍需小心。

---

## Go 端完整性確認

已確認的 Go 端能力：
- `pkg/database/jsondb.go`：核心 CRUD、journal、backup、merge、compact、stats、actress/studio 管理。
- `cmd/scanner/db_cmd.go`：`get/update/delete/list/stats/compact/merge/actress-* / backup-* / fix-studios` 等子命令齊備。
- `cmd/scanner/cache_cmd.go`：`stats/prune/clear/get/set/delete` 齊備。
- `cmd/scanner/identify_cmd.go`：`-batch/-rules/-prefixes/-list/-major/-json` 齊備。
- `cmd/scanner/main.go`：`db/cache/identify/scan/move/history/help` 主路由已接起來。
- `pkg/extractor/extractor.go`、`pkg/cache/cache.go`、`pkg/studio/identifier.go`、`pkg/mover/*.go`：核心功能均存在，且有對應測試。

完整性判斷：
- **結構完整：是**
- **單元測試存在：是**
- **CLI/e2e 完整驗證：未完全確認**

因此，Go 端可以判定為「**功能面完整、落地面大致成立，但尚缺最終端到端證據**」。

---

## 下一階段建議（Phase 9+）

### 1. 先把「核心真相來源」寫死
- 既然 Go 已是主路徑，下一階段不要再新增 Python 與 Go 的雙份業務邏輯。
- Python 只保留：GUI、設定、薄層相容、橋接與必要例外處理。
- 所有核心資料驗證、journal 語義、統計聚合、快取策略，原則上都應以 Go 為唯一實作。

### 2. 補一輪真正的 e2e 驗證
- 需要補的不是「函式存在」的證據，而是：
  - `db` CLI 可用
  - `cache` CLI 可用
  - `identify` CLI 可用
  - `move` CLI 可用
  - Python bridge 能正常呼叫並拿到預期回傳
- 最好補一份明確的整合測試腳本或 CI job。

### 3. 清理 Python 的過渡殘留
- `incremental_json_database.py` 應被正式定位成過渡層。
- `go_bridge.py` 的錯誤分類應再更清楚，避免把業務失敗誤判為系統故障。
- 對於已經 Go-only 的統計與 CRUD 路徑，不要再新增 Python 邏輯分支。

### 4. 針對 fallback 語意做一次收斂
- 要明確區分：
  - 資料不存在
  - Go CLI 執行失敗
  - JSON 解析失敗
  - 參數錯誤
- 否則上層會把「真實不存在」誤當成「系統壞掉」，或反過來。

### 5. 若要繼續 Phase 9+
- 優先順序建議：
  1. e2e 驗證
  2. 低風險殘留清理
  3. 文件/測試對齊
  4. 再考慮移除更多 Python 歷史實作

---

## 程式碼品質問題

以下為本次整體審閱保留下來的品質問題與風險，不做美化：

- **雙語意風險仍存在**：Python 與 Go 之間仍保留部分相似概念，若未持續收斂，之後會變成雙邊維護成本。
- **fallback 語意不夠銳利**：目前不少 Python 包裝層只能看見 `None` / `[]` / `False`，不容易區分真正業務結果與執行失敗。
- **e2e 驗證不足**：目前多數結論來自讀碼與單元測試；真正的 CLI 打通與 Python bridge 實跑，仍缺最後一層證據。
- **過渡層可能膨脹**：`incremental_json_database.py`、`go_bridge.py`、部分 `utils` 與 `services` 都有變成「薄層不夠薄、核心又不完全是核心」的傾向。
- **部分設計是正確但偏重**：例如 Go CRUD 後重建 Python DB，功能上正確，但批次操作時成本偏高。
- **少數測試與路徑對應仍是敏感點**：mover rollback、rename path、merge 舊欄位兼容、stats/backup 的一致性，都屬持續觀察項。

---

## 最終結論

**整體審閱結論：通過，但不是「完全收尾」狀態。**

- **已確認**：核心 Go 能力完整，前面任務指出的主要問題大多已收斂。
- **缺失**：本次沒有重新跑完整 e2e，因此最終打通證據仍不足。
- **疑慮**：Python 與 Go 的雙層語意仍需持續清理，否則未來會再次長出維護債。

如果要一句話總結：
**這個 migration 已經從「能不能做」進入「要不要把殘留整理乾淨」的階段了。**
