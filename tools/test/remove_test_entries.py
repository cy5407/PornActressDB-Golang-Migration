"""
依照 test-file/ 目錄內的檔名，從 data.json 移除對應的影片記錄。

用途：測試前清除已知片單，讓 APP 重新搜尋分類以驗證功能。

用法：
  python tools/test/remove_test_entries.py                    # dry-run，只顯示會刪什麼
  python tools/test/remove_test_entries.py --write            # 實際寫入
  python tools/test/remove_test_entries.py --test-dir <路徑>  # 指定測試目錄
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEST_DIR = REPO_ROOT / "test-file"
DEFAULT_DB_PATH = REPO_ROOT / "data" / "json_db" / "data.json"


def extract_codes(test_dir: Path) -> list[str]:
    return [p.stem.upper() for p in test_dir.iterdir() if p.is_file()]


def backup(db_path: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = db_path.with_name(f"data.backup_{ts}.json")
    shutil.copy2(db_path, dest)
    return dest


def remove_entries(db_path: Path, codes: list[str], write: bool) -> None:
    with open(db_path, encoding="utf-8") as f:
        db = json.load(f)

    videos: dict = db.get("videos", {})
    found = [c for c in codes if c in videos]
    missing = [c for c in codes if c not in videos]

    print(f"\n掃描 test-file/：{len(codes)} 個番號")
    print(f"  在 data.json 中找到：{len(found)} 筆")
    print(f"  不在 data.json 中：  {len(missing)} 筆")

    if found:
        print("\n將刪除：")
        for c in sorted(found):
            print(f"  - {c}")

    if missing:
        print("\n不存在（略過）：")
        for c in sorted(missing):
            print(f"  ? {c}")

    if not write:
        print("\n[dry-run] 未寫入，加 --write 才會實際刪除。")
        return

    if not found:
        print("\n沒有可刪除的記錄，結束。")
        return

    backup_path = backup(db_path)
    print(f"\n備份至：{backup_path.name}")

    for c in found:
        del videos[c]

    db["videos"] = videos
    db["updated_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    if "statistics" in db and "total_videos" in db["statistics"]:
        db["statistics"]["total_videos"] = len(videos)

    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

    print(f"完成：已刪除 {len(found)} 筆，data.json 剩餘 {len(videos)} 筆。")


def main() -> None:
    parser = argparse.ArgumentParser(description="從 data.json 移除 test-file/ 內的影片記錄")
    parser.add_argument("--test-dir", type=Path, default=DEFAULT_TEST_DIR)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--write", action="store_true", help="實際寫入（預設 dry-run）")
    args = parser.parse_args()

    if not args.test_dir.exists():
        print(f"錯誤：找不到測試目錄 {args.test_dir}")
        raise SystemExit(1)
    if not args.db.exists():
        print(f"錯誤：找不到資料庫 {args.db}")
        raise SystemExit(1)

    codes = extract_codes(args.test_dir)
    remove_entries(args.db, codes, args.write)


if __name__ == "__main__":
    main()
