# -*- coding: utf-8 -*-
"""
Wiki 瀏覽器伺服器
執行方式：python wiki/serve.py
"""
import http.server
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


class WikiHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WIKI_DIR), **kwargs)

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
