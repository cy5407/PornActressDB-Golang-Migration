# PornActressDB 審計腳本說明

`docs/pornactressdb_audit.py` 是 repo 內使用的安全版審計腳本，用來盤點較可能屬於：

- 本地產生的報告
- build / coverage 產物
- 測試樣本備份檔
- 備份副檔名檔案
- git 未追蹤檔案

它的目標不是直接找「可刪除的 live code」，而是先產出較安全的候選清單與風險分級。

## 為什麼要改版

舊版腳本把 `src/services/*.py`、`MIGRATION_STATUS.md` 這類 live code / 核心文件也列入可疑清單，容易造成誤刪判斷。新版改成：

- 不再把 `src/`、`tests/`、`tools/`、`cmd/`、`pkg/`、`wails-app/`、`wiki/` 直接當成可刪目標
- 對命中程式碼路徑或 source-like 檔案，一律降級成 `manual_review`
- 對 git 已追蹤檔案，不再直接標為低風險刪除候選
- 對 `docs/`、`.md`、`.lock` 這類未追蹤檔案，預設視為「先判斷是否該納入版控」

## 用法

```bash
python3 docs/pornactressdb_audit.py
python3 docs/pornactressdb_audit.py --project-root /path/to/repo
python3 docs/pornactressdb_audit.py --output-dir /tmp/pornactressdb-audit
```

預設會輸出：

- `.audit_report.json`
- `.audit_report.txt`

## 輸出判讀

每個命中項目都會附上：

- `action`
  - `delete_candidate`: 低風險、通常可重建的暫存/報告產物
  - `ignore_candidate`: 較像 build artifact，優先考慮加入 `.gitignore`
  - `manual_review`: 不可直接刪，必須人工複核
- `risk_level`
  - `low` / `medium` / `high`
- `tracked`
  - 是否已被 git 追蹤

## 重要限制

這支腳本不是 dead-code analyzer，也不是引用分析器。

所以：

1. 命中清單不能直接當刪檔清單
2. 只要牽涉 `src/`、`tests/`、`tools/`、核心文件、跨層介面檔案，都必須再做人工驗證
3. 若報告結果與實際引用、測試、AGENTS / 規格文件衝突，應以實際引用與測試為準

一句話說，這份報告只能拿來「縮小人工審查範圍」，不能拿來自動清理。 
