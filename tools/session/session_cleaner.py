#!/usr/bin/env python3
"""
session_cleaner.py — Copilot CLI session markdown 清洗工具

保留：
  - ### 👤 User        使用者訊息（全文）
  - ### 💬 Copilot     AI 結論（全文）
  - ### ✅ `tool`      成功工具呼叫（保留標題+查詢參數，刪除 <details> 展開內容）
  - ### ❌ `tool`      失敗的工具呼叫（保留完整內容，含 stderr/stack trace）
  - <sub>⏱️ ...        時間戳（保留）

刪除：
  - ### 💭 Reasoning   AI 思考過程
  - ### ℹ️ Info        環境樣板資訊
  - <details>...</details> 成功工具呼叫的完整輸出

用法：
  python session_cleaner.py input.md
  python session_cleaner.py input.md -o output.md
"""

import re
import sys
from pathlib import Path


# 每個 section 的起始標記（### 開頭）
SECTION_RE = re.compile(r'^(### .+)$', re.MULTILINE)

# 判斷 section 類型
KEEP_FULL   = re.compile(r'^### (👤 User|💬 Copilot)')
KEEP_HEADER = re.compile(r'^### ✅')   # 成功工具呼叫：只留標題+參數
DROP        = re.compile(r'^### (💭 Reasoning|ℹ️)')

# <details>...</details> 整塊（含 summary 與內容）
DETAILS_RE = re.compile(r'<details>.*?</details>', re.DOTALL)

# 程式碼區塊包住的查詢參數（工具呼叫第一個 ``` 區塊）
FIRST_CODE_RE = re.compile(r'```[\s\S]*?```')


def split_sections(text: str) -> list[tuple[str, str]]:
    """將 markdown 切成 (heading, body) 的清單，第一個 heading 可能是空字串（檔案開頭）"""
    parts = SECTION_RE.split(text)
    # split 產生 [前綴, heading1, body1, heading2, body2, ...]
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
    """工具呼叫 body：移除 <details> 展開內容，保留標題行與查詢參數區塊"""
    # 移除 <details> 整塊
    body = DETAILS_RE.sub('', body)
    # 移除殘留多餘空行（連續 3 行以上空行壓成 2 行）
    body = re.sub(r'\n{3,}', '\n\n', body)
    return body


def clean(text: str) -> str:
    sections = split_sections(text)
    out = []

    for heading, body in sections:
        # 無標題（檔案開頭，通常是 # 標題與 session info）
        if not heading:
            out.append(body)
            continue

        if DROP.match(heading):
            # 完全丟棄，但保留時間戳（時間戳在上一個 section body 尾端）
            continue

        if KEEP_FULL.match(heading):
            out.append(heading)
            out.append(body)
            continue

        if KEEP_HEADER.match(heading):
            out.append(heading)
            out.append(clean_tool_body(body))
            continue

        # 其他未知 section（如自訂小標題）一律保留
        out.append(heading)
        out.append(body)

    result = '\n'.join(out)
    # 最後整理：連續空行壓縮
    result = re.sub(r'\n{3,}', '\n\n', result)
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
