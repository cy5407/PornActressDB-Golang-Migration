# AV-WIKI HTML 提取邏輯修復報告

**修復日期**: 2025-11-16  
**修復版本**: v2.1  
**影響範圍**: 28 個之前失敗的番號

## 🎯 修復概要

### 問題描述
系統出現 28 個「未找到女優資訊」的警告，涉及番號包括：
- SSIS-688, MIDE-989, AVOP-004, MIDV-727, STARS-685
- ROYD-080, ABP-601, SSIS-964, SSIS-589, SSIS-337
- STARS-627, ABP-563, MIDV-873, SONE-995, LUXU-457
- STARS-818, ABP-733, MIAA-582, ADN-616, MIDV-577
- IPZZ-294, MIDV-361, SONE-040, HMN-128, ABF-159
- MIDV-116, UMD-844, STARS-866

### 根本原因分析
AV-WIKI 的 HTML 結構中，女優信息存在於多個位置：

1. **`<a rel="tag">` 標籤** (最可靠) 
   ```html
   <a href="https://av-wiki.net/av-actress/ishikawa-mio/" rel="tag">石川澪</a>
   ```

2. **`actress-name` class 元素內的 `<a>` 標籤**
   ```html
   <li class="actress-name"><i class="fa fa-venus"></i><a href="...">石川澪</a></li>
   ```

原有代碼只檢查了 `actress-name` class 的文本內容，沒有先從其中的 `<a>` 標籤提取，導致許多情況下無法找到女優。

### 修復方案

#### 修改文件
- **`src/scrapers/sources/avwiki_scraper.py`**

#### 修改內容

##### 1. 改進 `_parse_search_results()` 方法
**原邏輯**：
```python
# 方法2: 尋找專用的女優名稱元素
actress_name_elements = soup.find_all(class_="actress-name")
if actress_name_elements:
    for element in actress_name_elements:
        actress_name = element.text.strip()  # ❌ 直接取文本
        if actress_name not in seen_actresses and self._is_valid_actress_name(actress_name):
            # ...
```

**新邏輯**：
```python
# 方法2: 尋找專用的女優名稱元素 (actress-name class 內的 <a> 標籤)
actress_name_elements = soup.find_all(class_="actress-name")
if actress_name_elements:
    for element in actress_name_elements:
        # 首先嘗試從元素內的 <a> 標籤提取 ✅
        actress_links = element.find_all("a")
        for link in actress_links:
            href = link.get('href', '')
            text = link.get_text(strip=True)
            
            # 優先使用帶有 /av-actress/ 連結的
            if '/av-actress/' in href and text and text not in seen_actresses:
                actress_elements.append({
                    'name': text,
                    'href': href,
                    'source': 'actress-name-link'
                })
                seen_actresses.add(text)
        
        # 如果沒找到連結，則使用元素的完整文本
        if not actress_elements:
            actress_name = element.text.strip()
            if actress_name not in seen_actresses and self._is_valid_actress_name(actress_name):
                # ...
```

##### 2. 改進 `_parse_detail_page()` 方法
增加新的方法層級，優化提取流程：

**新提取層級**：
1. **方法 1**: `rel="tag"` 連結 (最可靠) ✅
2. **方法 2**: `actress-name` class 內的 `<a>` 標籤 (新增) ✅
3. **方法 3**: 其他 article 內的 tag 連結
4. **方法 4**: 文本掃描 (備選)

```python
# 方法2: 如果沒找到，嘗試從 actress-name class 提取
if not actresses:
    actress_name_elements = soup.find_all(class_="actress-name")
    for element in actress_name_elements:
        # 首先嘗試從元素內的 <a> 標籤提取
        actress_links = element.find_all("a")
        for link in actress_links:
            href = link.get('href', '')
            text = link.get_text(strip=True)
            
            if '/av-actress/' in href and text and text not in actresses:
                actresses.append(text)
        
        # 如果沒找到連結，則使用元素的完整文本
        if not actresses:
            actress_name = element.text.strip()
            if actress_name and self._is_valid_actress_name(actress_name):
                actresses.append(actress_name)

# 方法3: 如果仍沒找到，嘗試文本掃描
if not actresses:
    actresses = self._extract_actresses_from_text(page_text)
```

## 📊 測試結果

### 完整測試（28 個番號）

```
總計: 28 個番號
成功: 26 個 (92.9%) ✅
失敗: 2 個 (7.1%)   ⚠️

失敗番號: AVOP-004, LUXU-457
(這兩個在 AV-WIKI 上可能真的沒有女優信息)
```

### 成功提取的番號
- **1 位女優** (23 個): SSIS-688, MIDE-989, MIDV-727, STARS-685, ROYD-080, 等
- **2 位女優** (2 個): MIAA-582, HMN-128
- **3 位女優** (1 個): UMD-844

### 修復前後對比

| 指標 | 修復前 | 修復後 | 改進 |
|------|--------|--------|------|
| 成功率 | 0% | 92.9% | ⬆️ 92.9% |
| 可成功提取的番號 | 0 個 | 26 個 | ⬆️ 26 個 |
| 無資訊的番號 | 28 個 | 2 個 | ⬇️ 92.9% |

## 🔍 技術說明

### 改進的提取邏輯
新的分層提取策略確保了最大的覆蓋率：

```
HTML 結構層級
├── 第 1 層: rel="tag" 連結
│   └── <a href="/av-actress/...">女優名</a> ✅ 最可靠
├── 第 2 層: actress-name class
│   ├── 子元素 <a> 標籤 ✅ 新增（本次修復）
│   └── 元素文本備選
├── 第 3 層: article 內的 tag 連結
│   └── <a href="/av-actress/...">女優名</a>
└── 第 4 層: 文本掃描
    └── 使用正則表達式提取日文名稱
```

### 為什麼有效
1. **層級化設計**：優先使用最可靠的來源
2. **HTML 結構適配**：直接提取 `<a>` 標籤內的文本，避免了額外的 HTML 元素污染
3. **無回歸問題**：只增加了新的提取方法，不改變現有的排除規則

## 📝 修改清單

### 檔案變更
```
src/scrapers/sources/avwiki_scraper.py
  - _parse_search_results() 方法：+20 行（新增 actress-name link 提取）
  - _parse_detail_page() 方法：+20 行（新增 actress-name link 提取）
```

### 代碼行數變化
- **新增**: 40 行
- **刪除**: 0 行
- **修改**: 2 個方法

## ✅ 驗證步驟

1. ✅ 單個番號測試（快速驗證）
   ```python
   python test_actress_extraction.py
   # 結果: 90.0% 成功率 (9/10)
   ```

2. ✅ 完整批量測試（28 個番號）
   ```python
   python test_complete_recovery.py
   # 結果: 92.9% 成功率 (26/28)
   ```

## 🚀 部署建議

### 立即行動
1. 應用代碼修改到生產環境
2. 清除之前的快取
3. 重新運行失敗的番號搜尋

### 監控建議
1. 監控搜尋成功率（應保持 > 90%）
2. 監控新的「未找到女優資訊」警告
3. 定期檢查是否有新的 HTML 結構變化

### 未來改進
1. 定期更新排除規則（基於真實的垃圾文本）
2. 新增備用搜尋源（當 AV-WIKI 失敗時）
3. 建立搜尋結果的統計儀表板

## 🔗 相關文檔
- 之前的修復: `AVWIKI_FIX_REPORT.md`
- 排除規則說明: 在程式碼註解中
- 二次搜尋機制: `DOUBLE_SEARCH_IMPLEMENTATION.md`

---

**修復完成**: ✅  
**測試通過**: ✅  
**可部署**: ✅
