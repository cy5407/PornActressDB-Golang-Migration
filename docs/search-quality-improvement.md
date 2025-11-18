# AV-WIKI 搜尋品質改進方案

## 問題分析

### 當前問題
番號 `SAVR-00410` 的女優欄位包含大量非女優資訊：
- 片商名稱（如：`シロウト逸材発掘`）
- 網站/系列名稱（如：`ラポルノリコピンルナティックス`）
- 標籤/分類（如：`系パコパコ`、`炉利`）

### 根本原因
1. `_extract_actresses_from_text()` 使用寬鬆的正則表達式抓取所有日文字串
2. `_is_valid_actress_name()` 排除清單不完整
3. 批次併發搜尋直接使用解析結果，未進行二次驗證

---

## 解決方案

### 方案 A：嚴格驗證模式（推薦）

**優點**：
- 大幅降低誤判率
- 提升資料品質
- 減少後續手動修正工作

**缺點**：
- 可能漏掉一些真實女優
- 需要維護更完整的排除清單

**處理邏輯**：
1. **搜尋階段**：使用更嚴格的女優名稱驗證
2. **儲存階段**：
   - 如果找到 0 位女優 → 標記為 `actresses: []`，`search_status: 'searched_no_actress'`
   - 如果找到疑似錯誤資料（>10 位女優）→ 標記為 `search_status: 'searched_suspicious'`
3. **再次搜尋規則**：
   - `actresses: []` → **可以再次搜尋**（可能是網站暫時問題）
   - `actresses: ['XXXX']` → **跳過**（已標記為無法識別）
   - `search_status: 'searched_suspicious'` → **可以再次搜尋**（需要人工確認）

---

### 方案 B：寬鬆驗證 + 人工審核

**優點**：
- 不會漏掉女優
- 保留所有可能資訊

**缺點**：
- 需要大量人工審核
- 資料庫品質較低

**處理邏輯**：
1. 儲存所有搜尋結果
2. 標記 `needs_review: true` 當女優數量異常
3. 提供批次審核介面

---

### 方案 C：多層級驗證（最佳方案）

結合 A 和 B 的優點：

1. **第一層：嚴格驗證**
   - 使用完整的排除清單
   - 限制女優名稱長度（2-8 字元）
   - 排除包含特定字詞的項目

2. **第二層：數量檢查**
   - 0 位女優 → `search_status: 'no_actress_found'`
   - 1-3 位女優 → `search_status: 'searched_found'`（正常）
   - 4-10 位女優 → `search_status: 'searched_multiple'` + `needs_review: true`
   - >10 位女優 → `search_status: 'search_error'` + `actresses: []`（清空）

3. **第三層：再次搜尋規則**
   ```python
   should_research = (
       video['search_status'] == 'no_actress_found' or
       video['search_status'] == 'search_error' or
       video.get('actresses') == [] or
       (video.get('actresses') == ['XXXX'] and user_confirmed)
   )
   ```

---

## 建議實作

### 1. 擴充排除清單

新增以下分類到 `_is_valid_actress_name()`：

```python
exclude_keywords = [
    # 現有關鍵詞
    'SOD', 'STARS', 'FANZA', 'MGS', 'MIDV', 'SSIS', 'IPX', 'IPZZ',
    
    # 片商/系列名稱
    'シロウト', 'しろうと', 'エスワン', 'プレステージ', 'アイポケ', 'ムーディーズ',
    'マキシング', 'アタッカーズ', 'マドンナ', 'プレミアム', 'ファレノ',
    'なまハメ', 'ハメ撮り', 'パコパコ', 'ナンパ', 'マジックミラー',
    
    # 網站/平台
    'ギャラリー', 'チャンネル', 'ドリームチケット', 'レーベル', 'プロジェクト',
    'グループ', 'クラブ', 'サークル', 'カンパニー', 'スタジオ',
    
    # 分類/標籤
    '素人', '人妻', '巨乳', '美少女', '制服', 'コスプレ', 'ドキュメント',
    '企画', '単体', '配信', '限定', 'オリジナル', 'セレクト',
    
    # 動作/描述
    '逸材', '発掘', '系', '専科', '倶楽部', '同好会', '研究所',
    
    # 過長關鍵詞（通常是組合詞）
    'ラビリンス', 'ルナティックス', 'リコピン', 'ポルノ', 'ラポ',
]

# 長度限制
if len(name) > 8:  # 女優名稱通常不超過 8 字元
    return False
```

### 2. 新增搜尋狀態

修改資料結構，添加更多狀態：

```json
{
  "code": "SAVR-00410",
  "actresses": [],
  "search_status": "search_error",
  "search_error_reason": "too_many_results",
  "needs_review": true,
  "last_search_date": "2025-11-15T10:30:00"
}
```

### 3. 再次搜尋邏輯

```python
def should_research(video_info: dict) -> bool:
    """判斷是否需要再次搜尋"""
    
    # 從未搜尋過
    if not video_info.get('search_status'):
        return True
    
    # 搜尋錯誤
    if video_info['search_status'] in ['search_error', 'no_actress_found']:
        return True
    
    # 空的女優列表（可能是暫時問題）
    if not video_info.get('actresses'):
        return True
    
    # 標記為 XXXX（人工確認後可再搜尋）
    if video_info.get('actresses') == ['XXXX']:
        # 需要用戶確認
        return ask_user_confirmation(video_info['code'])
    
    # 可疑結果（超過 10 位女優）
    if video_info['search_status'] == 'searched_multiple':
        # 需要用戶確認
        return ask_user_confirmation(video_info['code'])
    
    # 已找到正常結果
    return False
```

---

## 實作優先順序

### 第一階段（立即修復）
1. ✅ 擴充 `exclude_keywords` 清單
2. ✅ 添加女優名稱長度限制（2-8 字元）
3. ✅ 添加搜尋結果數量檢查

### 第二階段（品質提升）
1. ⏳ 添加 `search_status` 欄位
2. ⏳ 實作再次搜尋邏輯
3. ⏳ 修正現有錯誤資料（如 SAVR-00410）

### 第三階段（使用者體驗）
1. ⏳ 添加批次審核介面
2. ⏳ 提供手動標記功能
3. ⏳ 統計報表（成功率、錯誤率等）

---

## 測試案例

### 正常案例
- `STARS-123` → 1 位女優 ✅
- `SSIS-456` → 1 位女優 ✅

### 錯誤案例
- `SAVR-00410` → >50 位"女優"（實為標籤） ❌ → 修正後應為 `[]`

### 邊界案例
- VR 片商（如 SAVR）→ 通常較難找到
- 舊番號 → 可能資料不全
- 無碼片 → AV-WIKI 可能沒有

---

## 建議採用

**推薦方案 C（多層級驗證）**，理由：
1. 平衡準確率與召回率
2. 提供清晰的錯誤狀態
3. 支援人工介入
4. 可逐步改進
