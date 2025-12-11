# Copilot Instructions - 女優分類系統

## 語言規範
- 所有回應使用繁體中文 (zh-TW)
- 術語對照：create=建立, object=物件, code=程式碼, library=函式庫, package=套件, class=類別, function=函式

## 專案資訊
- Python 3.11+ / Tkinter GUI 桌面應用
- 主進入點：`run.py`
- 版本：v5.4.3

## 架構
- `src/models/` - 資料模型（IncrementalJSONDB）
- `src/services/` - 業務邏輯（ClassifierCore, WebSearcher）
- `src/scrapers/` - 爬蟲（AVWikiScraper, ChibafScraper, JAVDBScraper）
- `src/ui/` - GUI 介面

## 重要規範
1. 長時間操作使用背景執行緒
2. GUI 更新使用 `root.after()` 回主執行緒
3. 日誌使用 emoji 前綴（🚀開始 ✅成功 ❌失敗 ⚠️警告）
4. 級聯搜尋順序：AV-WIKI → chiba-f → JAVDB
