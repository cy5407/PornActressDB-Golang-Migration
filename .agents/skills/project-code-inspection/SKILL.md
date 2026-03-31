---
name: project-code-inspection
description: 專案程式碼巡檢工作流 - 用於例行巡檢安全性、冗餘與一致性衝突、明顯低效寫法，並先讀取既有報告與近期提交避免重複回報已修復事項。
---

# 專案程式碼巡檢 Skill

## 何時使用此 Skill

當需要執行本專案的例行程式碼巡檢、追蹤既有安全議題、整理持續追蹤報告，或將 automation 的巡檢流程手動重跑時使用。

常見情境：
- 檢查本輪程式碼是否有新的安全性問題
- 確認既有追蹤項目是否已在近期提交中修復
- 針對高價值問題直接補修正、補測試並更新報告
- 將巡檢結果整理到 `security_reports/code_review_tracking.md`

## 巡檢目標

巡檢時只聚焦高價值問題：
- 安全性或資安風險
- 程式碼冗餘、行為不一致、實作重複
- 明顯低效且已知有更佳寫法的路徑

預設不回報：
- 純風格問題
- 只影響格式或命名、但不影響正確性與維護性的問題
- 已在既有報告或近期提交中明確修復的問題

## 固定工作流

### 1. 先讀既有上下文

每次巡檢開始時，先讀以下內容：
- automation memory（若本次工作由排程延伸而來）
- `security_reports/` 下既有巡檢或修復報告
- 最近 20 筆 git commit
- `AGENTS.md` 內「已修復問題紀錄」與「已知未解決問題」

目標是先建立「哪些問題已修、哪些還在追」的基線，避免重複回報。

建議指令：

```powershell
git log --oneline -20
rg -n "已修復問題紀錄|已知未解決問題" AGENTS.md
Get-ChildItem security_reports
```

### 2. 先驗證舊問題是否仍存在

不要直接沿用舊報告結論。對每個待追蹤項目，先確認：
- 是否已被近期 commit 修掉
- 是否只是舊報告未更新
- 是否仍可在目前程式碼中穩定重現

若已修復，更新追蹤報告狀態，不要再次列為新問題。

### 3. 進行高信噪比巡檢

依下列順序檢查：
1. 安全性與錯誤處理
2. 執行緒安全與重試邏輯
3. Python ↔ Go 橋接一致性
4. 重複實作與行為分岐
5. 明顯效能熱點

優先查看：
- `src/services/`
- `src/scrapers/`
- `src/models/`
- `pkg/`
- 與本輪修正直接相關的測試檔

如果是搜尋或爬蟲路徑，特別檢查：
- timeout 是否存在
- Retry-After / rate limit 資訊是否有往下傳遞
- fallback 是否完整
- 編碼與相依套件缺失時是否會直接崩潰

如果是 GUI 路徑，特別檢查：
- GUI 更新是否回主執行緒
- 背景執行緒是否直接操作 tkinter 元件

如果是 GoBridge 或 Go CLI 路徑，特別檢查：
- JSON 輸出是否穩定
- fallback 到 Python 是否完整
- 逾時、錯誤訊息與結構是否一致

### 4. 發現問題後優先補最小修正

若問題明確、修正範圍小且風險可控，優先直接修正，而不是只留下報告。

修正時一併處理：
- 最小必要測試
- 回歸測試
- 相關報告更新

避免一次混入無關重構。

### 5. 固定做最小驗證

完成修正後，至少做下列其中幾項，依變更內容選擇：
- `python -m pytest <targeted tests> -q -p no:cacheprovider`
- `python -m py_compile <changed python files>`
- `go test <relevant packages>`
- `go build -o classifier.exe ./cmd/scanner`
- 定向 smoke test / inline 驗證

原則：
- 優先跑與修正直接相關的最小測試集
- 若是 import、語法、例外流程調整，至少做 `py_compile`
- 若是 Go CLI 或橋接層，至少確認 build 或核心命令可執行

### 6. 更新持續追蹤報告

巡檢結束後，更新 `security_reports/code_review_tracking.md`，至少包含：
- 本輪新增問題
- 本輪已修正問題
- 仍待追蹤問題
- 驗證結果
- commit / push / 阻塞狀態

若本輪沒有可安全提交的修正，仍要更新報告，明確記錄沒有提交的原因。

## 建議輸出格式

每輪巡檢摘要建議固定包含：
- 本輪先讀取的歷史來源
- 已驗證不再成立的舊問題
- 本輪已修正
- 本輪仍待追蹤
- 驗證結果
- git 狀態或阻塞

## 與其他 Skills 的搭配

- 需要一般程式碼審查準則時，搭配 `code-review`
- 需要驗證測試策略時，搭配 `testing-validation`
- 需要 Python ↔ Go 橋接背景時，搭配 `go-bridge-development`
- 需要快速定位相關檔案與符號時，搭配 `smart-code-search`

## 執行原則

- 先確認現況，再下結論
- 不重複回報已修復事項
- 只處理可證明、可行動的問題
- 小修正配小驗證，維持迭代速度
- 報告必須能延續到下一輪使用
