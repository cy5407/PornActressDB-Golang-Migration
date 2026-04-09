# Go-only 路線收尾計畫

> 更新日期：2026-04-09
> 
> 這份文件是給之後接手的 AI / 開發者看的。從這一天開始，專案的主方向是 **Go-only delegation**：**能不用 Python 就不用 Python，不再補回或新增 Python fallback。**

---

## 核心決策

1. **不再以「Go 不可用時 Python 要能正常接手」為目標。**
2. **Python 層應盡量只保留薄委派 / 業務編排 / 爬蟲整合，不重做 Go 已經負責的能力。**
3. **遇到 Go CLI 不可用時，優先修 CI、建置、路徑解析、workflow；不是補 Python fallback。**
4. **後續所有重構都應以刪除冗餘 fallback、guard、雙軌實作為優先。**

---

## 現況判斷

目前 repo 的方向其實已經非常接近 Go-only，但還有幾個地方沒有完全收尾：

### 1. CI 觀念仍混雜

- `.github/workflows/python-test.yml` 目前還寫著：
  - `Run Python unit tests (without Go CLI)`
  - `CLASSIFIER_EXE: ""`
- 這是舊思維，假設 Python 測試應該覆蓋「Go 不可用」情境。
- 但現在方針已改成 **不保留 fallback**，所以這個 workflow 應改成：
  - 在 Linux runner 先建置 `classifier`
  - Python 測試直接跑 **Go delegation 路徑**
  - 不再刻意模擬「沒有 Go CLI」

### 2. `go_cli.py` 的執行檔解析要標準化

- 專案中多個 workflow / Dockerfile 已經在用 `CLASSIFIER_EXE`
- 但 `src/services/go_cli.py` 目前沒有正式把 `CLASSIFIER_EXE` 當成最高優先來源
- 這會造成 CI / Linux / 本機執行時的路徑行為不一致

**應修方向：**

- `go_cli.py` 優先讀 `CLASSIFIER_EXE`
- 若有設定，就直接使用該路徑
- 若沒設定，再退回目前的搜尋邏輯（repo root / cwd / PATH）

> 注意：這不是 Python fallback，而是 **Go CLI 路徑解析** 的標準化。

### 3. 測試還殘留舊假設

- 部分測試與 workflow 還帶著「Go 不在也要過」的歷史包袱
- 之後應改成兩類：

| 類型 | 正確方向 |
|------|----------|
| 純 Python 邏輯測試 | 只測真的仍由 Python 負責的邏輯 |
| Go delegation / 整合測試 | 明確要求先有 `classifier`，直接測真實路徑 |

不應再維持這種狀態：

- workflow 說自己在測「without Go CLI」
- 但產品方向其實要求 Go 必須存在

### 4. fallback 註解 / 文件 /命名仍需清理

雖然很多 fallback 已刪掉，但文件與部分說明還殘留舊語意，例如：

- 「若 Go 不可用則回傳 Python 結果」
- 「fallback 到 Python」
- 「測試 Python fallback 路徑」

這些都要逐步改掉，避免未來 AI 看到註解後又往錯方向補實作。

---

## 接下來建議的實作順序

### Phase A — 先把 CI 與執行環境對齊 Go-only

1. 更新 `src/services/go_cli.py`
   - 支援 `CLASSIFIER_EXE`
   - Linux / Windows / PATH 路徑解析一致化

2. 更新 `.github/workflows/python-test.yml`
   - 先建置 Linux `classifier`
   - 設 `CLASSIFIER_EXE: ${{ github.workspace }}/classifier`
   - 移除「without Go CLI」與空字串設定

3. 檢查其他 workflow
   - `integration-test.yml`
   - `sonar.yml`
   - Dockerfile
   - 確認 Linux runner 用 `classifier`
   - Windows 包裝 / 發行才用 `classifier.exe`

### Phase B — 清理測試中的 fallback 舊假設

1. 檢查 `tests/` 內是否還有：
   - 以 Go 不存在為前提的測試
   - mock fallback path 的測試
   - 依賴舊 guard/fallback 說明的測試名稱

2. 調整為：
   - Go-only delegation 測試
   - CLI 可用時的整合測試
   - 若 Go 缺失，應明確失敗或 skip（依測試定位決定），但**不要再驗證 Python fallback**

### Phase C — 繼續刪冗餘 fallback 痕跡

目標不是大改功能，而是把舊時代殘留的雙軌思維清乾淨。

優先搜尋關鍵字：

- `fallback`
- `Go 不可用`
- `Python fallback`
- `CLASSIFIER_EXE: ""`
- `without Go CLI`
- `if ... is_available`
- `except ImportError`

看到之後要分辨：

| 類型 | 處理原則 |
|------|----------|
| 真正冗餘的 Python fallback | 刪除 |
| Go 路徑解析 / import 相容層 | 視必要保留 |
| 記憶體快取回傳 | 只有在不重做 Python 業務邏輯前提下再評估 |
| 舊註解 / 舊文件 | 改寫 |

---

## 這次調查時已確認的問題

### Python Test workflow 失敗不是 `chore: 連結 SonarLint 至 SonarCloud 專案` 造成的

GitHub Actions `Python Test` 最近連續多個 run 都是紅的，屬於既有問題。

目前可見的根因：

1. `tests/test_extractor.py`
   - `src/models/extractor.py` 現在是純 Go 委派
   - workflow 卻沒有先提供正確的 Linux `classifier`
   - 結果 `extract_code()` 全部回 `None`

2. `tests/test_json_database.py`
   - 同樣依賴 Go CLI
   - workflow 若沒有先把可執行檔路徑對齊，就會整串失敗

3. `python-test.yml`
   - 還在刻意把 `CLASSIFIER_EXE` 設成空字串
   - 這和目前 Go-only 方向直接衝突

---

## 給下一個 AI 的明確指示

如果你接到的任務是修 CI、修 extractor、修 json database、修 workflow：

### 請先遵守這些原則

1. **不要再補 Python fallback。**
2. **先修 Go CLI 可用性與 workflow。**
3. **先讓 Linux CI 能正確建置並找到 `classifier`。**
4. **測試失敗時，優先問自己是不是 workflow 還停留在舊時代，而不是去補 Python 路徑。**

### 優先處理檔案

1. `src/services/go_cli.py`
2. `.github/workflows/python-test.yml`
3. `.github/workflows/integration-test.yml`
4. `.github/workflows/sonar.yml`
5. `tests/test_extractor.py`
6. `tests/test_json_database.py`

---

## 目標狀態

完成後應該長這樣：

- Python 層只做薄委派，不重做 Go 功能
- CI 上的 Python 測試預設就有 Go CLI
- `CLASSIFIER_EXE` 成為標準入口
- 測試與文件都不再鼓勵 fallback 思維
- 後續 AI 不會再把時間浪費在「幫 Python 補備援實作」

---

## 一句話版

**這個專案現在的方向不是「Go 壞了 Python 接手」，而是「Go 是主路徑，Python 只保留必要外殼；接下來要做的是把殘留的 fallback 思維與 workflow 全部清乾淨」。**
