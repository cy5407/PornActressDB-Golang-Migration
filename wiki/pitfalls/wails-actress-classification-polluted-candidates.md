---
category: Wails / 搜尋鏈
date: 2026-04-22
---
# 女優分類在過濾前判斷多人共演，會把污染字串與 AV-WIKI 純文字 fallback 一起放大成錯誤資料夾

## 症狀

Windows / Wails GUI 在做一般「女優分類 / 移動」時，會出現兩類表面症狀：

1. 明明 DB 或搜尋結果裡有女優資料，仍被移到 `未分類`
2. `Z:\分類` 底下被建立出明顯不是女優名的資料夾，例如片名碎片、宣傳語、拼接字串

實際觀察到的污染例子包含：

- `可愛い顔した魔性少女がおっぱ`
- `田舎帰省で成長期の姪っ子と自`
- `幼馴染と結婚したら`
- `同窓会でネトラレてるのにいっ`
- `手を繋`
- `木下ひまり #森沢かな #橘メアリー #百永さりな`

另外也曾出現本來有女優資料卻落入 `未分類` 的番號，例如：

- `WAAA-609`
- `WAAA-628`
- `XVSR-796`
- `YMDD-469`
- `YUJ-019`
- `ZOCM-042`

## 根因

這次不是單一 bug，而是四層問題連鎖放大。

### 1. 前端分類只吃 `searchResults`，缺資料就直接掉進 `未分類`

`App.tsx` 的一般女優分類原本依賴前端記憶體中的 `searchResults` 建立 `code -> actress` 對應。只要某筆沒有進到 store，就會 fallback 成 `未分類`。

這會把「前面搜尋資料流少了一筆」誤判成「真的沒有女優」。

### 2. DB fallback 失敗時，後端原本把 `ensureDB()` 錯誤吃掉

前端後來改成缺 `searchResults` 時去呼叫 `DbGetVideo()` 補資料，但如果 DB 初始化 / 載入失敗，後端原本會吞掉錯誤，前端看到的只剩空值或模糊狀態。

結果就會再次把「DB 壞掉 / 沒載入成功」誤判成「沒有女優資料」。

### 3. 多人共演判斷做在清洗前，污染字串會先被當成候選女優

這是使用者在 Windows 實機中抓到的真正核心：

```text
原本流程（錯誤）：
actresses -> 直接判斷是否多人 -> 再使用候選名單
```

如果 `actresses` 裡混入片名碎片、宣傳語、黏在一起的字串，就會出現：

- 單女優片被誤判成多人共演
- dialog 顯示污染選項
- 使用者一旦選錯，或 fallback 直接取第一位，就建立錯誤女優資料夾

正確順序必須是：

```text
searchResults / DbGetVideo() -> 先清洗候選名單 ->
0 位: 未分類
1 位: 直接分類
2 位以上: 才彈多人共演對話框
```

### 4. AV-WIKI 上游 parser 會在沒有結構化 actress link 時，用全文文字猜女優

真正把污染字串灌進 `actresses` 的高風險來源，不只是前端判斷式，而是 AV-WIKI 上游資料本身就可能已經髒掉。

本次調查確認：

- Wails / Windows 主線 AV-WIKI 搜尋實際走的是 `src/services/web_searcher.py`
- repo 內另一套 `src/scrapers/sources/avwiki_scraper.py` 也存在類似 fallback

高風險行為是：

- 對整頁 `soup.get_text()` 做全文掃描
- 或把 `.actress-name` 容器裡的純文字直接當女優

這會把片名片段、宣傳文案、鄰近內文一起誤抓進 `actresses`

## 修正

### 第一層：缺 `searchResults` 時改查 DB fallback

- 前端一般女優分類缺資料時，先呼叫 `DbGetVideo()` 補回 `actresses`
- 不再因為前端 store 少一筆就直接進 `未分類`

### 第二層：DB fallback 失敗時 fail-closed，中止整批分類

- `ensureDB()` 改為回傳 error，而不是吞掉
- `DbGetVideo()` / `DbListVideos()` 傳遞初始化失敗
- 前端若任何一筆 fallback DB lookup 出錯，整批分類直接中止

目標是避免把系統故障偽裝成「沒有女優資料」。

### 第三層：多人共演判斷改成吃「清洗後」的候選名單

前端 `classification.ts` 新增 / 收斂的規則包括：

- 先清洗候選女優名，再決定 0/1/多位
- 保留多人共演偏好記憶 wiring
- 加入可信保留名單
- 加入已知污染字串黑名單
- 避免把像 `三田` 這種從 `三田真鈴` 錯切出的污染片段當成獨立女優

本輪使用者更正後的保留名單為：

- `瀧本雫葉`
- `蒼乃美月`
- `綾瀬天`
- `東雲すみれ`
- `五芭`
- `天然美月`

### 第四層：AV-WIKI 改成結構化優先，沒有結構化證據就 fail-closed

本次把 AV-WIKI parser 收斂成像 JAVDB 一樣的方向：

只接受結構化 actress link，例如：

- `a[rel="tag"]` 且 `href` 含 `/av-actress/`
- `.actress-name` 容器內、且 `href` 含 `/av-actress/` 的 link

不再接受：

- `.actress-name` 的純文字 fallback
- 全頁文字掃描 `_scan_avwiki_text_for_actresses()`
- `_extract_actresses_from_text(page_text)` 這類全文猜測

這次還補了一個容易漏掉的邏輯洞：

- `WebSearcher._extract_avwiki_actresses()` 不能在抓到 `rel="tag"` 後就提早 return
- 否則混合結構頁面會漏掉只存在 `.actress-name a` 的另一位女優
- 修正後改成合併收集兩種結構化來源的聯集

## 涉及檔案

### 前端 / Wails

- `wails-app/frontend/src/App.tsx`
- `wails-app/frontend/src/lib/classification.ts`
- `wails-app/frontend/tests/classification.test.ts`

### Go backend

- `wails-app/backend/app.go`
- `wails-app/backend/app_test.go`

### Python / AV-WIKI parser

- `src/services/web_searcher.py`
- `src/scrapers/sources/avwiki_scraper.py`
- `tests/test_coverage_web_searcher.py`
- `tests/test_avwiki_scraper.py`
- `tests/test_coverage_avwiki_scraper.py`

## 修復 commit

這次實際分成四批修：

- `fd1685b` — `fix: abort actress classification when db fallback fails`
- `6967dd9` — `fix: restore actress move fallback and multi-actress choices`
- `8b75e75` — `fix: filter polluted actress candidates before multi-choice`
- `d1e9d99` — `fix: make avwiki actress extraction fail closed`

## 驗證重點

### 前端

- 缺 `searchResults` 時會抓 DB fallback
- 清洗後 0 位才進 `未分類`
- 清洗後 1 位直接分類
- 清洗後 2 位以上才進多人共演 dialog
- 多人共演偏好記憶仍保留

### Python / AV-WIKI

已驗證：

```bash
./venv/bin/python -m pytest \
  tests/test_avwiki_scraper.py \
  tests/test_coverage_avwiki_scraper.py \
  tests/test_coverage_web_searcher.py \
  tests/test_split_search_entrypoints.py -q
```

結果：`178 passed`

另外補了主線 WebSearcher 的 mixed-structure 測試，確認：

- 沒有 tag link 時，`.actress-name a` 仍可抓到
- 同頁同時有 `rel="tag"` 與 `.actress-name a` 時，會回傳聯集
- 沒有結構化 link 時，不會再觸發 text scan

## 預防

1. 女優分類不能把「資料缺失 / 載入失敗」直接當成「未分類」
2. 多人共演判斷必須做在清洗後名單，而不是原始 `actresses`
3. 對分類系統來說，precision 優先於 recall；寧可 fail-closed，也不要把片名碎片寫成正式女優資料夾
4. 調查 scraper 問題時，要先追 runtime 真正生效的是哪一條路徑，不要只修 repo 內另一套看起來更完整、但主線沒在用的 parser
5. AV-WIKI 這種來源若沒有結構化 actress link，應視為「證據不足」，不要再用全文猜名字
