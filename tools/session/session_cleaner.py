#!/usr/bin/env python3
"""
session_cleaner.py — Copilot CLI session markdown 清洗工具

保留：
  - ### 👤 User        使用者訊息（全文）
  - ### 💬 Copilot     AI 結論（全文）
  - ### ✅ `tool`      成功工具呼叫（保留標題+參數，body 超過 800 字元時截斷）
  - ### ❌ `tool`      失敗的工具呼叫（保留完整內容，含 stderr/stack trace）
  - <sub>⏱️ ...        時間戳（保留）

刪除/壓縮：
  - ### 💭 Reasoning   AI 思考過程
  - ### ℹ️ Info        環境樣板資訊
  - <details>...</details> 成功工具呼叫的完整輸出
  - 超大工具輸出（如 MCP server JSON 未被 <details> 包裝的部分）
  - 重複出現的絕對路徑前綴（自動偵測並縮短為 .\\）

用法：
  python session_cleaner.py input.md
  python session_cleaner.py input.md -o output.md
"""

import re
import sys
from collections import Counter
from pathlib import Path


# 每個 section 的起始標記（### 開頭）
SECTION_RE = re.compile(r'^(### .+)$', re.MULTILINE)

# 判斷 section 類型
KEEP_FULL   = re.compile(r'^### (👤 User|💬 Copilot)')
KEEP_HEADER = re.compile(r'^### ✅')   # 成功工具呼叫：只留標題+參數
DROP        = re.compile(r'^### (💭 Reasoning|ℹ️)')

# <details>...</details> 整塊（含 summary 與內容）
DETAILS_RE = re.compile(r'<details>.*?</details>', re.DOTALL)

# 成功工具呼叫 body 的最大字元數（超過則截斷）
# 處理 MCP server 等未被 <details> 包裝的大量 JSON 輸出
BODY_MAX_CHARS = 800

# 路徑壓縮：至少出現這麼多次才會觸發替換
PATH_MIN_OCCURRENCES = 20

# 絕對路徑模式（Windows / Unix，至少 3 層目錄）
_WIN_PATH_RE  = re.compile(r'[A-Z]:\\(?:[^\\*?"<>|\n]+\\){3,}')
_UNIX_PATH_RE = re.compile(r'/(?:home|Users)/(?:[^/\n]+/){3,}')


def split_sections(text: str) -> list[tuple[str, str]]:
    """將 markdown 切成 (heading, body) 的清單，第一個 heading 可能是空字串（檔案開頭）"""
    parts = SECTION_RE.split(text)
    sections = []
    it = iter(parts)
    prefix = next(it)
    if prefix.strip():
        sections.append(('', prefix))
    for heading in it:
        body = next(it, '')
        sections.append((heading, body))
    return sections


def clean_tool_body(body: str) -> str:
    """工具呼叫 body：移除 <details>，若仍超過閾值則截斷"""
    body = DETAILS_RE.sub('', body)

    # 截斷超大 body（如 MCP 工具的裸 JSON 輸出）
    content = body.strip()
    if len(content) > BODY_MAX_CHARS:
        truncated_chars = len(content) - BODY_MAX_CHARS
        body = content[:BODY_MAX_CHARS] + f'\n\n*[… {truncated_chars} chars truncated]*\n'

    body = re.sub(r'\n{3,}', '\n\n', body)
    return body


def compress_paths(text: str) -> tuple[str, str | None]:
    """自動偵測最頻繁的絕對路徑前綴並替換為相對路徑。

    回傳 (text, replaced_prefix)，若無替換則 replaced_prefix 為 None。
    """
    found = _WIN_PATH_RE.findall(text) + _UNIX_PATH_RE.findall(text)
    if not found:
        return text, None

    prefix, count = Counter(found).most_common(1)[0]
    if count < PATH_MIN_OCCURRENCES:
        return text, None

    sep = '\\' if '\\' in prefix else '/'
    return text.replace(prefix, '.' + sep), prefix


def clean(text: str) -> str:
    sections = split_sections(text)
    out = []

    for heading, body in sections:
        if not heading:
            out.append(body)
            continue

        if DROP.match(heading):
            continue

        if KEEP_FULL.match(heading):
            out.append(heading)
            out.append(body)
            continue

        if KEEP_HEADER.match(heading):
            out.append(heading)
            out.append(clean_tool_body(body))
            continue

        # 其他未知 section（如 ❌ 失敗工具呼叫）一律保留
        out.append(heading)
        out.append(body)

    result = '\n'.join(out)
    result = re.sub(r'\n{3,}', '\n\n', result)

    # 壓縮重複出現的絕對路徑前綴
    result, _ = compress_paths(result)

    return result.strip() + '\n'


def main():
    import argparse
    parser = argparse.ArgumentParser(description='清洗 Copilot CLI session markdown')
    parser.add_argument('input', help='輸入 .md 檔案')
    parser.add_argument('-o', '--output', help='輸出檔案（預設：input.cleaned.md）')
    args = parser.parse_args()

    src = Path(args.input)
    if not src.exists():
        print(f'❌ 找不到檔案：{src}', file=sys.stderr)
        sys.exit(1)

    dst = Path(args.output) if args.output else src.with_suffix('.cleaned.md')

    text = src.read_text(encoding='utf-8')
    cleaned = clean(text)

    dst.write_text(cleaned, encoding='utf-8')

    orig_kb  = len(text.encode()) / 1024
    clean_kb = len(cleaned.encode()) / 1024
    ratio    = (1 - clean_kb / orig_kb) * 100
    print(f'✅ 完成：{src.name}')
    print(f'   原始：{orig_kb:.1f} KB  →  清洗後：{clean_kb:.1f} KB  (縮減 {ratio:.1f}%)')
    print(f'   輸出：{dst}')


if __name__ == '__main__':
    main()
