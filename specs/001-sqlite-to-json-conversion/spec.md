# Feature Specification: SQLite 轉換為 JSON 資料庫儲存

**Feature Branch**: `001-sqlite-to-json-conversion`  
**Created**: 2025-10-16  
**Status**: Draft  
**Input**: User description: "SQLite 轉換為 JSON 資料庫儲存"

## User Scenarios & Testing

### User Story 1 - 資料庫系統平滑遷移 (Priority: P1)

系統管理員希望將現有 SQLite 資料庫無損地轉換至 JSON 檔案儲存格式，同時保持所有功能可用。這包括保留現有資料、維護查詢性能、確保無停機時間進行遷移。

**Why this priority**: 這是遷移的核心需求。若無法完整保留資料和功能，整個遷移計畫將面臨風險。系統必須支援無停機轉換。

**Independent Test**: 遷移工具可執行並驗證數據完整性後，系統應能使用新的 JSON 資料庫繼續運作，功能等同於 SQLite 版本。

**Acceptance Scenarios**:

1. **Given** 現有 SQLite 資料庫含 500+ 筆影片記錄，**When** 執行遷移工具，**Then** 所有記錄應完整轉移至 JSON 檔案且資料無損
2. **Given** JSON 資料庫已建立，**When** 系統查詢影片資訊，**Then** 應返回與 SQLite 相同的結果
3. **Given** 遷移過程中出現錯誤，**When** 遷移中止，**Then** 原始 SQLite 資料庫應保持完好可復原

---

### User Story 2 - 資料庫類型靈活切換 (Priority: P2)

開發者希望系統能透過設定檔選擇使用 SQLite 或 JSON 資料庫，無需修改程式碼。這讓不同部署環境可選擇最適合的儲存方式。

**Why this priority**: 支援靈活切換對於測試、漸進式遷移和降低風險至關重要。使用設定檔驅動的架構讓操作更安全。

**Independent Test**: 修改設定檔切換資料庫類型後，系統應自動使用新的資料庫後端，功能無異。

**Acceptance Scenarios**:

1. **Given** 設定檔指定 `database_type = sqlite`，**When** 系統啟動，**Then** 應使用 SQLiteDBManager
2. **Given** 設定檔指定 `database_type = json`，**When** 系統啟動，**Then** 應使用 JSONDBManager
3. **Given** 從 SQLite 切換至 JSON，**When** 重啟系統，**Then** 應自動使用 JSON 資料庫無須人工干預

---

### User Story 3 - 複雜查詢能力等價 (Priority: P2)

業務分析師執行統計查詢（女優統計、片商統計、交叉統計）時，JSON 資料庫應返回與 SQLite 相同的結果集，支援相同的篩選和聚合功能。

**Why this priority**: 資料一致性對於商業決策至關重要。若統計結果不同，會造成信任問題。

**Independent Test**: 針對同一查詢，SQLite 和 JSON 版本應返回相同的統計數據。

**Acceptance Scenarios**:

1. **Given** 同一部女優在多部影片中出現，**When** 查詢該女優出演部數，**Then** JSON 和 SQLite 應返回相同計數
2. **Given** 執行片商統計查詢，**When** 篩選特定日期範圍，**Then** 結果集應完全相同
3. **Given** 執行增強版交叉統計，**When** 查詢女優-片商組合，**Then** JSON 結果應等同 SQLite

---

### User Story 4 - 並行存取時資料完整 (Priority: P3)

多個程式同時讀寫資料庫時，JSON 資料庫應確保資料一致性，無損壞或不完整的情況。

**Why this priority**: 並行存取是生產環境的實際需求。防止資料損壞是基本要求，但可在初期版本後優化效能。

**Independent Test**: 模擬並行讀寫後，驗證 JSON 檔案資料完整且無損壞。

**Acceptance Scenarios**:

1. **Given** 五個併發進程同時寫入資料，**When** 所有操作完成，**Then** JSON 檔案應不損壞且包含所有寫入
2. **Given** 一個程式讀取而另一個程式修改，**When** 讀取完成，**Then** 應獲得一致的資料快照

---

### Edge Cases

- 如果遷移中途中止會發生什麼？(應有備份和恢復機制)
- 如果 JSON 檔案被外部程式損壞會如何？(應有驗證和修復機制)
- 如果併發操作超過檔案系統限制會如何？(應優雅降級)
- 如果資料量超大 (>10,000 筆) 會發生什麼？(應評估效能並優化)

## Requirements

### Functional Requirements

- **FR-001**: 系統 MUST 提供遷移工具將 SQLite 資料完整轉移至 JSON 格式，包含所有影片、女優、關聯資料
- **FR-002**: 系統 MUST 支援透過設定檔選擇使用 SQLite 或 JSON 資料庫，無需程式碼修改
- **FR-003**: JSON 資料庫 MUST 實現所有 SQLiteDBManager 的公開方法，包括 add_or_update_video、get_video_info、get_all_videos
- **FR-004**: 系統 MUST 支援統計查詢功能（女優統計、片商統計、交叉統計），結果應等同 SQLite
- **FR-005**: JSON 資料庫 MUST 使用檔案鎖定機制確保併行寫入的資料一致性
- **FR-006**: 系統 MUST 提供驗證工具檢查遷移後的資料完整性（記錄計數、資料雜湊檢查）
- **FR-007**: 系統 MUST 支援從 JSON 資料庫備份建立快照，用於災難恢復
- **FR-008**: 系統 MUST 記錄遷移過程（開始時間、完成時間、處理筆數、任何錯誤）

### Key Entities

- **Video**: 影片記錄，包含 ID、片名、片商、發行日期、網址等屬性
- **Actress**: 女優資訊，包含 ID、姓名、影片出演清單
- **VideoActressLink**: 影片-女優關聯表，定義多對多關係
- **Statistics**: 由多個影片/女優組合計算出的聚合資訊

## Success Criteria

### Measurable Outcomes

- **SC-001**: 遷移工具能在 5 分鐘內完成 500+ 筆記錄的轉移，資料完整性 100% 驗證通過
- **SC-002**: JSON 資料庫查詢結果與 SQLite 完全相同（統計查詢、資訊查詢、篩選結果）
- **SC-003**: 併行操作測試中，5 個併發進程同時讀寫時無資料損壞或損失
- **SC-004**: 遷移工具提供詳細日誌，管理員可清楚追蹤遷移進度和任何警告
- **SC-005**: 系統可透過設定檔在 10 秒內從 SQLite 切換至 JSON 或反向切換
- **SC-006**: 備份恢復測試中，從備份還原的資料應 100% 等同備份時的狀態

