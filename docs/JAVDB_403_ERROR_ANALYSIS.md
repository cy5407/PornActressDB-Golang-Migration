# JAVDB 403 Forbidden 錯誤分析報告

**日期**: 2026-04-03
**嚴重性**: 高 — JAVDB 搜尋功能完全失效
**影響範圍**: `SafeJAVDBSearcher`、級聯搜尋 JAVDB 階段、獨立 JAVDB 搜尋按鈕

---

## 錯誤現象

批次搜尋時，所有 JAVDB 請求均回傳 HTTP 403 Forbidden，且重試機制因等待時間邏輯 bug 永遠直接放棄：

```
⚠️ 收到 403 錯誤，可能被暫時封鎖
⚠️ 403 重試等待時間 288.4 秒超過上限 60 秒，直接放棄
```

---

## 根因分析

### Bug 1：重試等待時間邏輯矛盾（程式碼層級）

**檔案**: `src/services/safe_javdb_searcher.py` 第 247 行

```python
wait_time = 120 + _random_delay(60, 180)  # 計算結果: 180~300 秒
```

但上限設定為：

```python
self.max_retry_wait_seconds = 60.0  # 第 65 行
```

由於 `wait_time`（180~300 秒）**必定大於** `max_retry_wait_seconds`（60 秒），403 重試**永遠會被跳過**。這等同於 403 完全無重試機制。

### Bug 2：缺少 Cloudflare 反爬蟲對策

JAVDB 使用 Cloudflare 保護，僅靠 User-Agent 輪換和 HTTP headers 模擬無法通過驗證。被封鎖後，需要更長的冷卻時間或 Cookie/瀏覽器指紋才能恢復。

### Bug 3：批次搜尋速率過快

即使設定了 3~7 秒延遲，短時間內大量請求仍會觸發 Cloudflare 的速率限制。日誌顯示請求間隔約 5~6 秒，但連續多筆請求累積後仍被封鎖。

### Bug 4：429 重試同樣失效

```python
wait_time = 60 + _random_delay(30, 90)  # 結果: 90~150 秒，也超過 60 秒上限
```

與 403 相同的邏輯問題，429 Too Many Requests 的重試也永遠會被跳過。

---

## 附帶發現：功能重複

### 級聯搜尋中的 JAVDB 階段 vs 獨立 JAVDB 按鈕

| 項目 | 獨立 JAVDB 按鈕 | 級聯搜尋 JAVDB 階段 |
|------|-----------------|---------------------|
| 進入點 | `start_javdb_search` | `_japanese_search_worker` |
| 底層方法 | `process_and_search_javdb` | `batch_cascade_search` |
| 搜尋器 | `SafeJAVDBSearcher` | `SafeJAVDBSearcher`（同一個） |
| 二次搜尋 | 支援（零女優番號重查） | 不支援 |
| 搜尋對象 | 所有未搜尋 + 零女優番號 | 僅 AV-WIKI 失敗的番號 |

**結論**: 兩者底層完全相同，獨立按鈕多了二次搜尋能力。級聯搜尋中的 JAVDB 階段應移除以避免功能重複。

---

## 解決方案

### 方案 A：修復重試邏輯（優先）

將 `max_retry_wait_seconds` 調高至合理範圍，或降低計算出的等待時間，使重試能實際執行。

### 方案 B：引入自適應速率控制

根據連續 403/429 次數動態調整延遲，而非使用固定等待時間。

### 方案 C：移除級聯中的 JAVDB 階段

日文網站搜尋改為純 AV-WIKI，JAVDB 備援交由獨立按鈕。減少 JAVDB 請求總量，降低被封鎖機率。

---

## 相關檔案

- `src/services/safe_javdb_searcher.py` — 核心搜尋器
- `src/services/web_searcher.py` — 級聯搜尋編排
- `src/services/classifier_core.py` — 業務流程
- `src/ui/main_gui.py` — GUI 按鈕綁定
- `src/scrapers/sources/javdb_scraper.py` — 爬蟲層（async 版，與 safe_javdb_searcher 獨立）
