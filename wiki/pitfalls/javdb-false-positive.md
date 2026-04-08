---
category: Python
date: 2026-04-06
---
# Issue 12：JAVDB False Positive（搜尋結果寫入錯誤番號）

**日期**：2026-04-06  
**嚴重度**：🔴 高（資料庫污染，難以事後察覺）

---

## 症狀

搜尋 `WTB-045` 後，資料庫寫入的是 `AWTB-005` 的女優名稱和標題。

搜尋日誌顯示「✅ 找到」，但資料內容對不上。

---

## 根本原因

### 搜尋邏輯的 Fallback 問題

舊版 `search_javdb()` 在清單頁找不到精確匹配時，會 fallback 取**第一筆結果**：

```python
# ❌ 舊版（有問題）
def search_javdb(self, code: str):
    results = self._search_list_page(code)
    
    # 嘗試找精確匹配
    exact = next((r for r in results if r["code"] == code), None)
    
    if exact:
        return self._parse_detail_page(exact["url"])
    elif results:
        # ← 問題在這：無精確匹配時取第一筆
        return self._parse_detail_page(results[0]["url"])
    return None
```

`WTB-045` 搜尋結果清單第一筆恰好是 `AWTB-005`（因為 JAVDB 的搜尋演算法相似度匹配），被錯誤寫入。

### 詳細頁缺乏二次驗證

即使進入詳細頁，舊版也沒有從頁面標題再次確認番號是否與搜尋目標一致。

---

## 修正

**兩層防護：**

### 1. 移除 fallback — 無精確匹配直接回傳 None

```python
# ✅ 修正後
def search_javdb(self, code: str):
    results = self._search_list_page(code)
    exact = next((r for r in results if r["code"].upper() == code.upper()), None)
    
    if not exact:
        return None   # ← 無精確匹配直接放棄，不取第一筆
    
    return self._parse_detail_page(exact["url"], expected_code=code)
```

### 2. 詳細頁二次驗證

```python
# ✅ _parse_detail_page 新增 expected_code 參數
def _parse_detail_page(self, url: str, expected_code: str | None = None) -> dict | None:
    soup = self._fetch_page(url)
    
    # 從頁面標題提取番號
    title = soup.find("h3", class_="title")
    page_code = self._extract_code_from_title(title.text if title else "")
    
    if expected_code and page_code:
        if page_code.upper() != expected_code.upper():
            logger.warning(f"⚠️ JAVDB 番號不符：搜尋 {expected_code}，頁面顯示 {page_code}，放棄")
            return None   # ← 二次驗證失敗
    
    # 正常解析...
```

---

## 修正前後對比

| 情況 | 修正前 | 修正後 |
|------|--------|--------|
| 精確匹配 | ✅ 正確 | ✅ 正確 |
| 無精確匹配 | ❌ 取第一筆（污染資料） | ✅ 回傳 None |
| 相似番號（AWTB-005 vs WTB-045）| ❌ 誤寫入 | ✅ 二次驗證擋下 |

---

## 影響範圍

**涉及檔案**：`src/services/safe_javdb_searcher.py`

搜尋引擎級聯順序：AV-WIKI → JAVDB，此修正只影響 JAVDB 這一層。AV-WIKI 有自己的精確匹配邏輯，不受影響。

→ 詳見 [architecture/search-engine.md](../architecture/search-engine.md)
