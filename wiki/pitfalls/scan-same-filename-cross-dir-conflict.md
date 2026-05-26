---
category: 掃描 / 移動
date: 2026-05-25
status: latent
---
# 同檔名跨目錄：兩個 source 撞到同一 destination

## 症狀

兩個影片檔位於不同子目錄但 **basename 完全相同**：

```
C:\Downloads\AV\
  ├── A\KUSE-042-1.mp4
  └── B\KUSE-042-1.mp4
```

`ScanDirectory`（2026-05-25 移除 code dedupe 之後）會把兩筆都列進來，但 `BatchMove` 時兩筆指向同一個 destination `<夏優響資料夾>\KUSE-042-1.mp4`。後一筆套用 `OnConflict`：

- `skip` → 第二筆**留在原地**，user 預期沒搬走
- `overwrite` → 第二筆**覆蓋第一筆**，**資料遺失**
- `rename` → 第二筆被 rename 成 `KUSE-042-1 (1).mp4`

若 `BatchMove` 跑 goroutine pool 並行，兩個 worker 同時 `os.Stat` 都看不到對方 → 即使 `skip` 也可能 race 撞名。

## 根因

`CheckConflicts`（`wails-app/backend/app.go:316-329`）只用 `os.Stat(item.Destination)` 預檢磁碟上 dest 是否已存在，**不會偵測同批次內 source A / source B 指向同一 dest** 這層 in-batch collision。預檢時兩筆 dest 都還不存在，全部進 BatchMove。

## 目前狀態

- 2026-05-25 移除 scan 階段 `seen[code]` dedupe 後暴露此 edge case。
- **未修**：採用「選項 A：接受現狀」。GUI 預設 `skip`，最壞結果是 file B 留在原地，不會丟資料。
- 與 multi-part 切割檔（`KUSE-042-1.mp4` + `KUSE-042-2.mp4`，basename 不同 → dest 不撞）**完全是不同問題**；後者已修。

## 規避

| 你想做什麼 | 怎麼做 |
|-----------|--------|
| 確保兩個檔都被搬 | 跑前手動 rename 一邊（如 `KUSE-042-1_v2.mp4`）讓 basename 唯一 |
| 確保不丟資料 | 不要把 `OnConflict` 設成 `overwrite` |
| 想看哪些檔被 skip | 跑完看 GUI batch result log，skipped 列表會列出 |

## 未來修法

四個選項的完整分析請見：[**docs/茶包射手/scan-multi-part-and-same-name-cross-dir.md**](../../docs/茶包射手/scan-multi-part-and-same-name-cross-dir.md)

簡要：

- **A**（現在採用）：不動，靠預設 `skip` 保資料安全
- **B**：`CheckConflicts` 加 in-batch dest 重複偵測
- **C**：Scan dedupe 改成 `(directory, code)` 複合 key
- **D**：A 的修法 + B（完整解）

## 相關檔案

- `wails-app/backend/app.go::ScanDirectory`（不再 dedupe）
- `wails-app/backend/app.go::CheckConflicts`（檔內預檢，無 in-batch 偵測）
- `wails-app/backend/app_test.go::TestScanDirectory_KeepsMultiplePartsWithSameCode`

## 相關 pitfall

- [`wails-scan-duplicate.md`](wails-scan-duplicate.md) — 歷史上加 `seen[]` map 的背景
