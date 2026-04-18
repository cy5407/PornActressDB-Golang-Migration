---
category: Wails
date: 2026-04-08
---
# Wails 批次搜尋效能優化歷程

> 歸檔日期：2026-04-07  
> 成果：63 筆搜尋從 **75 秒 → 10 秒**（7.5x 加速）

---

## 問題描述

Wails GUI (`actress-classifier.exe`) 第一版批次搜尋需要 75 秒完成 63 筆番號（1G 網路）。效能遠低於預期。

---

## 根本原因分析（兩層瓶頸）

### 瓶頸 1：Python subprocess 啟動開銷（~32 秒）

原版 `BatchSearch()` 對每個番號各啟動一個 Python process：

```go
// 原版 Go（已修正）：每個番號獨立啟動 Python
for _, code := range codes {
    cmd := exec.Command("python", "search_single.py", code)
    // ...
}
```

65 次 × ~500ms Python import 時間 = **約 32 秒純啟動開銷**。

### 瓶頸 2：SafeSearcher Rate Limiter（剩餘 ~43 秒的主因）

`SafeSearcher.japanese_searcher.config`：
```python
min_interval = 0.5   # 秒
max_interval = 1.5   # 秒
```

當 HTTP 回傳速度 < 0.5s 時，`wait_time = random.uniform(0.5, 1.5) - elapsed`，最長 sleep 1.2 秒。  
5 個 workers，每個 worker 每次搜尋後都被強制 sleep → 人為串行化。

---

## 優化歷程（四輪）

### 第一輪（原始）：75 秒

```
每筆 → 啟動 Python → import → search → 結束
65 次 × ~1.15s = 75s
```

### 第二輪（batch script）：39 秒

**方法**：建立 `src/scrapers/run_batch_search.py`，一次啟動一個 Python process，內部用 `ThreadPoolExecutor(15)` 並發搜尋。

```python
# run_batch_search.py
with ThreadPoolExecutor(max_workers=workers) as executor:
    futures = {executor.submit(search_one, c): c for c in codes}
```

效果：啟動開銷 32s → 5s（15 threads 並行初始化，GIL 在 I/O 讓步）。

### 第三輪（反效果）：50 秒

**嘗試**：主 thread 預先建立所有 WebSearcher（避免 GIL 競爭）。

```python
# 錯誤嘗試：主 thread 串行預建
searchers = [_make_searcher() for _ in range(20)]  # 14 秒！
```

**原因失敗**：
- Python GIL 在 I/O 操作（讀 cache 文件、import module）時**自動讓步**
- threads 並行初始化本來就能近似並行（5s）
- 主 thread 串行強制消除了這個優勢（14s）

**教訓**：GIL 在 I/O 密集段不是瓶頸，強制串行只會更慢。

### 第四輪（最終）：10 秒 🚀

**方法**：恢復 thread-local 並行初始化 + 停用 rate limiter。

```python
def _get_searcher():
    if not hasattr(_thread_local, "searcher"):
        from services.web_searcher import WebSearcher
        searcher = WebSearcher(ConfigManager(_resolve_config_path()))
        # 批次模式：每個 thread 獨立 SafeSearcher，rate limiter 無意義
        searcher.japanese_searcher.config.min_interval = 0.0
        searcher.japanese_searcher.config.max_interval = 0.0
        searcher.safe_searcher.config.min_interval = 0.0
        searcher.safe_searcher.config.max_interval = 0.0
        _thread_local.searcher = searcher
    return _thread_local.searcher
```

**為什麼停用 rate limiter 安全**：
- 批次模式中每個 thread 有獨立 `SafeSearcher`
- `last_request_time` 存在各自實例中，**不跨 thread 共用**
- rate limiter 的原意是防止「同一 session 連續高頻請求」——批次模式天然分散
- AV-WIKI 的 TCP back-pressure（連線超時、HTTP 429）仍提供自然保護

---

## 最終效能數據

| 指標 | 數值 |
|------|------|
| 搜尋筆數 | 63 筆（唯一番號）|
| 並行 workers | 20 |
| Python 啟動耗時 | ~3 秒 |
| 搜尋有效時間 | ~7 秒 |
| **總耗時** | **10 秒** |
| 成功率 | **63/63 = 100%** |

實測 log（第四輪）：

```
09:46:08 🔍 開始搜尋 63 筆番號
09:46:11 搜尋中 (1/63)：PFES-115   ← 3 秒啟動
09:46:18 搜尋完成：63 成功 / 0 失敗 ← 總計 10 秒
```

---

## ⚠️ 效能波動：AV-WIKI Server Throttling

**第五輪實測（連續測試後，10:06:01 → 10:09:21 = 200 秒）**

同一天連續多輪測試後，AV-WIKI 開始 server 端限速：

```
(1-4) 10:06:15~17  → 每筆 <2s（正常）
(5)   10:06:23     → 突然跳到 6s
(6)   10:06:30     → 7s
(11)  10:06:45     → 8s
...之後維持 5-8s/筆
```

根本原因：短時間內大量並發請求觸發 server 端 IP 限速，這是**外部因素，無法從客戶端繞過**。

| 狀態 | 耗時 | 說明 |
|------|------|------|
| Server 不限速（冷啟動）| **10 秒** | 距上次測試有足夠間隔 |
| Server 限速（連續測試）| **200 秒** | AV-WIKI throttling |
| 實際生產環境（估）| **20-40 秒** | 使用者不會連續高頻觸發 |

**緩解策略**：日常使用間隔 5-10 分鐘以上即可自動解除限速。程式碼端已達優化極限。

---

## 相關程式碼

- `src/scrapers/run_batch_search.py`：批次搜尋 Python script
- `wails-app/backend/app.go`：`BatchSearch()` Go binding
- `src/services/safe_searcher.py`：SafeSearcher 實作（rate limiter 在此）

## 相關文件

- [掃描去重問題](./wails-scan-duplicate.md)
- [Wails E2E 完整踩坑](../../docs/茶包射手/wails-e2e-scan.md)
