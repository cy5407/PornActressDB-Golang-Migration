# 區塊 3：分類核心評估

## 本次檢閱範圍

已檢閱：

- `src/services/classifier_core.py`
- `src/services/studio_classifier.py`
- `src/services/interactive_classifier.py`
- `src/models/extractor.py`
- `src/models/studio.py`
- `src/utils/file_mover.py`
- `src/utils/scanner.py`

## 這個區塊在做什麼

- 掃描結果到分類決策的主流程
- 搜尋後寫回資料庫
- 片商分類規則
- 多女優互動式分類流程
- 檔案搬移前後的業務判斷

## 現況判斷

`src/services/classifier_core.py` 是專案最大的 Python 核心之一，約 1427 行。  
它同時處理：

- DB 初始化
- 掃描器 / 搬移器建立
- 搜尋器呼叫
- 寫入資料庫
- 進度 callback
- 片商分類串接

也就是說，這裡混了「純業務規則」與「UI/流程接線」。

## 是否適合重構成 Golang

**判定：適合，但要先切開純規則與 GUI 流程**

適合搬到 Go 的部分：

- 搜尋結果轉影片資料結構
- 分類規則
- 片商分群判斷
- 批次分類 orchestration
- 檔案目標路徑決策

不適合直接搬的部分：

- callback 字串輸出
- 與 Tkinter dialog 緊密耦合的互動流程
- 直接操作 GUI 狀態的部分

## 是否適合重構成 Rust

**判定：低到中**

Rust 可以做業務規則引擎，但這個專案目前已有 Go 掃描器、Go mover、Go database，若核心決策層改用 Rust，跨語言邊界只會更多。

## 建議結論

這一區塊很適合繼續往 **Go 業務核心** 方向推進，但不應該一次把整個 `classifier_core.py` 原封不動翻譯過去。

正確做法是先拆成兩層：

1. Go：分類決策引擎
2. Python：GUI 流程與使用者互動殼層

## 建議遷移邊界

### 可先搬到 Go 的子模組

- `build_video_info` 類型的資料整形邏輯
- 片商分類統計
- 批次分類任務執行器
- 檔案目的地決策
- 搜尋結果與 DB 寫入規則

### 暫留 Python 的子模組

- `InteractiveClassifier`
- GUI callback
- 對話框開啟與使用者選擇

## 遷移風險

- `classifier_core.py` 目前責任過重，若不先拆功能邊界，Go 版會只是把大檔案換語言
- 業務流程高度依賴字串型進度訊息，建議先改成結構化事件
- 與 DB / mover / scanner 的介面最好先標準化成 request/response model

## 建議優先度

**優先度：P1-P2 之間**

如果目標是快速降低 Python 比例，這區塊很值得早做，但必須建立清楚邊界。

