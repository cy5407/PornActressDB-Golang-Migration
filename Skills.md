# 技術技能清單 (Skills.md)

本專案使用的技術、工具和最佳實踐。

---

## 🐍 Python 開發

### 核心技術
- **Python 3.11+** - 主要開發語言
- **Tkinter** - GUI 桌面應用框架
- **Threading** - 多執行緒背景處理

### 資料處理
- **JSON** - 資料儲存格式 (IncrementalJSONDB)
- **BeautifulSoup4** - HTML 解析爬蟲
- **Requests** - HTTP 客戶端

---

## 🛠️ 開發工具

### 程式碼品質 (2024-2025 主流)

#### **Ruff** ⚡ - 程式碼檢查與格式化
- **速度**: 用 Rust 編寫，比 Black 快 10-100 倍
- **功能**: 同時替代 Flake8 + Black + isort + pyupgrade
- **下載量**: ~1.1 億次/月 (PyPI 2025年12月)
- **GitHub**: 44.4k+ stars

```bash
# 安裝
pip install ruff

# 檢查程式碼
ruff check .

# 自動修復
ruff check --fix .

# 格式化程式碼
ruff format .

# 同時執行檢查和格式化
ruff check --fix . && ruff format .
```

#### 配置 (pyproject.toml)
```toml
[tool.ruff]
line-length = 88
target-version = "py311"

[tool.ruff.lint]
select = ["E", "W", "F", "I", "UP", "B", "C4", "SIM"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

### 版本控制
- **Git** - 版本控制系統
- **GitHub** - 程式碼託管

---

## 📏 程式碼風格標準

### PEP 8 基礎規範
| 項目 | 標準 |
|------|------|
| 行長度 | 88 字元 (Black/Ruff 預設) |
| 縮排 | 4 個空格 |
| 引號 | 雙引號 `"string"` |
| import 順序 | 標準庫 → 第三方 → 本地 |

### 命名慣例
| 類型 | 風格 | 範例 |
|------|------|------|
| 模組/套件 | snake_case | `my_module.py` |
| 類別 | PascalCase | `MyClass` |
| 函式/變數 | snake_case | `my_function` |
| 常數 | UPPER_SNAKE | `MAX_VALUE` |
| 私有 | _prefix | `_private_var` |

### 本專案特定規範
- 日誌使用 emoji 前綴：🚀開始 ✅成功 ❌失敗 ⚠️警告
- GUI 更新使用 `root.after()` 回主執行緒
- 長時間操作使用背景執行緒

---

## 🔧 程式碼檢查規則

### 啟用的 Ruff 規則
| 代碼 | 說明 | 來源 |
|------|------|------|
| E | 程式碼風格錯誤 | pycodestyle |
| W | 程式碼風格警告 | pycodestyle |
| F | 邏輯錯誤 | Pyflakes |
| I | import 排序 | isort |
| UP | 語法升級 | pyupgrade |
| B | 常見 bug | flake8-bugbear |
| C4 | 推導式優化 | flake8-comprehensions |
| SIM | 簡化建議 | flake8-simplify |

---

## 📊 工具比較 (2025)

| 工具 | 速度 | Linting | Formatting | Import排序 | Stars |
|------|------|---------|------------|-----------|-------|
| **Ruff** 🏆 | ⚡極快 | ✅ | ✅ | ✅ | 44k |
| Black | 🐢較慢 | ❌ | ✅ | ❌ | 38k |
| Flake8 | 🐢較慢 | ✅ | ❌ | ❌ | 3k |
| autopep8 | 🐢較慢 | ❌ | ✅ | ❌ | 4k |

### 為什麼選擇 Ruff？
1. **All-in-one** - 一個工具替代多個
2. **極速** - Rust 實作，毫秒級執行
3. **廣泛採用** - FastAPI、Pandas、PyTorch 等都在用
4. **與 Black 相容** - 可無縫切換

---

## 🚀 快速開始

### 首次設定
```bash
# 1. 安裝 ruff
pip install ruff

# 2. 檢查整個專案
ruff check .

# 3. 自動修復可修復的問題
ruff check --fix .

# 4. 格式化程式碼
ruff format .
```

### VS Code 整合
1. 安裝擴充套件: `charliermarsh.ruff`
2. 設定自動格式化:
```json
{
    "[python]": {
        "editor.formatOnSave": true,
        "editor.defaultFormatter": "charliermarsh.ruff"
    }
}
```

### Pre-commit Hook
```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.14.9
    hooks:
      - id: ruff-check
        args: [--fix]
      - id: ruff-format
```

---

## 📚 參考資源

- [PEP 8 - Python 官方風格指南](https://peps.python.org/pep-0008/)
- [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
- [Ruff 官方文件](https://docs.astral.sh/ruff/)
- [Black 程式碼風格](https://black.readthedocs.io/)

---

*最後更新: 2025年12月13日*
