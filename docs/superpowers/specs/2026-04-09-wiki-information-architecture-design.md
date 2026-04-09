# Wiki Information Architecture Design

> Date: 2026-04-09  
> Scope: wiki 內部重構，不調整 README / AGENTS / CLAUDE 入口  
> Status: 設計決策

## 問題陳述

目前 wiki 已經累積大量高價值內容，特別是 `pitfalls/`、`patterns/`、`architecture/` 與 `log.md`，但入口仍偏向維護者導向：

- 新進協作者或 AI 容易先看到分類目錄，卻不容易快速掌握系統全貌
- 真實修復案例分散在 pitfall 與 log，缺少可重演、可驗證的案例庫
- 掃描 / 搜尋 / 片商分類 / 搬移規則 / dist 資源等輸出契約散落多處
- 現有頁面缺少一致的狀態標記，AI 容易把設計想法、已驗證事實與待確認推測混在一起

本設計目標是在**不大幅搬動既有 wiki 結構**的前提下，補上可導覽、可重演、可查契約的知識層。

## 目標

1. 建立一頁可快速掌握系統責任邊界的單頁架構總表。
2. 建立 `wiki/examples/`，收納真實修復案例並用固定模板描述。
3. 把高頻輸出契約與行為規則集中成可查頁面。
4. 導入統一狀態標記，並逐步回補到新舊頁面。
5. 保持既有 `pitfalls/`、`patterns/`、`architecture/` 路徑穩定，避免大規模連結失效。

## 非目標

- 本輪不重寫整個 wiki 的分類法
- 本輪不整理 README、AGENTS.md、CLAUDE.md 的入口文案
- 本輪不追求一次補齊所有舊文件，只建立可持續擴張的骨架

## 採用策略

採用 **加法式重構**：

- 保留既有 `architecture/`、`patterns/`、`pitfalls/`、`log.md`
- 新增較高層的入口頁與案例頁
- 以交叉連結方式整合舊內容，而非搬遷大量舊頁

這個策略的優點是：

- 風險低，不會打亂現有 AI 與人類使用路徑
- 可以立即改善可讀性
- 可以分批落地，不必一次整理完整個知識庫

## 目標資訊架構

```text
wiki/
├── index.md
├── log.md
├── architecture/
│   ├── overview.md
│   ├── system-contracts.md          # new
│   └── ...
├── contracts/                       # new
│   ├── scan-search-contracts.md
│   ├── studio-move-contracts.md
│   └── packaging-runtime-constraints.md
├── examples/                        # new
│   ├── same-root-studio-classification.md
│   ├── non-video-scan-filter.md
│   └── same-path-move-safety.md
├── patterns/
├── pitfalls/
└── ...
```

## 頁面設計

### 1. `wiki/architecture/system-contracts.md`

**定位：** 單頁架構總表。  
**狀態：** 已驗證 + 設計決策混合頁，需明確標示每區塊狀態。

**必含欄位：**

| 欄位 | 說明 |
|------|------|
| 模組 | 檔案或套件名稱 |
| 角色 | 在整體流程中的責任 |
| 主要輸入 | 接受的資料或呼叫來源 |
| 主要輸出 | 回傳資料、產出副作用或檔案 |
| 主要相依 | 依賴的模組 / JSON / 設定 |
| 常見風險 | 容易踩坑或契約漂移處 |
| 參考文件 | 對應 architecture / pitfalls / examples 頁 |

**第一批模組：**

- `wails-app/frontend/src/App.tsx`
- `wails-app/backend/app.go`
- `src/services/go_cli.py`
- `pkg/mover`
- `pkg/database`
- `pkg/studio`

### 2. `wiki/examples/`

**定位：** 可重演、可驗證的真實案例庫。  
**狀態：** 原則上每篇都應標為 **已驗證**。

**第一批案例：**

1. `same-root-studio-classification.md`
2. `non-video-scan-filter.md`
3. `same-path-move-safety.md`

**固定模板：**

1. 問題場景
2. 目錄結構
3. 預期行為
4. 實際觀察到的錯誤
5. 根因
6. 實際修法
7. 測試 / 驗證點
8. UI 日誌範例
9. 相關 pitfall / 相關程式檔案

### 3. `wiki/contracts/`

**定位：** 高頻行為與輸出契約中心。  
**狀態：** 以 **已驗證** 或 **設計決策** 為主，不應混入未確認推測。

**建議拆分：**

- `scan-search-contracts.md`
  - 掃描結果 shape
  - 搜尋結果 shape
  - `search_status` / `search_method` 列舉與語意
- `studio-move-contracts.md`
  - 片商分類的移動主體是女優資料夾
  - 同名資料夾合併規則
  - 同名檔案的 `skip / overwrite / rename`
  - `source == destination` 安全規則
- `packaging-runtime-constraints.md`
  - `config.ini` 尋址規則
  - `studios.json` / `major_studios.json` 的 runtime 需求
  - Wails build / dist 需要同步的外部資源

### 4. 狀態標記規範

wiki 新增三種固定標記：

| 標記 | 定義 | 使用時機 |
|------|------|----------|
| 已驗證 | 已由程式碼、測試、實測或 build 證據支持 | 行為事實、案例結果、契約現況 |
| 設計決策 | 已與使用者或專案方針確認的規則 | 業務規則、架構方向、未來維護方針 |
| 推測待驗證 | 尚未有直接證據，需要實測或讀碼確認 | 暫存假設、待補查線索 |

**導入方式：**

- 新頁面從第一版就必須使用標記
- 舊頁面採逐步回補，不要求一次補齊
- 若同一頁混合多種狀態，應對區塊而非整頁標記

## 導覽與交叉連結策略

`wiki/index.md` 將新增或強化以下入口：

- 單頁架構總表
- 案例庫
- 契約頁
- 狀態標記說明

所有新頁面都應至少具備：

- 一個回鏈到 `index.md`
- 一個鏈到相關 `pitfalls/`
- 一個鏈到相關 `architecture/` 或 `contracts/`

## 維護流程

新知識寫入順序如下：

1. 判斷屬性：`architecture / contracts / examples / pitfalls / log`
2. 若可重演，優先寫 `examples/`
3. 若屬於規則或輸出形狀，寫 `contracts/`
4. 若屬於踩坑教訓，寫 `pitfalls/`
5. 最後在 `log.md` 補一筆摘要索引

## 驗證標準

第一輪完成後，應滿足：

1. `wiki/index.md` 能明顯導向單頁架構總表、案例庫、契約頁
2. `system-contracts.md` 能回答主要模組的責任與邊界
3. 三篇案例都能清楚回答「發生什麼 / 為何發生 / 如何修 / 如何驗證」
4. 契約頁能回答至少以下高頻問題：
   - 掃描結果長什麼樣
   - 搜尋狀態有哪些
   - 片商分類移動什麼單位
   - 同名資料夾 / 檔案怎麼處理
   - dist build 依賴哪些外部檔案
5. 新頁面與至少一部分舊頁已導入狀態標記

## 建議落地順序

### Phase 1：建立骨架

1. 新增 `architecture/system-contracts.md`
2. 新增 `examples/` 三篇
3. 新增 `contracts/` 三頁

### Phase 2：補導覽與標記

4. 更新 `wiki/index.md`
5. 更新 `wiki/log.md` 記錄本次 wiki 重構
6. 為新頁與高流量舊頁補上狀態標記

### Phase 3：第二輪擴充

7. 收斂 benchmark / 實測成效成摘要頁
8. 收斂安全 / 路徑 / 打包限制成長期約束頁

## 風險與控管

| 風險 | 說明 | 控管方式 |
|------|------|----------|
| 重複內容增加 | 新頁可能與舊 pitfall 重複 | 新頁只做索引與收斂，細節回鏈舊頁 |
| 路徑改動太大 | 搬遷舊頁會破壞既有連結 | 本輪不搬家，只新增 |
| 狀態標記失控 | 標記種類太多會變成噪音 | 固定只保留三種標記 |
| 案例頁空泛 | 沒附證據會變成另一種筆記 | 每篇案例都要求測試點與 UI log 範例 |

## 成功定義

當使用者或 AI 問以下問題時，應能在 1-2 跳內從 wiki 找到答案：

- 系統的主流程和各模組責任是什麼？
- 片商分類移動的是檔案還是女優資料夾？
- 為什麼同輸入輸出目錄會出現同路徑保護？
- 非影片檔為什麼不能進搜尋？
- Wails dist 缺少片商資料時要補哪些檔案？

若這些問題仍需來回翻 4-5 篇文件才能理解，代表本輪重構尚未達標。
