# 批次搜尋優化計畫

> 目標：提升批次搜尋的速度與穩定性，減少被封鎖風險，改善使用者體感。

---

## 📋 Todo List

| # | 項目 | 狀態 | 預估時間 |
|---|------|------|---------|
| 1 | 建立 retry_utils 工具模組 | ⬜ 未開始 | 3 分鐘 |
| 2 | AV-WIKI 併發數自動調節 | ⬜ 未開始 | 5 分鐘 |
| 3 | chiba-f 加入簡單退避 | ⬜ 未開始 | 2 分鐘 |
| 4 | 級聯搜尋進度顯示優化 | ⬜ 未開始 | 3 分鐘 |
| 5 | 驗證與回歸測試 | ⬜ 未開始 | 2 分鐘 |

---

## 🔧 技術細節

### 1. 建立 retry_utils 工具模組

**檔案**：`src/utils/retry_utils.py`（新增）

#### 1.1 ExponentialBackoff（指數退避計算器）

```python
class ExponentialBackoff:
    def __init__(
        self,
        base_delay: float = 0.5,      # 基礎延遲
        max_delay: float = 30.0,       # 最大延遲上限
        multiplier: float = 2.0,       # 每次失敗乘數
        jitter: bool = True            # 是否加入隨機抖動
    )
    
    def next_delay(self) -> float      # 回傳下一次應等待的秒數
    def reset(self)                    # 重置計數器（成功後呼叫）
    def current_attempt(self) -> int   # 目前已重試次數
```

**演算法**：
```
delay = min(base_delay × (multiplier ^ attempt), max_delay)
若 jitter=True，加入 ±20% 隨機偏移
```

**範例**：
| 重試次數 | 延遲（秒） |
|---------|-----------|
| 0 | 0.5 |
| 1 | 1.0 |
| 2 | 2.0 |
| 3 | 4.0 |
| 4 | 8.0 |
| 5+ | 16.0 → 30.0（上限） |

---

#### 1.2 AdaptiveConcurrencyController（自適應併發控制器）

```python
class AdaptiveConcurrencyController:
    def __init__(
        self,
        initial: int = 15,             # 初始併發數
        minimum: int = 2,              # 最低併發數
        maximum: int = 30,             # 最高併發數
        decrease_threshold: int = 3,   # 連續錯誤達此數值則降載
        increase_threshold: int = 10,  # 連續成功達此數值則升載
        decrease_factor: float = 0.5,  # 降載時乘數
        increase_step: int = 2         # 升載時增量
    )
    
    def report_success(self)           # 回報成功
    def report_failure(self)           # 回報失敗
    def get_concurrency(self) -> int   # 取得目前建議併發數
```

**降載邏輯**：
```
連續失敗 ≥ 3 次 → concurrency = max(minimum, concurrency × 0.5)
```

**升載邏輯**：
```
連續成功 ≥ 10 次 → concurrency = min(maximum, concurrency + 2)
```

**狀態轉換**：
```
         連續成功 10+           連續失敗 3+
    ┌─────────────────┐    ┌─────────────────┐
    │                 ▼    │                 ▼
 ┌──┴──┐           ┌──┴──┐           ┌──────┐
 │ 15  │ ◄──────── │  8  │ ◄──────── │  4   │
 └─────┘           └─────┘           └──────┘
   正常              降載1             降載2
```

---

### 2. AV-WIKI 併發數自動調節

**檔案**：`src/scrapers/sources/avwiki_scraper.py`

**修改函式**：`search_batch_concurrent`

#### 改動點

| 位置 | 現況 | 改為 |
|------|------|------|
| 方法開頭 | 固定 `Semaphore(max_concurrent)` | 引入 `AdaptiveConcurrencyController` |
| 單筆搜尋 | 無錯誤處理回報 | 成功/失敗回報 + 暫時性錯誤退避 |
| semaphore | 固定值 | 動態更新 |

#### 暫時性錯誤定義（觸發退避）

| 錯誤類型 | 說明 |
|---------|------|
| HTTP 429 | Too Many Requests（速率限制） |
| HTTP 500/502/503/504 | 伺服器錯誤 |
| `asyncio.TimeoutError` | 請求超時 |
| `aiohttp.ClientConnectionError` | 連線失敗 |

#### 非暫時性錯誤（不退避）

| 錯誤類型 | 說明 |
|---------|------|
| HTTP 404 | 頁面不存在（正常情況） |
| `PARSING_ERROR` | 解析失敗（網頁結構問題） |

---

### 3. chiba-f 加入簡單退避

**檔案**：`src/services/web_searcher.py`

**修改函式**：`batch_cascade_search` 第二階段

#### 改動邏輯

```python
consecutive_failures = 0

for code in failed_codes:
    result = self._search_chiba_f_net(code, stop_event)
    
    if result and result.get("actresses"):
        consecutive_failures = 0  # 成功，重置
    else:
        consecutive_failures += 1
        if consecutive_failures >= 3:
            # 遞增延遲：0.5s, 1.0s, 1.5s, ... 上限 3.0s
            backoff_delay = min((consecutive_failures - 2) * 0.5, 3.0)
            time.sleep(backoff_delay)
```

#### 延遲公式

| 連續失敗次數 | 延遲（秒） |
|-------------|-----------|
| 1-2 | 0 |
| 3 | 0.5 |
| 4 | 1.0 |
| 5 | 1.5 |
| 6 | 2.0 |
| 7+ | 3.0（上限） |

---

### 4. 級聯搜尋進度顯示優化

**檔案**：`src/services/web_searcher.py`

**修改函式**：`batch_cascade_search`

#### 現有問題

| 問題 | 影響 |
|------|------|
| 快取命中仍輸出 log | 輸出太多雜訊 |
| 每筆都輸出完整進度 | 資訊重複、畫面跳動 |
| 第二/三階段冗餘前綴 | 干擾閱讀 |

#### 解法

| 問題 | 解法 |
|------|------|
| 快取命中 | 靜默處理，只統計數字，結束時輸出摘要 |
| 重複進度 | 每 5 筆或每階段結束輸出一次 |
| 冗餘前綴 | 精簡格式，只顯示關鍵資訊 |

#### 改善後輸出範例

```
============================================================
📡 第一階段：AV-WIKI 批次併發搜尋 (100 個番號)
============================================================
📦 快取命中: 30 個 | 🔍 實際搜尋: 70 個
✅ AV-WIKI 完成: 55/70 找到資料

============================================================
🔄 第二階段：chiba-f 備援搜尋 (15 個番號)
============================================================
[5/15] 搜尋中...
[10/15] 搜尋中...
✅ chiba-f 完成: 8/15 找到資料

============================================================
📊 第三階段：JAVDB 備援搜尋 (7 個番號)
============================================================
⚠️ 已啟用內建安全延遲（約 3-7 秒/次）
[3/7] 搜尋中...
✅ JAVDB 完成: 4/7 找到資料

============================================================
📈 搜尋摘要
============================================================
總計: 100 | 成功: 97 (97%) | 失敗: 3 (3%)
來源分布: AV-WIKI 85, chiba-f 8, JAVDB 4
```

---

### 5. 驗證與回歸測試

#### 步驟

1. **Ruff 檢查**
   ```powershell
   ruff check .
   ```
   預期：`All checks passed!`

2. **語法編譯檢查**
   ```powershell
   python -m py_compile src/utils/retry_utils.py
   python -m py_compile src/scrapers/sources/avwiki_scraper.py
   python -m py_compile src/services/web_searcher.py
   ```
   預期：無輸出（成功）

3. **手動驗證**（選用）
   - 啟動 GUI
   - 輸入 5-10 個測試番號執行批次搜尋
   - 觀察日誌確認：
     - [ ] 併發數有動態調整
     - [ ] 進度顯示精簡
     - [ ] 搜尋結果格式不變

---

## ⚠️ 風險評估

| 風險 | 影響程度 | 緩解措施 |
|------|---------|---------|
| 併發降載太激進導致變慢 | 中 | 只有連續 ≥ 3 次錯誤才降；回升也漸進 |
| chiba-f 延遲導致第二階段變慢 | 低 | 只有連續失敗才加；正常情況 0 延遲 |
| 邏輯改動影響搜尋結果 | 中 | 不動解析邏輯，只改節奏控制 |

---

## 📊 預期效果

| 指標 | 改善前 | 改善後 |
|------|--------|--------|
| AV-WIKI 被 429 機率 | 偶發 | 大幅降低（自動降載） |
| chiba-f 連續失敗卡頓 | 無處理 | 自動退避 |
| 進度輸出雜訊 | 多 | 精簡 |
| 整體搜尋穩定性 | 一般 | 提升 |

---

## 📁 涉及檔案

| 檔案 | 操作 |
|------|------|
| `src/utils/retry_utils.py` | 新增 |
| `src/scrapers/sources/avwiki_scraper.py` | 修改 |
| `src/services/web_searcher.py` | 修改 |

---

*文件建立時間：2025-12-13*
