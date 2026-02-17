---
name: documentation-guide
description: 文件撰寫指引 - 用於更新 README、撰寫 API 文件、建立使用指南、維護 CHANGELOG 和規範註解
argument-hint: "[doc-type]"
---

# 文件撰寫 Skill

## 何時使用此 Skill

當需要：
1. **更新 README**（新功能說明）
2. **撰寫 API 文件**（函式說明）
3. **建立使用指南**（操作步驟）
4. **維護 CHANGELOG**（版本記錄）
5. **規範程式碼註解**

## 文件結構

```
docs/
├── VSCODE_AGENT_SKILLS_GUIDE.md          # Agent Skills 官方指南
├── VSCODE_SKILLS_QUICK_REFERENCE.md      # 快速參考
├── SKILLS_ANALYSIS_REPORT.md             # Skills 分析報告
└── SKILLS_IMPLEMENTATION_TASKS.md        # 實作任務清單

專案根目錄/
├── README.md                              # 專案概述
├── CLAUDE.md                              # Claude 開發指引
├── QUICK_START_GUIDE.md                   # 快速開始
└── CHANGELOG.md                           # 變更日誌
```

## 文件規範

### README 章節

1. 專案概述
2. 功能特色
3. 安裝步驟
4. 快速開始
5. 使用說明
6. 開發指南
7. 常見問題
8. 授權資訊

### API 文件格式

```python
def add_video(code: str, info: dict) -> bool:
    """新增影片到資料庫
    
    Args:
        code: 番號（如 STARS-707）
        info: 影片資訊字典
            - actresses: 女優列表
            - title: 標題
            - studio: 片商
    
    Returns:
        bool: 成功回傳 True，失敗回傳 False
    
    Example:
        >>> db.add_video('STARS-707', {
        ...     'actresses': ['橋本ありな'],
        ...     'title': '作品標題'
        ... })
        True
    """
```

## 相關檔案

- `README.md` - 專案主文件
- `CLAUDE.md` - 開發指引
- `docs/` - 詳細文件目錄
