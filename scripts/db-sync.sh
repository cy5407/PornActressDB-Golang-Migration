#!/usr/bin/env bash
# db-sync.sh — Shadow SQLite 同步腳本
#
# ⚠ 已退役：此腳本串接的是 v2 shadow 流程（db-init / db-import-json / db-compare-json，
# 寫入 data/shadow.sqlite），已非 runtime source of truth。runtime 為 v3 SQLite
# （data/db.sqlite）。請改用：
#   - classifier db verify-sync / export-json / resync-from-json（v3 runtime）
#   - db-tool db-import-json-v3 / db-verify（v3 runtime）
# 本腳本僅供 legacy v2 shadow 診斷保留，不應再進入正式同步流程。
#
# 用法: bash scripts/db-sync.sh [--benchmark] [--skip-compact]
#
# 執行順序: compact → db-init → db-import-json → db-compare-json
# compare 失敗則中止，不繼續跑 benchmark

set -euo pipefail

CLASSIFIER="./classifier"
DB_TOOL="./tools-rs/target/release/db-tool"
JSON_PATH="data/json_db/data.json"
SQLITE_PATH="data/shadow.sqlite"

BENCHMARK=0
SKIP_COMPACT=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --benchmark)    BENCHMARK=1 ;;
        --skip-compact) SKIP_COMPACT=1 ;;
        *) echo "未知選項: $1" >&2; exit 1 ;;
    esac
    shift
done

if [[ ! -x "$CLASSIFIER" ]]; then
    echo "找不到 $CLASSIFIER，請先執行: go build -o classifier ./cmd/scanner" >&2
    exit 1
fi
if [[ ! -x "$DB_TOOL" ]]; then
    echo "找不到 $DB_TOOL，請先執行: cd tools-rs && cargo build --release" >&2
    exit 1
fi
if [[ ! -f "$JSON_PATH" ]]; then
    echo "找不到 $JSON_PATH，請先確認 data.json 存在" >&2
    exit 1
fi

if [[ $SKIP_COMPACT -eq 0 ]]; then
    echo "[1/4] compact journal..."
    "$CLASSIFIER" db compact
else
    echo "[1/4] compact 略過 (--skip-compact)"
fi

echo "[2/4] db-init..."
"$DB_TOOL" db-init --sqlite "$SQLITE_PATH" --replace

echo "[3/4] db-import-json..."
"$DB_TOOL" db-import-json --json "$JSON_PATH" --sqlite "$SQLITE_PATH" --replace

echo "[4/4] db-compare-json..."
if ! "$DB_TOOL" db-compare-json --json "$JSON_PATH" --sqlite "$SQLITE_PATH"; then
    echo ""
    echo "✗ compare 失敗，shadow DB 可能不完整" >&2
    exit 1
fi

if [[ $BENCHMARK -eq 1 ]]; then
    echo "[+]  db-benchmark..."
    "$DB_TOOL" db-benchmark --json "$JSON_PATH" --sqlite "$SQLITE_PATH"
fi

echo ""
echo "✓ shadow DB 同步完成"
