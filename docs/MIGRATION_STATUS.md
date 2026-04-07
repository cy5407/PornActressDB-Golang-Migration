# MIGRATION STATUS

> W1–W6 已完成；W7 為最終驗收階段。

## Completed

- [x] W1 — 環境建置 & PoC
- [x] W2 — Go Backend Bindings
- [x] W3 — 核心 UI 元件
- [x] W4 — 進階對話框
- [x] W5 — 爬蟲整合
- [x] W6 — 打包與清理

## Current

- [ ] W7 — E2E 驗收 & 打包確認
  - [ ] 執行 `e2e/run_e2e.sh` 通過
  - [ ] 手動驗證所有 E2E 場景
  - [ ] `wails build` 可產生 `.exe`
  - [ ] NSIS installer 可正常安裝與解安裝
  - [ ] Python 爬蟲可於打包後被 Go subprocess 呼叫
  - [ ] 打包 smoke test checklist 全部通過
  - [ ] 專案完成標記更新

## Notes

- W1–W6 為既有完成階段。
- W7 是專案最後的驗收與發佈確認階段。
