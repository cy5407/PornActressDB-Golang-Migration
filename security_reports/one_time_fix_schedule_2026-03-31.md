# 一次性修復排程

建立時間：2026-03-31 23:10 (Asia/Taipei)

依據文件：
- `security_reports/security_report_2026-03-31.pdf`
- `security_reports/fix_report_2026-03-31.pdf`

## 報告摘要

- 掃描結果總計 211 項。
- HIGH：1 項，`B324`，位置 `src/services/safe_searcher.py:194`
- MEDIUM：1 項，`B301`，位置 `src/scrapers/cache_manager.py:194`
- LOW：209 項，多數為測試中的 `assert`、`subprocess` 使用提醒與非密碼學亂數告警

## 已完成修復

- `B324 / CWE-327` 已於修復報告中標示完成。
- 修復內容：`hashlib.md5(..., usedforsecurity=False)`
- 修復位置：`src/services/safe_searcher.py:194`

## 本次一次性修復目標

本次排程僅處理尚未完成且具實際風險的項目，避免重複處理已修復內容。

1. 處理 `B301 / CWE-502`
2. 驗證 `B324` 修復仍然有效
3. 重新執行定向安全掃描並輸出結果
4. 補上修復紀錄

## 執行排程

### 2026-04-01 09:00-09:15

目標：確認既有高風險修復未被回退

工作內容：
- 檢查 `src/services/safe_searcher.py:194` 是否仍為 `usedforsecurity=False`
- 定向執行 Bandit 驗證 `B324` 不再出現

建議命令：

```powershell
python -m bandit -r src/services/safe_searcher.py
```

### 2026-04-01 09:15-10:00

目標：修復 `src/scrapers/cache_manager.py:194` 的 `pickle` 反序列化風險

工作內容：
- 優先改為 `json` 快取格式
- 若短期內無法改為 `json`，至少加上受信任來源限制、檔案完整性驗證或版本/型別檢查
- 檢查 `src/scrapers/cache_manager.py` 全檔對 `pickle` 的讀寫路徑，確認不是只修單點

完成條件：
- `B301` 不再出現在定向掃描結果中，或已有明確風險控管與註解
- 快取讀寫流程仍可正常運作

### 2026-04-01 10:00-10:20

目標：執行功能回歸驗證

工作內容：
- 驗證快取建立、讀取、失效處理
- 驗證爬蟲搜尋流程未因快取格式調整而失敗

建議命令：

```powershell
python -m pytest tests -k cache
python test_enhanced_search.py
```

### 2026-04-01 10:20-10:40

目標：重新掃描並產出最終結果

工作內容：
- 重跑 Bandit
- 更新修復報告或附上新的掃描摘要

建議命令：

```powershell
python -m bandit -r src
```

### 2026-04-01 10:40-11:00

目標：收尾與紀錄

工作內容：
- 更新 `security_reports/` 下的修復說明
- 記錄剩餘 LOW 告警哪些屬於可接受風險、哪些需後續追蹤

## 優先順序說明

- `B324` 已修復，本次只需驗證，不需再投入主要修復時段。
- `B301` 是目前唯一未完成的中風險項目，應作為本次單次排程的核心。
- LOW 告警數量雖多，但目前資訊顯示大多屬工具提醒，建議另開後續整理批次，不塞進本次一次性修復窗口。

## 本次交付標準

- `src/scrapers/cache_manager.py` 的 `pickle` 風險完成處理或降級為可接受風險
- `src/services/safe_searcher.py` 的 `B324` 修復驗證通過
- 重新掃描結果可證明 HIGH = 0，MEDIUM 至少不高於目前
- 產出新的修復摘要文件

## 備註

- 若要改成真正的自動化排程，需另外指定執行時間與執行方式。
- 目前先建立的是「一次性執行排程文件」，內容以報告現況為準，不包含 LOW 告警的大規模清理。
