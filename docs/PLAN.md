# 保守式 Copilot 重構 Workflow（Actions + Copilot CLI）

## 摘要
- 目標是讓 GitHub Actions 中的 Copilot CLI 不只產生報告，而是能在受控範圍內實際做小型重構，並以 draft PR 交付。
- 第一版只鎖定 Go 單一套件 `pkg/extractor`，不碰 Python、GUI、資料庫與 workflow 檔，優先追求穩定與可回顧。
- 方案建立在 GitHub 官方已支援的 Copilot CLI Actions 自動化、CLI autopilot，以及「自動化後再處理輸出/PR」的模式上：
  [Automate with Actions](https://docs.github.com/en/copilot/how-tos/copilot-cli/automate-copilot-cli/automate-with-actions)、
  [Autopilot](https://docs.github.com/en/copilot/concepts/agents/copilot-cli/autopilot)、
  [Cloud agent settings](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/configuring-agent-settings)。

## 重要變更
- 新增 workflow：[`.github/workflows/copilot-refactor-go.yml`](C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration\.github\workflows\copilot-refactor-go.yml)
- 新增窄範圍 prompt 檔：[`.github/prompts/refactor-pkg-extractor.md`](C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration\.github\prompts\refactor-pkg-extractor.md)
- 不修改現有 CI workflow；新 workflow 只負責「小範圍重構 + 驗證 + 建立/更新 draft PR」
- 不修改 repo 既有廣域 [`copilot-instructions.md`](C:\Users\cy5407\Desktop\PornActressDB-Golang-Migration\.github\copilot-instructions.md) 的自主權限設定；CI 安全邏輯改由 workflow guard 與專用 prompt 控制

## 介面與行為
- Workflow 觸發：
  - `workflow_dispatch`
  - 每週一次排程，固定在台北時間週一上午執行
- Workflow 權限：
  - `contents: write`
  - `pull-requests: write`
- 必要 secret：
  - `PERSONAL_ACCESS_TOKEN`
  - 用於 `COPILOT_GITHUB_TOKEN`
  - 此 token 需具備 GitHub 官方文件要求的 `Copilot Requests` 權限
- 固定 branch 與 PR 策略：
  - branch 名稱固定為 `copilot/refactor-extractor`
  - 每次執行只更新同一個 draft PR，避免 PR 爆量
  - base branch 使用 repo default branch
- Copilot 執行模式：
  - 使用 `copilot -p ... --autopilot --max-autopilot-continues 3`
  - 僅允許 `write`、`shell(git:*)`、`shell(go:*)`
  - 不給整個 repo 的無限制自由重構權限
- Prompt 約束：
  - 只允許修改 `pkg/extractor/**`
  - 可同步修改對應測試
  - 只做可讀性、重複邏輯、命名、結構微調
  - 不得改 public behavior、CLI 介面、JSON 輸出格式、跨語言橋接
  - 若需要觸碰 `src/`、`cmd/`、`.github/workflows/` 才能完成，必須停止並讓 workflow fail
- Guard 步驟：
  - Copilot 執行後檢查 `git diff --name-only`
  - 只要有變更超出 `pkg/extractor/**`，立即 fail，不建立 PR
  - 若無 diff，workflow 成功結束，但不建立 PR

## 實作流程
- Checkout repo，設定 Go 與 Node 環境，安裝 Copilot CLI
- 先跑 baseline：`go test ./pkg/extractor -v`
- 執行 Copilot CLI 專用 prompt，要求它只在允許範圍內重構並自行驗證
- 執行變更範圍 guard
- 跑驗證：
  - `go test ./pkg/extractor -v`
  - `go test ./pkg/... -v`
- 產出 `copilot-summary.md`，寫入 workflow summary
- 若有合法 diff 且測試通過，建立或更新同一個 draft PR
- PR 內容固定標註：
  - AI 產生
  - 僅限 `pkg/extractor`
  - 已通過 Go 套件測試
  - 待人工 review 後才可合併

## 測試情境
- 手動觸發、無變更時：workflow 成功，無 PR
- 小型合法重構時：建立或更新單一 draft PR
- Copilot 觸碰 `pkg/extractor` 以外檔案時：workflow fail，無 PR
- 重構後 `go test ./pkg/extractor -v` 失敗時：workflow fail，無 PR
- 重構後 `go test ./pkg/... -v` 失敗時：workflow fail，無 PR
- 重跑 workflow 時：更新既有 `copilot/refactor-extractor` PR，不新增第二張 PR
- 排程與手動同時發生時：用 workflow concurrency 保證一次只跑一個

## 假設與預設
- 第一個重構目標預設選 `pkg/extractor`，因為它 Go-only、檔案小、已有單元測試、風險明顯低於 `pkg/database` 與 `src/services/go_bridge.py`
- 第一版不做自動 merge，只做 draft PR
- 第一版不引入 Python 測試與整合測試，因為 scope 被刻意限制在 Go extractor；待連續穩定後再擴大
- 這份方案明確避開 Copilot cloud agent 的自動 workflow 放行模式；官方文件指出 cloud agent 預設不會自動跑 Actions，且自動放行有 secrets 與未審查程式碼風險，因此不作為第一版主路線
- 這個方案的成功標準是：
  - 每週能穩定跑
  - 不會改到 scope 外檔案
  - 不會直接污染主分支
  - 只產生可 review 的單一 draft PR
