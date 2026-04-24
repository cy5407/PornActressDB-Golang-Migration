---
category: Go
date: 2026-04-08
---
# Extractor：`[CODE] 格式`番號被 bracketRe 清空

**日期**：2026-04-08  
**更新**：2026-04-24（補充 MGS 數字前綴提取契約）  
**嚴重度**：🟡 中（部分番號提取失敗，不影響系統穩定）

---

## 問題描述

檔名格式為 `[CODE] 女優名.mp4`（番號放在方括號內）時，
`ExtractCode()` 的 `bracketRe` 清理步驟會把 `[...]` 整個抹除，
導致番號跟著消失，最終回傳空字串。

---

## 觸發的番號格式

```
[SKMJ-310] タイトル.mp4       → ""  ❌
[ING-057] 女優名.mp4           → ""  ❌
[EWDX-426]something.mp4       → ""  ❌
```

---

## 根本原因

`extractor.go` 的前處理步驟：

```go
// 移除 [中文/日文/空白] 之類的說明標籤
bracketRe := regexp.MustCompile(`\[([^\]]*[^\x00-\x7F][^\]]*)\]`)
filename = bracketRe.ReplaceAllString(filename, "")
```

這個 regex 的設計是移除含非 ASCII（中日文）的方括號，
但 `[SKMJ-310]` 全為 ASCII，不應被清除。

**實際問題在於清理順序**：`bracketRe` 是在正規番號提取之前執行，
導致全 ASCII 的番號方括號雖然不被 bracketRe 清除，
但後續 `bracketExtractRe`（`\[([A-Z0-9-]+)\]`）提取後，
若後續 fallback 路徑依賴的 cleanRe 把剩餘 `[...]` 去掉，
最終結果仍然為空。

---

## 修復方案

在 `ExtractCode()` 最前面加入**括號前置提取**：
若檔名以 `[大寫字母-數字]` 開頭，直接提取作為番號，不走後續清理流程。

```go
// 優先處理 [CODE] 格式的檔名（最前方）
bracketCodeRe := regexp.MustCompile(`^\[([A-Z0-9]+-[0-9]+)\]`)
if m := bracketCodeRe.FindStringSubmatch(filename); m != nil {
    return m[1]
}
```

---

## PPV 位數區分（同時修復）

同批番號中有 `PPV-32184`（5 位數），原本被 skip pattern 誤擋：

```go
// 舊：所有 PPV-\d+ 都 skip
skipPPV := regexp.MustCompile(`(?i)^PPV[-_]\d`)

// 新：只 skip 6 位以上（FC2-PPV 業餘影片的格式）
skipPPV := regexp.MustCompile(`(?i)^PPV[-_]\d{6,}`)
```

邏輯依據：
- `PPV-777777`（6 位）= FC2-PPV 素人，skip ✅
- `PPV-32184`（5 位）= 片商正式番號，保留 ✅

---

## MGS 數字前綴格式（2026-04-24 補充）

實測資料發現 MGS / 素人系常見番號格式會在片商字母前保留數字前綴：

```text
200GANA-3376.mp4 → 200GANA-3376
259LUXU-1880.mp4 → 259LUXU-1880
300MIUM-1357.mp4 → 300MIUM-1357
```

這些數字前綴是番號本體，不應被當成網站前綴或雜訊移除。修正方式：

- 在 `codePatterns` 中把 `\d{2,4}[A-Z]{2,6}-\d{3,5}` 放在標準格式前面。
- 在 `validPatterns` 中加入同一格式。
- `normalizeCode()` 只對純 `LETTERS+DIGITS` 緊湊格式補橫槓，避免再用「第一段字母 + 第一段數字」把 `200GANA-3376` 變成 `GANA-200` 或 `GANA-3376`。

這次修正後，`scan -extract` 與目錄掃描都會保留完整 MGS 數字前綴。

---

## 相關檔案

- `pkg/extractor/extractor.go` — bracketCodeRe 前置提取 + skipPPV 位數調整
- `pkg/extractor/extractor_test.go` — 新增測試案例
