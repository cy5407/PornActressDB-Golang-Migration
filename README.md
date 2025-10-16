# 女優分類系統 - 智慧影片管理工具

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Active-success.svg)]()

一個功能完整的智慧影片分類管理系統，支援自動女優識別、片商分類、多源搜尋與資料庫管理。

## ✨ 主要功能

### 🔍 智慧搜尋系統
- **多源搜尋**: 支援 AV-WIKI 和 chiba-f.net 雙重搜尋引擎
- **自動回退**: 主要搜尋失敗時自動切換備用源
- **片商資訊同步**: 搜尋時自動提取並儲存片商資訊
- **智慧過濾**: 自動過濾 FC2/PPV 檔案，避免無效搜尋

### 🗂️ 分類管理
- **女優分類**: 根據檔案名稱自動識別女優並分類
- **片商分類**: 基於信心度的智慧片商分類系統
- **互動模式**: 支援手動確認和自動分類模式
- **路徑管理**: 安全的檔案移動與重新組織

### 💾 資料庫系統
- **JSON 儲存**: 輕量級檔案型資料庫，無需額外安裝
- **並行安全**: 支援多執行緒讀寫，檔案鎖定保護
- **備份管理**: 自動備份與恢復功能
- **統計分析**: 完整的女優與片商統計資訊

### 🎨 使用者界面
- **現代化 GUI**: 基於 tkinter 的直觀界面
- **即時進度**: 詳細的處理進度與狀態顯示
- **偏好設定**: 可客製化的使用者偏好
- **錯誤處理**: 完善的錯誤提示與處理機制

## 🚀 快速開始

### 系統需求
- Python 3.8 或更高版本
- Windows 10/11 (主要測試平台)
- 網路連接 (用於線上搜尋功能)

### 安裝步驟

1. **複製專案**
   ```bash
   git clone https://github.com/YOUR_USERNAME/actress-classifier.git
   cd actress-classifier
   ```

2. **建立虛擬環境**
   ```bash
   python -m venv venv
   venv\Scripts\activate  # Windows
   ```

3. **安裝相依套件**
   ```bash
   pip install -r requirements.txt
   ```

4. **啟動程式**
   ```bash
   python run.py
   ```

### 首次使用

1. 程式會自動建立 JSON 資料庫於 `data/json_db/` 目錄
2. 可透過「偏好設定」調整分類參數
3. 建議先使用小量檔案測試功能

## 📋 功能說明

### 女優分類流程
1. 選擇包含影片檔案的資料夾
2. 系統自動掃描並識別檔案名稱中的女優資訊
3. 可選擇自動分類或互動式確認模式
4. 系統建立女優資料夾並移動對應檔案

### 片商分類流程
1. 分析女優資料夾中的影片檔案
2. 提取番號並識別對應片商
3. 計算片商信心度（基於影片數量比例）
4. 根據信心度閾值決定分類策略

### 搜尋功能
- **線上搜尋**: 從網路資料庫獲取女優資訊
- **離線模式**: 使用本地快取資料
- **批次處理**: 支援大量檔案的批次搜尋
- **結果儲存**: 搜尋結果自動儲存到資料庫

## 🛠️ 技術架構

### 專案結構
```
src/
├── models/              # 資料模型層
│   ├── config.py           # 設定管理
│   ├── database.py         # 資料庫操作
│   ├── extractor.py        # 檔案名稱解析
│   └── studio.py           # 片商識別
├── services/            # 業務邏輯層
│   ├── classifier_core.py      # 分類核心
│   ├── interactive_classifier.py # 互動分類
│   ├── studio_classifier.py    # 片商分類
│   └── web_searcher.py         # 網路搜尋
├── ui/                 # 使用者界面層
│   ├── main_gui.py         # 主要界面
│   └── preferences_dialog.py # 偏好設定
└── utils/              # 工具模組
    └── scanner.py          # 檔案掃描
```

### 核心技術
- **Python 3.8+**: 主要開發語言
- **tkinter**: GUI 框架
- **JSON**: 輕量級資料儲存 (檔案型資料庫)
- **httpx/requests**: HTTP 客戶端
- **BeautifulSoup**: HTML 解析
- **pathlib**: 現代化路徑處理

## 🔧 設定說明

### 資料庫設定
```ini
[database]
json_data_dir = data/json_db
```

**JSON 資料庫優勢**:
- ✓ 無需額外安裝資料庫軟體
- ✓ 易於備份和遷移 (單一 JSON 檔案)
- ✓ 支援並行讀寫 (檔案鎖定機制)
- ✓ 人類可讀的資料格式
- ✓ 輕量級部署,適合個人使用

### 搜尋設定
```ini
[search]
batch_size = 10
thread_count = 5
batch_delay = 2.0
request_timeout = 20
```

### 分類設定
```ini
[classification]
mode = interactive
auto_apply_preferences = true
```

## 🧪 測試

### 執行測試套件
```bash
# 檢查資料庫狀態
python check_database.py

# FC2/PPV 過濾測試
python test_fc2_filter.py

# 搜尋功能測試
python test_enhanced_search.py
```

### 驗證腳本
```bash
# Chiba-f.net 整合測試
python .ai-playground/validations/test_chiba_f_net.py

# 整合搜尋測試
python .ai-playground/validations/test_integrated_search.py
```

## 📚 文件

- [專案計畫書](專案管理/專案計畫/專案計畫書_v1.0.md)
- [需求規格書](專案管理/需求規格/需求規格書_v1.0.md)
- [資料庫配置指南](docs/database_guide.md)
- [24小時更新報告](專案管理/進度報告/24小時功能更新整合報告_20250618.md)

## 🐛 問題回報

如遇到問題，請提供以下資訊：
1. 錯誤訊息的完整內容
2. 作業系統版本
3. Python 版本
4. 重現步驟

## 🤝 貢獻指南

1. Fork 此專案
2. 建立功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交變更 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 開啟 Pull Request

## 📈 版本歷史

### v5.2 (2025-06-18)
- 🚀 完整系統模組化重構
- 🔍 多源搜尋引擎整合
- 🛡️ FC2/PPV 智慧過濾
- 🔧 穩定性大幅提升

### v5.1 (2025-06-18)
- 🎯 搜尋功能增強
- 💾 資料庫結構擴充
- 🧪 測試套件建立

### v5.0 (2025-06-17)
- 🏗️ 系統架構重構
- 📋 專案管理體系建立

## 📄 授權

此專案採用 MIT 授權條款 - 詳見 [LICENSE](LICENSE) 檔案

## 🙏 致謝

- 感謝所有使用者的回饋與建議
- 感謝開源社群提供的工具與函式庫
- 特別感謝 AI 輔助開發工具的支援

---

**注意**: 此工具僅供個人使用，請遵守相關法律法規與版權規定。
