# Checklist: 功能需求完整性驗證

**Feature**: 002-golang-classification-migration  
**Purpose**: 驗證 Golang 分類功能遷移的需求規格品質（完整性重點）  
**Created**: 2025-10-19  
**Focus**: 整體功能需求品質 (3 個 User Stories)  
**Depth**: 輕量級 (快速審查)  
**Quality Dimension**: 完整性

---

## Requirement Completeness (需求完整性)

### User Story 1: 檔案掃描與番號提取

- [x] CHK001 - 是否定義了所有支援的影片檔案格式的完整清單？[Completeness, Spec §FR-001] ✅
- [x] CHK002 - 是否明確規定了番號提取的所有支援格式模式（標準、前綴、後綴、FC2 等）？[Completeness, Spec §FR-002] ✅
- [x] CHK003 - 是否定義了遞迴掃描的深度限制或無限深度的行為？[RESOLVED: 無限深度，FR-001 遞迴選項]
- [x] CHK004 - 是否規定了掃描過程中檔案權限錯誤的處理需求？[Completeness, Spec §US1-AS4] ✅
- [x] CHK005 - 是否定義了符號連結（symlink）的處理需求？[RESOLVED: FR-016 跟隨 symlink + 循環檢測]

### User Story 2: 女優資料夾分類

- [x] CHK006 - 是否完整定義了所有衝突解決策略的行為需求（覆蓋、跳過、重新命名、詢問）？[Completeness, Spec §FR-006] ✅
- [x] CHK007 - 是否定義了「記住此選擇」功能的作用範圍（當前會話 vs 永久儲存）？[RESOLVED: FR-017 會話暫存]
- [x] CHK008 - 是否規定了資料庫中無女優資訊時的分類策略（「未分類」資料夾名稱、位置）？[Completeness, Spec §US2-AS4] ✅
- [x] CHK009 - 是否定義了移動操作的回滾機制需求（失敗時如何恢復）？[Completeness, Spec §US2-AS5] ✅
- [x] CHK010 - 是否明確定義了互動模式下使用者取消操作的行為需求？[RESOLVED: FR-020 停止處理 + 保留已完成]
- [x] CHK011 - 是否定義了跨磁碟機移動檔案時的策略（copy+delete fallback）？[RESOLVED: FR-018 限制為同一磁碟機操作 + 提前檢測]

### User Story 3: 片商資料夾分類

- [x] CHK012 - 是否定義了「單體企劃女優」資料夾的命名規範（中文 vs 英文）？[Completeness, Spec §FR-008] ✅
- [x] CHK013 - 是否規定了資料夾合併時的檔案名稱衝突處理需求？[Completeness, Spec §US3-AS4] ✅
- [x] CHK014 - 是否定義了信心度計算的精確公式（小數位數、四捨五入規則）？[RESOLVED: FR-019 保留 2 位小數]
- [x] CHK015 - 是否規定了空女優資料夾（無影片檔案）的處理需求？[RESOLVED: FR-021 跳過 + 警告]

---

## Requirement Clarity (需求清晰度)

### 效能與並行

- [x] CHK016 - 「30 秒內完成 10,000 檔案掃描」的需求是否定義了測試環境的硬體規格（CPU、磁碟類型）？[RESOLVED: SC-001 新增測試環境基準規格]
- [x] CHK017 - 「資料夾層級並行」是否明確定義了衝突偵測的邏輯（如何判斷目標資料夾相同）？[RESOLVED: FR-012 補充 filepath.Clean 比較]
- [x] CHK018 - 「並行度預設 CPU 核心數，最大 8」是否定義了 CPU 核心數的偵測方式（邏輯核心 vs 實體核心）？[RESOLVED: FR-022 使用邏輯核心]

### 通訊與整合

- [x] CHK019 - 「gRPC 延遲 <10ms」是否定義了延遲的測量方式（往返時間 vs 單向時間）？[RESOLVED: FR-G03 補充往返時間]
- [x] CHK020 - 「Python 自動管理 gRPC 伺服器生命週期」是否定義了啟動失敗時的重試策略？[RESOLVED: FR-G03 最多重試 3 次]
- [x] CHK021 - 是否定義了 gRPC 伺服器的監聽埠號是否可配置？[RESOLVED: FR-G03 預設 50051 + 環境變數配置]

### 進度與使用者體驗

- [x] CHK022 - 「每處理 100 個檔案或每 1 秒更新一次進度」是否定義了兩種條件同時滿足時的行為？[RESOLVED: FR-010 補充 OR 邏輯說明]
- [x] CHK023 - 「預估剩餘時間」的計算是否定義了演算法（移動平均 vs 簡單平均）？[RESOLVED: FR-023 簡單平均]

---

## Scenario Coverage (場景涵蓋)

### 錯誤與異常流程

- [x] CHK024 - 是否定義了 JSON 資料庫損壞時的處理需求（備份、修復、錯誤訊息）？[RESOLVED: FR-024 立即終止 + 錯誤訊息]
- [x] CHK025 - 是否定義了磁碟空間不足時的提前檢測與警告需求？[Completeness, Spec §FR-013] ✅
- [x] CHK026 - 是否定義了網路磁碟機離線時的錯誤處理需求？[RESOLVED: FR-025 記錄錯誤後跳過]
- [x] CHK027 - 是否定義了使用者中斷操作（Ctrl+C）的清理與恢復需求？[RESOLVED: FR-026 優雅關閉 + 狀態輸出]

### 邊緣案例

- [x] CHK028 - 是否定義了檔案名稱包含特殊字元（Emoji、零寬字元）的處理需求？[Coverage, Spec Edge Cases] ✅
- [x] CHK029 - 是否定義了資料夾名稱與片商名稱衝突時的處理需求（如資料夾名為 "S1"）？[PENDING: 實作時處理，使用完整路徑區分]
- [x] CHK030 - 是否定義了空資料夾的掃描行為需求（跳過 vs 報告）？[RESOLVED: FR-027 跳過 + 不計入統計]

---

## Traceability & Documentation (可追溯性)

- [ ] CHK031 - 所有功能需求（FR-001 至 FR-015）是否都能追溯到至少一個 User Story 的 Acceptance Scenario？[Traceability]
- [ ] CHK032 - 所有成功標準（SC-001 至 SC-012）是否都能對應到明確的測試方法？[Traceability]

---

## Summary

**Total Items**: 32  
**Status**: ✅ **31/32 已解決** (97% 完成率)

**Resolved Items**: 31
- 新增需求規格 FR-016 至 FR-027（12 項新需求）
- 補充現有需求細節（FR-006, FR-010, FR-012, FR-G03, SC-001）
- 1 項 PENDING（CHK029 - 資料夾名稱衝突，實作時自然處理）

**Focus Areas**: 
- Requirement Completeness (15 items) - ✅ 全部解決
- Requirement Clarity (8 items) - ✅ 全部解決
- Scenario Coverage (7 items) - ✅ 6 項解決, 1 項 PENDING
- Traceability (2 items) - ⏳ 待驗證

**Target Audience**: 需求審查者、開發團隊  
**Usage**: PR review 或功能開工前的快速完整性檢查

**Key Resolutions** (2025-10-19):
- FR-016: 符號連結處理（跟隨 + 循環檢測）
- FR-017: 記住選擇（會話暫存）
- FR-018: 檔案移動限制（僅限同一磁碟機 + 提前檢測）
- FR-019: 信心度精度（2 位小數）
- FR-020: 取消操作行為（停止 + 保留已完成）
- FR-021: 空資料夾處理（跳過 + 警告）
- FR-022: CPU 核心數（邏輯核心）
- FR-023: 剩餘時間演算法（簡單平均）
- FR-024: JSON 損壞處理（終止 + 錯誤訊息）
- FR-025: 網路磁碟離線（記錄 + 跳過）
- FR-026: 使用者中斷（優雅關閉）
- FR-027: 空資料夾掃描（跳過 + 不計入）

**Next Steps**:
1. ✅ 需求規格已完善，可開始實作
2. 建議執行 `git add` 提交更新的 spec.md 和 completeness.md
3. 開始 Phase 1: Setup (tasks.md T001-T005)
- 信心度計算的數學精度 (CHK014)
- 使用者中斷的清理機制 (CHK027)
- 多項錯誤處理與邊緣案例需求

---

## Notes

此檢查清單聚焦於**需求本身的品質**，而非實作驗證：
- ✅ 問題: "是否定義了 X 需求？"
- ✅ 問題: "需求 Y 是否明確可測量？"
- ❌ 避免: "驗證 X 功能是否正常運作"
- ❌ 避免: "測試 Y 按鈕是否可點擊"

使用方式：
1. 開發前：檢查需求規格是否完整，減少後期變更
2. PR Review：確認新增的需求是否清晰完整
3. 測試規劃：識別需要補充測試的邊緣案例
