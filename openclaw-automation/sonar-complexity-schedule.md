# Sonar Complexity Schedule

目標 branch：`sonar-complexity-refactor`

狀態說明：
- `[ ]` 未處理
- `[-]` 進行中
- `[x]` 已完成
- `[s]` 略過（需附原因）

## Groups
- [x] Group 1 — `WBS-3` / `WBS-4`
- [x] Group 2 — `AVW-3` / `AVW-4`
- [x] Group 3 — `JDB-2` / `JDB-3`
- [x] Group 4 — `ANF-2` + final review / final commit

## Estimated Duration
- Group 1: 20–35 分
- Group 2: 20–35 分
- Group 3: 15–30 分
- Group 4: 10–20 分
- Total: 約 1.5–2.5 小時

## Run Log
- 初始化：建立 complexity 排程清單，等待排程執行。
- 2026-04-11：完成 Group 1（WBS-3 / WBS-4），拆分 AV-WIKI 批次搜尋與級聯 fallback orchestration。
- 2026-04-11：完成 Group 2（AVW-3 / AVW-4），拆分批次搜尋 orchestration / 統計 / 錯誤處理與文本掃描 helper。
- 2026-04-11：完成 Group 3（JDB-2 / JDB-3），拆分詳情頁 result builder 與搜尋流程 orchestration。
- 2026-04-11：完成 Group 4（ANF-2），將 `get_most_likely_actress()` 的 score helper 外提為 private static method。
- 所有 complexity groups 已完成，停用排程：pornactressdb:sonar-complexity-refactor