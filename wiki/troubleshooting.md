---
name: 故障排除
description: 以症狀為起點的反向索引——遇到什麼現象就翻到對應 pitfall
date: 2026-05-02
---

# 故障排除（症狀 → 對應頁）

> 這頁是給「我遇到 X，怎麼辦？」設計的反向查表。  
> 如果你是新來的，先看 [getting-started.md](getting-started.md) 了解整體脈絡，再回來這頁查症狀。  
> 一個症狀可能對應多個原因，依「最常見 → 較少見」排序。

---

## 資料庫 / 設定

| 症狀 | 對應頁 | 驗證 fix 是否在你的 build |
|------|--------|---------------------------|
| 在 GUI 改了 DB 路徑、按儲存，後續操作仍走舊路徑（要重啟才生效） | [wails-dbonce-no-reset](pitfalls/wails-dbonce-no-reset.md) | `Select-String "dbMu sync.Mutex" wails-app\backend\app.go` |
| 搜尋一直發 HTTP，`data.journal` 有東西、但 `data.json` 永遠是舊的或空的 | [wails-db-json-never-updated](pitfalls/wails-db-json-never-updated.md) | `Select-String "Compact\(\)\|CompactIfNeeded\(\)" wails-app\backend\app.go` 應命中 ≥3 處 |
| 重啟 app 後資料消失；DB 跑去 `wails-app\build\bin\data\json_db\` | [wails-db-path-wrong-dir](pitfalls/wails-db-path-wrong-dir.md) | `Select-String '\"\\.\\.\", \"\\.\\.\", \"\\.\\.\", \"config.ini\"' wails-app\backend\app.go` 應命中 |
| `data.json` 同時出現 `success` 與 `searched_found` 兩種狀態 | [wails-db-format-migration](pitfalls/wails-db-format-migration.md) | `Select-String '\"searched_found\"' wails-app\backend\app.go` 應命中（不應再寫 `\"success\"`） |
| 前端顯示「已搜尋」但後端認為未找到（或反過來） | [wails-cache-status-mismatch](pitfalls/wails-cache-status-mismatch.md) | — |

## 搜尋

| 症狀 | 對應頁 | 驗證 fix 是否在你的 build |
|------|--------|---------------------------|
| 一輪批次搜尋要跑 70+ 秒（理論值約 10 秒） | [wails-search-perf](pitfalls/wails-search-perf.md) | `Select-String "min_interval = 0" src\scrapers\run_batch_search.py` 應命中 |
| 搜尋來源欄位（`search_method`）永遠空白 | [python-search-method-field-mismatch](pitfalls/python-search-method-field-mismatch.md) | `Select-String '\"search_method\"' src\scrapers\run_batch_search.py` 應命中、且不再用 `\"method\"` |
| JAVDB 把 `WTB-045` 寫成 `AWTB-005` 之類相似番號的資料 | [javdb-false-positive](pitfalls/javdb-false-positive.md) | `Select-String "expected_code" src\services\safe_javdb_searcher.py` 應命中 |
| 連跑 cascade → AV-WIKI → JAVDB 後分類，部分番號落入「未分類」 | [wails-source-search-clears-results](pitfalls/wails-source-search-clears-results.md) | `Select-String "clearSearchResults" wails-app\frontend\src\App.tsx` 不應在 `runSourceSearch` 內 |
| 同番號掃描出現多次、搜尋次數爆增 | [wails-scan-duplicate](pitfalls/wails-scan-duplicate.md) | `Select-String "seen\[code\]" wails-app\backend\app.go` 應命中 |

## 移動 / 分類

| 症狀 | 對應頁 | 驗證 fix 是否在你的 build |
|------|--------|---------------------------|
| 對已分類過的檔案再執行一次分類，原檔被刪除 | [wails-move-same-path-delete](pitfalls/wails-move-same-path-delete.md) | `Select-String "absSrc == absDst" wails-app\backend\app.go pkg\mover\file_move.go` 兩處皆命中 |
| 移動成功但二次移動報「找不到」 | [wails-move-stale-paths](pitfalls/wails-move-stale-paths.md) | 前端 store 行為，無單一 grep；確認 `App.tsx` 在 `BatchMove` 後有更新 `scanResults` |
| 「片商分類」把 SOD star 歸到「單體企劃女優」 | [wails-studio-canonical-match](pitfalls/wails-studio-canonical-match.md)（問題 A ✅、問題 B ⚠️） | A：`Select-String "strings.ToUpper" wails-app\backend\app.go` 應命中 `canonicalMajorStudio` 區段；B：3 層 fallback 仍未實作（請用 `setup.ps1` portable bundle） |
| 片商識別整體失效，所有片商顯示 UNKNOWN | [wails-dist-missing-studio-data](pitfalls/wails-dist-missing-studio-data.md) | EXE 同目錄需有 `studios.json` / `major_studios.json`；裸 `wails build` 後請改跑 `setup.ps1` |
| 分類資料夾出現片名碎片 / 拼接字串 / 多人共演對話框內容亂掉 | [wails-actress-classification-polluted-candidates](pitfalls/wails-actress-classification-polluted-candidates.md) | `Select-String "_extract_actresses_from_text\|_scan_avwiki_text_for_actresses" src\services\web_searcher.py` 不應命中（已 fail-closed） |

## 番號提取

| 症狀 | 對應頁 | 驗證 fix 是否在你的 build |
|------|--------|---------------------------|
| `[SKMJ-310]` 之類括號番號被清空、`200GANA-3376` 數字前綴被切掉 | [go-extractor-bracket-format](pitfalls/go-extractor-bracket-format.md) | `Select-String "bracketCodeRe" pkg\extractor\extractor.go` 應命中 |

## 建置 / 發行

| 症狀 | 對應頁 | 驗證 fix 是否在你的 build |
|------|--------|---------------------------|
| `wails build` 報 npm peer dependency / TS namespace 衝突 | [wails-build-issues](pitfalls/wails-build-issues.md) | — |
| 直接複製 `actress-classifier.exe` 出去，片商功能整個壞掉 | [wails-dist-missing-studio-data](pitfalls/wails-dist-missing-studio-data.md) | 改跑 `setup.ps1` 產出 `dist\portable\` 完整 bundle |
| GitHub Actions workflow 沒按 schedule 跑、scope guard / Go API 編譯失敗 | [github-actions-issues](pitfalls/github-actions-issues.md) | — |

## Wiki / 開發工具

| 症狀 | 對應頁 |
|------|--------|
| 雙擊 `wiki/viewer.html` 看到「Failed to fetch」 | [viewer-file-cors](pitfalls/viewer-file-cors.md) |
| 改完 `.md` 後 viewer 側欄沒有新頁面 | 跑 `python wiki/gen_data.py`；歷史背景 [wiki-viewer-nav-out-of-sync](pitfalls/wiki-viewer-nav-out-of-sync.md) |
| `gen_data.py` 在 Windows 跑出 `UnicodeEncodeError` | 用 `$env:PYTHONIOENCODING='utf-8'; python wiki\gen_data.py` 重跑 |

---

## 找不到對應症狀？

1. 先到 [index.md](index.md) 看完整目錄。
2. 用瀏覽器在 `viewer.html` 打開後 `Ctrl+F` 全文搜尋（內容已透過 wiki-data.js 內嵌）。
3. 看 [log.md](log.md) 有沒有最近的修復紀錄。
4. 確認你拿到的是哪個 commit / branch — 部分 pitfall 在新 build 已修復，舊 build 仍會踩。

如果是新發現的問題，請按 [pitfalls/](pitfalls/) 既有頁面格式記錄，並更新 `log.md` 與本頁的查表。
