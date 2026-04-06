# -*- coding: utf-8 -*-
"""
Wiki 瀏覽器伺服器
執行方式：python wiki/serve.py
"""
import http.server
import json
import os
import sys
import threading
import webbrowser
from pathlib import Path

# 強制 stdout 使用 UTF-8（避免 cp950 emoji 崩潰）
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PORT = 8765
WIKI_DIR = Path(__file__).parent

# 目錄分組順序與標題
SECTION_ORDER = ["root", "architecture", "patterns", "pitfalls"]
SECTION_META = {
    "root":         {"title": "📖 索引"},
    "architecture": {"title": "🏛️ 架構"},
    "patterns":     {"title": "📐 開發模式"},
    "pitfalls":     {"title": "🪲 踩坑紀錄"},
}

# 個別檔案 icon（path key → emoji）；未知檔案使用預設值
FILE_ICONS = {
    "index": "🏠", "log": "📋",
    "architecture/overview": "🗺️", "architecture/go-cli": "⚙️",
    "architecture/go-bridge": "🌉", "architecture/database": "🗄️",
    "architecture/search-engine": "🔍",
    "patterns/add-go-api-function": "➕", "patterns/add-go-cli-command": "🖥️",
    "patterns/add-gui-button": "🖱️", "patterns/naming-conventions": "📝",
    "patterns/pyinstaller": "📦", "patterns/zero-actress-retry": "🔄",
    "patterns/remove-python-fallback": "🗑️",
}


def _read_h1(path: Path) -> str:
    """讀取 markdown 第一個 H1；失敗時回傳人性化的檔名。"""
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
    except Exception:
        pass
    return path.stem.replace("-", " ").replace("_", " ").title()


def build_manifest(wiki_dir: Path) -> dict:
    """掃描 wiki/ 目錄，回傳側欄結構 JSON。"""
    groups: dict[str, list] = {k: [] for k in SECTION_ORDER}

    for md in sorted(wiki_dir.rglob("*.md")):
        rel = md.relative_to(wiki_dir)
        parts = rel.parts
        if len(parts) == 1:
            group = "root"
            file_path = parts[0]
            path_key = md.stem
        elif len(parts) == 2:
            group = parts[0]
            file_path = "/".join(parts)
            path_key = f"{parts[0]}/{md.stem}"
        else:
            continue  # 不支援三層以上

        if group not in groups:
            continue

        default_icon = "❌" if group == "pitfalls" else "📄"
        groups[group].append({
            "label": _read_h1(md),
            "icon":  FILE_ICONS.get(path_key, default_icon),
            "file":  file_path,
            "path":  path_key,
        })

    return {
        "sections": [
            {"title": SECTION_META[k]["title"], "items": groups[k]}
            for k in SECTION_ORDER
            if groups[k]
        ]
    }


class WikiHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WIKI_DIR), **kwargs)

    def do_GET(self):
        if self.path == "/api/manifest":
            self._serve_manifest()
        else:
            super().do_GET()

    def _serve_manifest(self):
        data = json.dumps(build_manifest(WIKI_DIR), ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        pass  # 靜音 access log


def main():
    os.chdir(WIKI_DIR)
    with http.server.HTTPServer(("127.0.0.1", PORT), WikiHandler) as httpd:
        url = f"http://127.0.0.1:{PORT}/viewer.html"
        print(f"Wiki viewer: {url}")
        print("Press Ctrl+C to stop.")
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
