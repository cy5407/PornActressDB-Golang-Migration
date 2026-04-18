# Agent Skills

Agent Skills 是擴展 Claude 功能的模組化能力。每個 Skill 封裝了指令、元資料和可選資源（腳本、範本），Claude 會在相關時自動使用它們。

---

## 為什麼使用 Skills

Skills 是可重複使用的、基於檔案系統的資源，為 Claude 提供特定領域的專業知識：工作流程、上下文和最佳實踐，將通用代理轉變為專家。與提示詞（對話層級的一次性任務指令）不同，Skills 按需載入，消除了在多個對話中重複提供相同指導的需要。

**主要優勢**：
- **專業化 Claude**：為特定領域任務量身定制能力
- **減少重複**：建立一次，自動使用
- **組合能力**：結合多個 Skills 建構複雜的工作流程

<Note>
如需深入了解 Agent Skills 的架構和實際應用，請閱讀我們的工程部落格：[Equipping agents for the real world with Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)。
</Note>

## 使用 Skills

Anthropic 為常見文件任務（PowerPoint、Excel、Word、PDF）提供預建的 Agent Skills，您也可以建立自己的自訂 Skills。兩者的運作方式相同。Claude 會在與您的請求相關時自動使用它們。

**預建 Agent Skills** 可供所有 claude.ai 使用者和透過 Claude API 使用。請參閱下方的[可用 Skills](#available-skills) 章節以獲取完整列表。

**自訂 Skills** 讓您封裝領域專業知識和組織知識。它們可在 Claude 的各產品中使用：在 Claude Code 中建立、透過 API 上傳，或在 claude.ai 設定中新增。

<Note>
**開始使用：**
- 預建 Agent Skills：請參閱[快速入門教學](/docs/zh-TW/agents-and-tools/agent-skills/quickstart)，開始在 API 中使用 PowerPoint、Excel、Word 和 PDF skills
- 自訂 Skills：請參閱 [Agent Skills Cookbook](https://platform.claude.com/cookbook/skills-notebooks-01-skills-introduction)，了解如何建立您自己的 Skills
</Note>

## Skills 的運作方式

Skills 利用 Claude 的 VM 環境來提供超越提示詞所能實現的能力。Claude 在具有檔案系統存取權限的虛擬機器中運作，允許 Skills 以目錄形式存在，包含指令、可執行程式碼和參考資料，組織方式就像您為新團隊成員建立的入職指南。

這種基於檔案系統的架構實現了**漸進式揭露**：Claude 根據需要分階段載入資訊，而不是預先消耗上下文。

### 三種 Skill 內容類型，三個載入層級

Skills 可以包含三種類型的內容，每種在不同時間載入：

### 第 1 層：元資料（始終載入）

**內容類型：指令**。Skill 的 YAML 前置資料提供發現資訊：

```yaml
---
name: pdf-processing
description: Extract text and tables from PDF files, fill forms, merge documents. Use when working with PDF files or when the user mentions PDFs, forms, or document extraction.
---
```

Claude 在啟動時載入此元資料並將其包含在系統提示中。這種輕量級方法意味著您可以安裝許多 Skills 而不會產生上下文損耗；Claude 只知道每個 Skill 的存在以及何時使用它。

### 第 2 層：指令（觸發時載入）

**內容類型：指令**。SKILL.md 的主體包含程序性知識：工作流程、最佳實踐和指導：

````markdown
# PDF Processing

## Quick start

Use pdfplumber to extract text from PDFs:

```python
import pdfplumber

with pdfplumber.open("document.pdf") as pdf:
    text = pdf.pages[0].extract_text()
```

For advanced form filling, see [FORMS.md](FORMS.md).
````

當您的請求與某個 Skill 的描述匹配時，Claude 會透過 bash 從檔案系統讀取 SKILL.md。只有在此時，這些內容才會進入上下文視窗。

### 第 3 層：資源和程式碼（按需載入）

**內容類型：指令、程式碼和資源**。Skills 可以捆綁額外的材料：

```
pdf-skill/
├── SKILL.md (main instructions)
├── FORMS.md (form-filling guide)
├── REFERENCE.md (detailed API reference)
└── scripts/
    └── fill_form.py (utility script)
```

**指令**：額外的 markdown 檔案（FORMS.md、REFERENCE.md），包含專門的指導和工作流程

**程式碼**：可執行腳本（fill_form.py、validate.py），Claude 透過 bash 執行；腳本提供確定性操作而不消耗上下文

**資源**：參考資料，如資料庫結構描述、API 文件、範本或範例

Claude 只在被引用時才存取這些檔案。檔案系統模型意味著每種內容類型都有不同的優勢：指令用於靈活的指導，程式碼用於可靠性，資源用於事實查詢。

| 層級 | 載入時機 | Token 成本 | 內容 |
|-------|------------|------------|---------|
| **第 1 層：元資料** | 始終（啟動時） | 每個 Skill 約 100 tokens | YAML 前置資料中的 `name` 和 `description` |
| **第 2 層：指令** | Skill 被觸發時 | 少於 5k tokens | SKILL.md 主體，包含指令和指導 |
| **第 3 層以上：資源** | 按需 | 實際上無限制 | 透過 bash 執行的捆綁檔案，無需將內容載入上下文 |

漸進式揭露確保在任何給定時間只有相關內容佔用上下文視窗。

### Skills 架構

Skills 在程式碼執行環境中運行，Claude 在其中擁有檔案系統存取權限、bash 命令和程式碼執行能力。可以這樣理解：Skills 以目錄形式存在於虛擬機器上，Claude 使用與您在電腦上瀏覽檔案相同的 bash 命令與它們互動。

![Agent Skills 架構 - 展示 Skills 如何與代理的配置和虛擬機器整合](/docs/images/agent-skills-architecture.png)

**Claude 如何存取 Skill 內容：**

當 Skill 被觸發時，Claude 使用 bash 從檔案系統讀取 SKILL.md，將其指令帶入上下文視窗。如果這些指令引用了其他檔案（如 FORMS.md 或資料庫結構描述），Claude 也會使用額外的 bash 命令讀取這些檔案。當指令提到可執行腳本時，Claude 透過 bash 執行它們，只接收輸出（腳本程式碼本身永遠不會進入上下文）。

**此架構實現的功能：**

**按需檔案存取**：Claude 只讀取每個特定任務所需的檔案。一個 Skill 可以包含數十個參考檔案，但如果您的任務只需要銷售結構描述，Claude 只載入那一個檔案。其餘檔案留在檔案系統上，消耗零 tokens。

**高效腳本執行**：當 Claude 執行 `validate_form.py` 時，腳本的程式碼永遠不會載入上下文視窗。只有腳本的輸出（如「驗證通過」或特定錯誤訊息）消耗 tokens。這使得腳本比讓 Claude 即時生成等效程式碼要高效得多。

**捆綁內容無實際限制**：因為檔案在被存取之前不會消耗上下文，Skills 可以包含完整的 API 文件、大型資料集、大量範例或您需要的任何參考資料。未使用的捆綁內容不會產生上下文損耗。

這種基於檔案系統的模型是漸進式揭露得以運作的原因。Claude 瀏覽您的 Skill 就像您查閱入職指南的特定章節一樣，精確存取每個任務所需的內容。

### 範例：載入 PDF 處理 skill

以下是 Claude 載入和使用 PDF 處理 skill 的方式：

1. **啟動**：系統提示包含：`PDF Processing - Extract text and tables from PDF files, fill forms, merge documents`
2. **使用者請求**：「從這個 PDF 中提取文字並進行摘要」
3. **Claude 呼叫**：`bash: read pdf-skill/SKILL.md` → 指令載入上下文
4. **Claude 判斷**：不需要表單填寫，因此不讀取 FORMS.md
5. **Claude 執行**：使用 SKILL.md 中的指令完成任務

![Skills 載入上下文視窗 - 展示 skill 元資料和內容的漸進式載入](/docs/images/agent-skills-context-window.png)

圖表顯示：
1. 預設狀態，系統提示和 skill 元資料已預先載入
2. Claude 透過 bash 讀取 SKILL.md 來觸發 skill
3. Claude 根據需要選擇性地讀取額外的捆綁檔案，如 FORMS.md
4. Claude 繼續執行任務

這種動態載入確保只有相關的 skill 內容佔用上下文視窗。

## Skills 的適用範圍

Skills 可在 Claude 的各代理產品中使用：

### Claude API

Claude API 支援預建 Agent Skills 和自訂 Skills。兩者的運作方式完全相同：在 `container` 參數中指定相關的 `skill_id`，同時搭配程式碼執行工具。

**先決條件**：透過 API 使用 Skills 需要三個 beta 標頭：
- `code-execution-2025-08-25` - Skills 在程式碼執行容器中運行
- `skills-2025-10-02` - 啟用 Skills 功能
- `files-api-2025-04-14` - 用於向容器上傳/下載檔案

透過引用 `skill_id`（例如 `pptx`、`xlsx`）使用預建 Agent Skills，或透過 Skills API（`/v1/skills` 端點）建立和上傳您自己的 Skills。自訂 Skills 在整個組織範圍內共享。

要了解更多，請參閱[透過 Claude API 使用 Skills](/docs/zh-TW/build-with-claude/skills-guide)。

### Claude Code

[Claude Code](https://code.claude.com/docs/en/overview) 僅支援自訂 Skills。

**自訂 Skills**：建立包含 SKILL.md 檔案的目錄作為 Skills。Claude 會自動發現並使用它們。

Claude Code 中的自訂 Skills 基於檔案系統，不需要 API 上傳。

要了解更多，請參閱[在 Claude Code 中使用 Skills](https://code.claude.com/docs/en/skills)。

### Claude Agent SDK

[Claude Agent SDK](/docs/zh-TW/agent-sdk/overview) 透過基於檔案系統的配置支援自訂 Skills。

**自訂 Skills**：在 `.claude/skills/` 中建立包含 SKILL.md 檔案的目錄。透過在 `allowed_tools` 配置中包含 `"Skill"` 來啟用 Skills。

SDK 運行時會自動發現 Skills。

要了解更多，請參閱 [Agent SDK 中的 Skills](/docs/zh-TW/agent-sdk/skills)。

### Claude.ai

[Claude.ai](https://claude.ai) 支援預建 Agent Skills 和自訂 Skills。

**預建 Agent Skills**：當您建立文件時，這些 Skills 已在幕後運作。Claude 無需任何設定即可使用它們。

**自訂 Skills**：透過設定 > 功能，以 zip 檔案形式上傳您自己的 Skills。適用於啟用了程式碼執行的 Pro、Max、Team 和 Enterprise 方案。自訂 Skills 是個人專屬的；它們不會在整個組織範圍內共享，管理員也無法集中管理。

要了解更多關於在 Claude.ai 中使用 Skills 的資訊，請參閱 Claude 幫助中心的以下資源：
- [什麼是 Skills？](https://support.claude.com/en/articles/12512176-what-are-skills)
- [在 Claude 中使用 Skills](https://support.claude.com/en/articles/12512180-using-skills-in-claude)
- [如何建立自訂 Skills](https://support.claude.com/en/articles/12512198-creating-custom-skills)
- [使用 Skills 教導 Claude 您的工作方式](https://support.claude.com/en/articles/12580051-teach-claude-your-way-of-working-using-skills)

## Skill 結構

每個 Skill 都需要一個包含 YAML 前置資料的 `SKILL.md` 檔案：

```yaml
---
name: your-skill-name
description: Brief description of what this Skill does and when to use it
---

# Your Skill Name

## Instructions
[Clear, step-by-step guidance for Claude to follow]

## Examples
[Concrete examples of using this Skill]
```

**必填欄位**：`name` 和 `description`

**欄位要求**：

`name`：
- 最多 64 個字元
- 只能包含小寫字母、數字和連字號
- 不能包含 XML 標籤
- 不能包含保留字：「anthropic」、「claude」

`description`：
- 不能為空
- 最多 1024 個字元
- 不能包含 XML 標籤

`description` 應包含 Skill 的功能以及 Claude 應在何時使用它。如需完整的撰寫指導，請參閱[最佳實踐指南](/docs/zh-TW/agents-and-tools/agent-skills/best-practices)。

## 安全考量

我們強烈建議僅使用來自可信來源的 Skills：您自己建立的或從 Anthropic 獲取的。Skills 透過指令和程式碼為 Claude 提供新能力，雖然這使它們功能強大，但也意味著惡意 Skill 可以指導 Claude 以不符合 Skill 聲明目的的方式呼叫工具或執行程式碼。

<Warning>
如果您必須使用來自不受信任或未知來源的 Skill，請極度謹慎並在使用前徹底審查。根據 Claude 在執行 Skill 時擁有的存取權限，惡意 Skills 可能導致資料外洩、未授權系統存取或其他安全風險。
</Warning>

**主要安全考量**：
- **徹底審查**：檢查 Skill 中捆綁的所有檔案：SKILL.md、腳本、圖片和其他資源。注意異常模式，如意外的網路呼叫、檔案存取模式或與 Skill 聲明目的不符的操作
- **外部來源有風險**：從外部 URL 獲取資料的 Skills 具有特別的風險，因為獲取的內容可能包含惡意指令。即使是可信的 Skills，如果其外部依賴項隨時間變化，也可能被入侵
- **工具濫用**：惡意 Skills 可以以有害方式呼叫工具（檔案操作、bash 命令、程式碼執行）
- **資料暴露**：具有敏感資料存取權限的 Skills 可能被設計為向外部系統洩露資訊
- **視同安裝軟體**：僅使用來自可信來源的 Skills。在將 Skills 整合到具有敏感資料或關鍵操作存取權限的生產系統時要特別小心

## 可用 Skills

### 預建 Agent Skills

以下預建 Agent Skills 可立即使用：

- **PowerPoint (pptx)**：建立簡報、編輯投影片、分析簡報內容
- **Excel (xlsx)**：建立試算表、分析資料、生成帶圖表的報告
- **Word (docx)**：建立文件、編輯內容、格式化文字
- **PDF (pdf)**：生成格式化的 PDF 文件和報告

這些 Skills 可在 Claude API 和 claude.ai 上使用。請參閱[快速入門教學](/docs/zh-TW/agents-and-tools/agent-skills/quickstart)以開始在 API 中使用它們。

### 自訂 Skills 範例

如需自訂 Skills 的完整範例，請參閱 [Skills cookbook](https://platform.claude.com/cookbook/skills-notebooks-01-skills-introduction)。

## 限制和約束

了解這些限制有助於您有效規劃 Skills 部署。

### 跨平台可用性

**自訂 Skills 不會跨平台同步**。上傳到一個平台的 Skills 不會自動在其他平台上可用：

- 上傳到 Claude.ai 的 Skills 必須另外上傳到 API
- 透過 API 上傳的 Skills 在 Claude.ai 上不可用
- Claude Code Skills 基於檔案系統，與 Claude.ai 和 API 都是分開的

您需要為每個想要使用 Skills 的平台分別管理和上傳 Skills。

### 共享範圍

Skills 根據使用位置有不同的共享模型：
- **Claude.ai**：僅限個人使用者；每個團隊成員必須分別上傳
- **Claude API**：工作區範圍；所有工作區成員都可以存取已上傳的 Skills
- **Claude Code**：個人（`~/.claude/skills/`）或專案級（`.claude/skills/`）；也可以透過 Claude Code Plugins 共享

Claude.ai 目前不支援集中式管理員管理或組織範圍的自訂 Skills 分發。

### 執行環境約束

您的 skill 可用的確切執行環境取決於您使用它的產品平台。

 - **Claude.ai**：
    - **不同的網路存取**：根據使用者/管理員設定，Skills 可能擁有完整、部分或無網路存取。如需更多詳情，請參閱[建立和編輯檔案](https://support.claude.com/en/articles/12111783-create-and-edit-files-with-claude#h_6b7e833898)支援文章。
- **Claude API**：
    - **無網路存取**：Skills 無法進行外部 API 呼叫或存取網際網路
    - **無執行時套件安裝**：僅預安裝的套件可用。您無法在執行期間安裝新套件。
    - **僅預配置的依賴項**：請查看[程式碼執行工具文件](/docs/zh-TW/agents-and-tools/tool-use/code-execution-tool)以獲取可用套件列表
- **Claude Code**：
    - **完整網路存取**：Skills 擁有與使用者電腦上任何其他程式相同的網路存取權限
    - **不建議全域套件安裝**：Skills 應僅在本地安裝套件，以避免干擾使用者的電腦

請規劃您的 Skills 以在這些約束條件下運作。

## 後續步驟

<CardGroup cols={2}>
  <Card
    title="開始使用 Agent Skills"
    icon="graduation-cap"
    href="/docs/zh-TW/agents-and-tools/agent-skills/quickstart"
  >
    建立您的第一個 Skill
  </Card>
  <Card
    title="API 指南"
    icon="code"
    href="/docs/zh-TW/build-with-claude/skills-guide"
  >
    透過 Claude API 使用 Skills
  </Card>
  <Card
    title="在 Claude Code 中使用 Skills"
    icon="terminal"
    href="https://code.claude.com/docs/en/skills"
  >
    在 Claude Code 中建立和管理自訂 Skills
  </Card>
  <Card
    title="在 Agent SDK 中使用 Skills"
    icon="cube"
    href="/docs/zh-TW/agent-sdk/skills"
  >
    在 TypeScript 和 Python 中以程式化方式使用 Skills
  </Card>
  <Card
    title="撰寫最佳實踐"
    icon="lightbulb"
    href="/docs/zh-TW/agents-and-tools/agent-skills/best-practices"
  >
    撰寫 Claude 能有效使用的 Skills
  </Card>
</CardGroup>