# -*- coding: utf-8 -*-
"""
產生 wiki-data.js — 將所有 wiki/*.md 內容內嵌為 JS 變數。
執行後 viewer.html 可直接用 file:// 開啟（不需要 server）。

執行方式：
    python wiki/gen_data.py
    python wiki/gen_data.py --watch   (監聽模式，存檔後自動重新產生)
"""
import json
import re
import sys
import time
from pathlib import Path

WIKI_DIR = Path(__file__).parent
OUT_FILE = WIKI_DIR / "wiki-data.js"

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
FM_FIELD_RE = re.compile(r"^(\w+):\s*(.+)$", re.MULTILINE)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """回傳 (metadata_dict, content_without_frontmatter)"""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fields = {k: v.strip() for k, v in FM_FIELD_RE.findall(m.group(1))}
    return fields, text[m.end():]


def build_data(wiki_dir: Path) -> tuple[dict[str, str], dict[str, dict]]:
    data = {}
    meta = {}
    for md in sorted(wiki_dir.rglob("*.md")):
        rel = md.relative_to(wiki_dir)
        if len(rel.parts) > 2:
            continue  # 不支援三層以上
        key = str(rel).replace("\\", "/")
        raw = md.read_text(encoding="utf-8")
        fm, content = parse_frontmatter(raw)
        data[key] = content
        if fm:
            meta[key] = fm
    return data, meta


def generate(wiki_dir: Path = WIKI_DIR):
    data, meta = build_data(wiki_dir)
    js = "// 自動產生，請勿手動編輯。執行 python wiki/gen_data.py 更新。\n"
    js += f"window.WIKI_DATA = {json.dumps(data, ensure_ascii=False, indent=2)};\n"
    js += f"window.WIKI_META = {json.dumps(meta, ensure_ascii=False, indent=2)};\n"
    OUT_FILE.write_text(js, encoding="utf-8")
    print(f"✅ 已產生 wiki-data.js（{len(data)} 個頁面，{len(meta)} 個含 frontmatter）")


def watch(wiki_dir: Path = WIKI_DIR):
    print("👀 監聽模式啟動，偵測到 .md 變更時自動更新 wiki-data.js ... (Ctrl+C 停止)")
    last_mtimes: dict[str, float] = {}

    def get_mtimes():
        return {str(p): p.stat().st_mtime for p in wiki_dir.rglob("*.md")}

    last_mtimes = get_mtimes()
    generate(wiki_dir)

    try:
        while True:
            time.sleep(1)
            current = get_mtimes()
            if current != last_mtimes:
                last_mtimes = current
                generate(wiki_dir)
    except KeyboardInterrupt:
        print("\n停止監聽。")


if __name__ == "__main__":
    if "--watch" in sys.argv:
        watch()
    else:
        generate()
