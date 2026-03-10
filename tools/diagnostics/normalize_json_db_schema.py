"""
正規化 JSON 資料庫影片 schema。

功能：
- 正規化 search_status / search_method
- 移除重複 id 與測試欄位
- 補齊 original_filename / file_path 欄位
- 支援 dry-run、輸出到新檔、原地寫回與備份
"""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.models.json_types import SEARCH_METHODS, SEARCH_STATUSES, VIDEO_ALLOWED_FIELDS


STATUS_MAPPING = {
    "": SEARCH_STATUSES["IMPORTED"],
    "success": SEARCH_STATUSES["SEARCHED_FOUND"],
    "partial": SEARCH_STATUSES["SEARCHED_FOUND"],
    "failed": SEARCH_STATUSES["SEARCH_ERROR"],
    "imported": SEARCH_STATUSES["IMPORTED"],
    "searched_found": SEARCH_STATUSES["SEARCHED_FOUND"],
    "searched_not_found": SEARCH_STATUSES["SEARCHED_NOT_FOUND"],
    "search_error": SEARCH_STATUSES["SEARCH_ERROR"],
    "not_searched": SEARCH_STATUSES["IMPORTED"],
    "video_not_found": SEARCH_STATUSES["SEARCHED_NOT_FOUND"],
    "no_actress_found": SEARCH_STATUSES["SEARCHED_NOT_FOUND"],
    "searched_multiple": SEARCH_STATUSES["SEARCHED_FOUND"],
}

METHOD_MAPPING = {
    "legacy-import": SEARCH_METHODS["LEGACY_IMPORT"],
    "AV-WIKI": SEARCH_METHODS["AV_WIKI"],
    "AV-WIKI (安全增強版)": SEARCH_METHODS["AV_WIKI"],
    "AV-WIKI (安全 增強版)": SEARCH_METHODS["AV_WIKI"],
    "chiba-f.net": SEARCH_METHODS["CHIBA_F"],
    "chiba-f.net (安全增強版)": SEARCH_METHODS["CHIBA_F"],
    "JAVDB": SEARCH_METHODS["JAVDB"],
    "JAVDB (安全增強版)": SEARCH_METHODS["JAVDB"],
    "cascade": SEARCH_METHODS["CASCADE"],
}


@dataclass
class NormalizationReport:
    total_videos: int = 0
    changed_videos: int = 0
    removed_duplicate_ids: int = 0
    mismatched_ids: list[str] = field(default_factory=list)
    removed_test_fields: int = 0
    normalized_statuses: Counter = field(default_factory=Counter)
    normalized_methods: Counter = field(default_factory=Counter)
    filled_original_filename: int = 0
    filled_file_path: int = 0
    blank_original_filename: int = 0
    blank_file_path: int = 0
    unknown_statuses: Counter = field(default_factory=Counter)
    unknown_methods: Counter = field(default_factory=Counter)
    unknown_fields: Counter = field(default_factory=Counter)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_status(value: object, report: NormalizationReport) -> str:
    original = "" if value is None else str(value).strip()
    normalized = STATUS_MAPPING.get(original)
    if normalized is None:
        report.unknown_statuses[original] += 1
        return SEARCH_STATUSES["SEARCH_ERROR"]
    if original != normalized:
        report.normalized_statuses[f"{original} -> {normalized}"] += 1
    return normalized


def normalize_method(value: object, report: NormalizationReport, status: str) -> str:
    original = "" if value is None else str(value).strip()

    if not original:
        fallback = (
            SEARCH_METHODS["LEGACY_IMPORT"]
            if status == SEARCH_STATUSES["IMPORTED"]
            else SEARCH_METHODS["CASCADE"]
        )
        report.normalized_methods[f"{original!r} -> {fallback}"] += 1
        return fallback

    normalized = METHOD_MAPPING.get(original)
    if normalized is None:
        report.unknown_methods[original] += 1
        return original
    if original != normalized:
        report.normalized_methods[f"{original} -> {normalized}"] += 1
    return normalized


def infer_original_filename(code: str, video: dict) -> str:
    file_path = str(video.get("file_path", "") or "").strip()
    if file_path:
        return Path(file_path).name

    original_filename = str(video.get("original_filename", "") or "").strip()
    if original_filename:
        return original_filename

    return f"{code}.mp4"


def infer_file_path(video: dict) -> str:
    file_path = str(video.get("file_path", "") or "").strip()
    if file_path:
        return file_path
    return ""


def normalize_database(data: dict) -> tuple[dict, NormalizationReport]:
    normalized = copy.deepcopy(data)
    report = NormalizationReport()
    videos = normalized.get("videos", {})

    for code, video in videos.items():
        report.total_videos += 1
        changed = False

        if not isinstance(video, dict):
            continue

        for field_name in list(video.keys()):
            if field_name not in VIDEO_ALLOWED_FIELDS and field_name not in {"id", "test_field"}:
                report.unknown_fields[field_name] += 1

        normalized_status = normalize_status(video.get("search_status"), report)
        if video.get("search_status") != normalized_status:
            video["search_status"] = normalized_status
            changed = True

        normalized_method = normalize_method(
            video.get("search_method"),
            report,
            normalized_status,
        )
        if video.get("search_method") != normalized_method:
            video["search_method"] = normalized_method
            changed = True

        if "id" in video:
            if str(video["id"]) == code:
                del video["id"]
                report.removed_duplicate_ids += 1
                changed = True
            else:
                report.mismatched_ids.append(code)

        if "test_field" in video:
            del video["test_field"]
            report.removed_test_fields += 1
            changed = True

        original_filename = str(video.get("original_filename", "") or "").strip()
        if not original_filename:
            video["original_filename"] = infer_original_filename(code, video)
            if video["original_filename"]:
                report.filled_original_filename += 1
            else:
                report.blank_original_filename += 1
            changed = True

        file_path = str(video.get("file_path", "") or "").strip()
        if not file_path:
            video["file_path"] = infer_file_path(video)
            if video["file_path"]:
                report.filled_file_path += 1
            else:
                report.blank_file_path += 1
            changed = True

        if changed:
            report.changed_videos += 1

    return normalized, report


def create_backup(input_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = input_path.with_name(f"{input_path.stem}.backup_{timestamp}{input_path.suffix}")
    shutil.copy2(input_path, backup_path)
    return backup_path


def print_report(report: NormalizationReport) -> None:
    print("正規化摘要")
    print(f"  總影片數: {report.total_videos}")
    print(f"  變更筆數: {report.changed_videos}")
    print(f"  移除重複 id: {report.removed_duplicate_ids}")
    print(f"  移除 test_field: {report.removed_test_fields}")
    print(f"  補齊 original_filename: {report.filled_original_filename}")
    print(f"  補齊 file_path: {report.filled_file_path}")
    print(f"  空白 original_filename: {report.blank_original_filename}")
    print(f"  空白 file_path: {report.blank_file_path}")

    if report.normalized_statuses:
        print("\nsearch_status 正規化:")
        for item, count in report.normalized_statuses.most_common():
            print(f"  - {item}: {count}")

    if report.normalized_methods:
        print("\nsearch_method 正規化:")
        for item, count in report.normalized_methods.most_common():
            print(f"  - {item}: {count}")

    if report.unknown_statuses:
        print("\n未知 search_status:")
        for item, count in report.unknown_statuses.most_common():
            print(f"  - {item!r}: {count}")

    if report.unknown_methods:
        print("\n未知 search_method:")
        for item, count in report.unknown_methods.most_common():
            print(f"  - {item!r}: {count}")

    if report.mismatched_ids:
        print("\nid 與 code 不一致的影片:")
        for code in report.mismatched_ids[:10]:
            print(f"  - {code}")
        if len(report.mismatched_ids) > 10:
            print(f"  ... 另外 {len(report.mismatched_ids) - 10} 筆")

    if report.unknown_fields:
        print("\n未知欄位:")
        for item, count in report.unknown_fields.most_common():
            print(f"  - {item}: {count}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="正規化 JSON 資料庫影片 schema")
    parser.add_argument(
        "input",
        nargs="?",
        default=str(REPO_ROOT / "data" / "json_db" / "data.json"),
        help="輸入的 data.json 路徑",
    )
    parser.add_argument(
        "--output",
        help="將正規化結果寫到指定檔案，不修改原檔",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="直接覆寫原始 data.json（執行前會自動備份）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="僅顯示預計變更，不輸出檔案",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).resolve()

    if not input_path.exists():
        print(f"找不到輸入檔案: {input_path}")
        return 1

    data = load_json(input_path)
    normalized, report = normalize_database(data)
    print_report(report)

    if args.dry_run:
        print("\nDry-run 完成，未寫入任何檔案。")
        return 0

    if args.write and args.output:
        print("不能同時使用 --write 與 --output")
        return 1

    if args.write:
        backup_path = create_backup(input_path)
        save_json(input_path, normalized)
        print(f"\n已備份原檔: {backup_path}")
        print(f"已寫回原檔: {input_path}")
        return 0

    if args.output:
        output_path = Path(args.output).resolve()
        save_json(output_path, normalized)
        print(f"\n已輸出正規化檔案: {output_path}")
        return 0

    print("\n未指定輸出方式；如需寫檔請使用 --dry-run、--output 或 --write。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
