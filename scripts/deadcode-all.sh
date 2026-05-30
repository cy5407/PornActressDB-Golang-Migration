#!/usr/bin/env bash
# deadcode-all.sh — 雙 binary 死碼交集腳本 (bash 版,主用為 deadcode-all.ps1)
#
# 目的:消除「`deadcode ./cmd/scanner` 把只有 wails 用的函數誤報死碼」的假陽性。
# 做法:同時對兩個 binary 跑 `deadcode`,各自輸出 unreachable 清單,
#       取交集(只有兩個 binary 都不可達才算真死碼),排除 *_test.go。
#
# 兩個 binary 起點:
#   1. Root module (actress-classifier)  → ./cmd/scanner
#   2. Wails module (wails-app)          → wails-app/ 內 deadcode .
#
# 注意:wails-app 是獨立 module(自己的 go.mod),且 module name 不同,
#       所以必須用 `-filter=`(空 regex)才能看到 wails 端對 actress-classifier/pkg/*
#       的可達性分析,否則預設 filter 會只看 wails-app 自己 module。
#
# 用法:
#   bash scripts/deadcode-all.sh
#   DEADCODE_EXE=/path/to/deadcode bash scripts/deadcode-all.sh
#
# 退出碼:任一 deadcode 子命令非零退出,本腳本也非零退出。

set -euo pipefail

# ---------- 0) 找 deadcode 執行檔 ----------
resolve_deadcode() {
    if [[ -n "${DEADCODE_EXE:-}" ]]; then
        if [[ -x "$DEADCODE_EXE" ]] || [[ -f "$DEADCODE_EXE" ]]; then
            echo "$DEADCODE_EXE"
            return 0
        fi
        echo "找不到 deadcode:$DEADCODE_EXE" >&2
        return 1
    fi
    if command -v deadcode >/dev/null 2>&1; then
        command -v deadcode
        return 0
    fi
    # fallback: GOPATH/bin/deadcode(.exe)
    local gopath
    gopath="${GOPATH:-}"
    if [[ -z "$gopath" ]] && command -v go >/dev/null 2>&1; then
        gopath="$(go env GOPATH 2>/dev/null || true)"
    fi
    if [[ -n "$gopath" ]]; then
        for name in deadcode.exe deadcode; do
            local cand="$gopath/bin/$name"
            if [[ -f "$cand" ]]; then
                echo "$cand"
                return 0
            fi
        done
    fi
    echo "找不到 deadcode。請先 go install golang.org/x/tools/cmd/deadcode@latest,或設 DEADCODE_EXE。" >&2
    return 1
}

# ---------- 1) 鎖定 repo root(腳本的 ../) ----------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WAILS_DIR="$REPO_ROOT/wails-app"

if [[ ! -f "$REPO_ROOT/go.mod" ]]; then
    echo "repo root 沒有 go.mod:$REPO_ROOT" >&2
    exit 1
fi
if [[ ! -f "$WAILS_DIR/go.mod" ]]; then
    echo "wails-app 沒有 go.mod:$WAILS_DIR" >&2
    exit 1
fi

DEADCODE="$(resolve_deadcode)"
PYTHON="${PYTHON:-python}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    if command -v python3 >/dev/null 2>&1; then
        PYTHON=python3
    else
        echo "找不到 python(用來 parse deadcode JSON)。" >&2
        exit 1
    fi
fi

echo "[deadcode-all] 使用 deadcode: $DEADCODE"
echo "[deadcode-all] repo root  : $REPO_ROOT"
echo "[deadcode-all] wails dir  : $WAILS_DIR"
echo ""

# ---------- 2) 跑 deadcode -json 兩次,各自存暫存 ----------
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

ROOT_JSON="$TMP_DIR/root.json"
WAILS_JSON="$TMP_DIR/wails.json"

echo "[deadcode-all] [root cmd/scanner] 跑 deadcode -filter= -json ./cmd/scanner ..."
(cd "$REPO_ROOT" && "$DEADCODE" -filter= -json ./cmd/scanner) > "$ROOT_JSON"

echo "[deadcode-all] [wails-app] 跑 deadcode -filter= -json . (cwd=$WAILS_DIR) ..."
(cd "$WAILS_DIR" && "$DEADCODE" -filter= -json .) > "$WAILS_JSON"

# ---------- 3) parse + 交集 + 差集,輸出 ----------
"$PYTHON" - "$ROOT_JSON" "$WAILS_JSON" <<'PYEOF'
import json
import os
import sys


def load_dead_set(path):
    """讀 deadcode -json 輸出,回傳 fully-qualified 死碼符號 set,排除 *_test.go。"""
    with open(path, encoding="utf-8") as f:
        raw = f.read().strip()
    if not raw or raw == "null":
        return set()
    data = json.loads(raw)
    if not isinstance(data, list):
        data = [data]
    out = set()
    for pkg in data:
        pkg_path = pkg.get("Path") or ""
        if not pkg_path:
            continue
        for fn in pkg.get("Funcs") or []:
            pos = fn.get("Position") or {}
            file_ = (pos.get("File") or "").replace("\\", "/")
            if file_.endswith("_test.go"):
                continue
            name = fn.get("Name")
            if not name:
                continue
            out.add(f"{pkg_path}.{name}")
    return out


root_path, wails_path = sys.argv[1], sys.argv[2]
root_dead = load_dead_set(root_path)
wails_dead = load_dead_set(wails_path)

intersection = sorted(root_dead & wails_dead)
only_root = sorted(root_dead - wails_dead)
only_wails = sorted(wails_dead - root_dead)

print()
print(f"[deadcode-all] root cmd/scanner unreachable(非測試):{len(root_dead)}")
print(f"[deadcode-all] wails-app       unreachable(非測試):{len(wails_dead)}")
print()

print("==== Real dead code (unreachable from BOTH binaries) ====")
print("# 兩個 binary 都看不到 → 真死碼,可安全刪除(刪前還是建議 grep 確認 reflect / //go:linkname 沒在用)。")
print(f"# 共 {len(intersection)} 個符號。")
if not intersection:
    print("(無)")
else:
    for s in intersection:
        print(f"  {s}")
print()

print("==== Single-binary-only (DO NOT DELETE — used by the other binary) ====")
print("# 只在其中一邊 dead,代表另一邊在用。刪掉會打壞另一個 binary。")
print()
print(f"-- Dead in cmd/scanner only (wails-app uses these) ---- {len(only_root)} 個")
if not only_root:
    print("(無)")
else:
    for s in only_root:
        print(f"  {s}")
print()
print(f"-- Dead in wails-app only (cmd/scanner uses these) ---- {len(only_wails)} 個")
if not only_wails:
    print("(無)")
else:
    for s in only_wails:
        print(f"  {s}")
print()

print("==== Summary ====")
print(f"  root  dead = {len(root_dead)}")
print(f"  wails dead = {len(wails_dead)}")
print(f"  intersect  = {len(intersection)}  (真死碼)")
print(f"  only-root  = {len(only_root)}      (wails 在用 → 勿刪)")
print(f"  only-wails = {len(only_wails)}     (cmd/scanner 在用 → 勿刪)")
PYEOF
