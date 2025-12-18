# 片商分類邏輯改進提案

## 📊 基於數據分析的發現

### 女優片商分佈統計 (504 位女優)
- **77 位 (37%)** - 專屬 1 個片商
- **38 位 (18%)** - 跨 2 個片商
- **91 位 (44%)** - 跨 3+ 個片商

### 關鍵發現

1. **專屬女優** (100% 單一片商)
   - S1: 21 位專屬女優（山手梨愛 22部、村上悠華 20部）
   - SOD: 9 位專屬女優
   - MOODYZ: 6 位專屬女優
   - FALENO: 5 位專屬女優

2. **高忠誠度女優** (70%+ 集中度)
   - 石川澪: MOODYZ 81.1% (53部中43部)
   - 水卜さくら: MOODYZ 80.8% (73部中59部)
   - 高橋しょう子: MOODYZ 85.7% (28部中24部)
   - 瀧本雫葉: PRESTIGE 87.0% (23部中20部)

3. **跨片商女優** (無法有效分類)
   - あけみみう: 45 片商 (主要 SOD 僅 10.1%)
   - 鳳みゆ: 43 片商 (主要 FALENO 僅 12.1%)
   - 逢沢みゆ: 37 片商 (主要 S1 僅 8.7%)

---

## 🔧 現有邏輯問題

### analyze_actress_primary_studio (json_database.py L1651-1792)

```python
# 現有分類條件
if best_stats["total_count"] >= 3 and confidence >= 70:
    recommendation = "studio_classification"
elif best_stats["total_count"] >= 1 and minor_studio_work_count < 10:
    recommendation = "studio_classification"
```

### 問題分析

| 問題 | 說明 |
|------|------|
| 未考慮片商數量 | 1 片商 vs 45 片商的女優用同樣邏輯判斷 |
| 信心度門檻固定 | 70% 對跨片商女優毫無意義 |
| 無「無法分類」選項 | 強制所有人進入片商或單體企劃 |
| 未利用專屬女優資訊 | 100% 專屬女優應該直接分類 |

---

## 📐 改進提案：三層分類策略

### 第一層：專屬女優快速通道
```python
def is_exclusive_actress(studio_stats: dict, total_videos: int) -> tuple[bool, str]:
    """檢查是否為專屬女優（100% 單一片商）"""
    if len(studio_stats) == 1 and total_videos >= 3:
        studio = list(studio_stats.keys())[0]
        return True, studio
    return False, None
```

**條件**：
- 只有 1 個片商
- 至少 3 部影片
- **直接分類到該片商**，無需計算信心度

### 第二層：高忠誠度女優
```python
def is_high_loyalty_actress(studio_stats: dict, total_videos: int, major_studios: set) -> tuple[bool, str, float]:
    """檢查是否為高忠誠度女優（>=70% 集中於大片商）"""
    for studio, stats in studio_stats.items():
        if studio in major_studios:
            confidence = (stats["total_count"] / total_videos) * 100
            if confidence >= 70 and stats["total_count"] >= 5:
                return True, studio, confidence
    return False, None, 0
```

**條件**：
- 大片商作品占比 >= 70%
- 大片商作品數量 >= 5 部
- **分類到該大片商**

### 第三層：跨片商女優判定
```python
def is_multi_studio_actress(studio_stats: dict) -> bool:
    """判斷是否為跨片商女優（無法有效分類）"""
    studio_count = len(studio_stats)
    
    # 跨 5+ 片商，幾乎無法分類
    if studio_count >= 5:
        return True
    
    # 跨 3+ 片商且沒有明顯主導（最高占比 < 40%）
    if studio_count >= 3:
        max_ratio = max(s["total_count"] for s in studio_stats.values()) / sum(s["total_count"] for s in studio_stats.values())
        if max_ratio < 0.4:
            return True
    
    return False
```

**結果**：標記為 `solo_artist`（單體企劃女優）

---

## 📊 新分類流程圖

```
開始分析女優
     │
     ▼
┌────────────────────┐
│ 是否專屬女優？       │
│ (1 片商 & >= 3 部)  │
└────────┬───────────┘
         │ 是
         ▼
    ✅ 直接分類到該片商
    信心度 = 100%
         │
         │ 否
         ▼
┌────────────────────┐
│ 是否高忠誠度女優？   │
│ (大片商 >= 70%)     │
└────────┬───────────┘
         │ 是
         ▼
    ✅ 分類到該大片商
    信心度 = 實際占比
         │
         │ 否
         ▼
┌────────────────────┐
│ 是否跨片商女優？     │
│ (5+ 片商 或         │
│  3+ 片商且無主導)   │
└────────┬───────────┘
         │ 是
         ▼
    🎭 歸入單體企劃
    信心度 = 0%
         │
         │ 否
         ▼
    📊 使用現有邏輯
    計算最佳片商
```

---

## 🔢 新舊邏輯對比

| 女優 | 影片數 | 片商數 | 舊邏輯 | 新邏輯 |
|------|-------|-------|--------|--------|
| 山手梨愛 | 22 | 1 | S1 (計算) | S1 (專屬, 100%) |
| 石川澪 | 53 | 5 | MOODYZ (81%) | MOODYZ (高忠誠, 81%) |
| あけみみう | 89 | 45 | SOD (10%) | 單體企劃 (跨片商) |
| 鳳みゆ | 66 | 43 | FALENO (12%) | 單體企劃 (跨片商) |
| 設楽ゆうひ | 30 | 4 | KAWAII (80%) | KAWAII (高忠誠, 80%) |

---

## 💻 實作建議

### 修改 analyze_actress_primary_studio()

```python
def analyze_actress_primary_studio(
    self, actress_name: str, major_studios: set = None
) -> dict:
    # ... 統計片商分布 ...
    
    studio_count = len(studio_stats)
    
    # 第一層：專屬女優快速通道
    if studio_count == 1 and total_videos >= 3:
        studio = list(studio_stats.keys())[0]
        return {
            "actress_name": actress_name,
            "primary_studio": studio,
            "confidence": 100.0,
            "total_videos": total_videos,
            "studio_distribution": studio_stats,
            "recommendation": "studio_classification" if studio in major_studios else "solo_artist",
            "classification_type": "exclusive",  # 新增：分類類型
        }
    
    # 第二層：高忠誠度女優
    if major_studios:
        for studio, stats in studio_stats.items():
            if studio in major_studios:
                confidence = (stats["total_count"] / total_videos) * 100
                if confidence >= 70 and stats["total_count"] >= 5:
                    return {
                        "actress_name": actress_name,
                        "primary_studio": studio,
                        "confidence": round(confidence, 1),
                        "total_videos": total_videos,
                        "studio_distribution": studio_stats,
                        "recommendation": "studio_classification",
                        "classification_type": "high_loyalty",
                    }
    
    # 第三層：跨片商女優
    if studio_count >= 5:
        # 跨 5+ 片商，直接歸入單體企劃
        best_studio = max(studio_stats.items(), key=lambda x: x[1]["total_count"])[0]
        return {
            "actress_name": actress_name,
            "primary_studio": best_studio,
            "confidence": 0.0,  # 信心度為 0 表示無法有效分類
            "total_videos": total_videos,
            "studio_distribution": studio_stats,
            "recommendation": "solo_artist",
            "classification_type": "multi_studio",
            "studio_count": studio_count,
        }
    
    if studio_count >= 3:
        max_ratio = max(s["total_count"] for s in studio_stats.values()) / total_videos
        if max_ratio < 0.4:
            # 跨 3+ 片商且無主導，歸入單體企劃
            best_studio = max(studio_stats.items(), key=lambda x: x[1]["total_count"])[0]
            return {
                "actress_name": actress_name,
                "primary_studio": best_studio,
                "confidence": round(max_ratio * 100, 1),
                "total_videos": total_videos,
                "studio_distribution": studio_stats,
                "recommendation": "solo_artist",
                "classification_type": "multi_studio",
                "studio_count": studio_count,
            }
    
    # 第四層：使用現有邏輯
    # ... 現有邏輯 ...
```

---

## 📈 預期效果

### 分類準確度提升

| 類型 | 女優數 | 預期改善 |
|------|-------|---------|
| 專屬女優 | 77 位 | 100% 直接正確分類 |
| 高忠誠度女優 | ~30 位 | 減少誤判到單體企劃 |
| 跨片商女優 | ~60 位 | 避免錯誤分類到單一片商 |

### 分類速度提升
- 專屬女優跳過複雜計算
- 減少不必要的信心度計算

---

## ⚠️ 注意事項

1. **向後相容**：新增 `classification_type` 欄位，不影響現有流程
2. **可調參數**：門檻值（70%、5部、40%）應可配置
3. **日誌記錄**：新增分類類型到日誌，便於追蹤

---

## 🗓️ 實作優先順序

1. **Phase 1**：專屬女優快速通道（影響最大，實作最簡單）
2. **Phase 2**：跨片商女優判定（避免錯誤分類）
3. **Phase 3**：高忠誠度女優優化
4. **Phase 4**：參數可配置化
