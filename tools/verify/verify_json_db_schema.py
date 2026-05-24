"""
驗證 JSON 資料庫影片 schema 是否符合目前規範。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.models.json_types import SEARCH_METHODS, SEARCH_STATUSES, VIDEO_ALLOWED_FIELDS

ALLOWED_STATUSES = set(SEARCH_STATUSES.values())
ALLOWED_METHODS = set(SEARCH_METHODS.values())
REQUIRED_ROOT_KEYS = {"videos", "actresses", "links", "statistics"}


@dataclass
class VerificationReport:
    total_videos: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    invalid_statuses: Counter = field(default_factory=Counter)
    invalid_methods: Counter = field(default_factory=Counter)
    unknown_fields: Counter = field(default_factory=Counter)
    missing_fields: Counter = field(default_factory=Counter)
    mismatched_ids: list[str] = field(default_factory=list)
    redundant_ids: list[str] = field(default_factory=list)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_database(data: dict) -> VerificationReport:
    report = VerificationReport()

    for key in REQUIRED_ROOT_KEYS:
        if key not in data:
            report.errors.append(f"缺少根層欄位: {key}")

    videos = data.get("videos", {})
    if not isinstance(videos, dict):
        report.errors.append("videos 必須是 dict")
        return report

    for code, video in videos.items():
        report.total_videos += 1
        if not isinstance(video, dict):
            report.errors.append(f"{code}: video 記錄不是 dict")
            continue

        for field_name in ("original_filename", "file_path"):
            if field_name not in video:
                report.missing_fields[field_name] += 1
                report.warnings.append(f"{code}: 缺少選填欄位 {field_name}")

        actresses = video.get("actresses")
        if not isinstance(actresses, list):
            report.errors.append(f"{code}: actresses 必須是 list")

        search_status = video.get("search_status")
        if search_status not in ALLOWED_STATUSES:
            report.invalid_statuses[str(search_status)] += 1
            report.errors.append(f"{code}: 非法 search_status={search_status!r}")

        search_method = video.get("search_method")
        if search_method in (None, ""):
            report.invalid_methods[str(search_method)] += 1
            report.warnings.append(f"{code}: search_method 空白，建議正規化")
        elif search_method not in ALLOWED_METHODS:
            report.invalid_methods[str(search_method)] += 1
            report.warnings.append(f"{code}: 非 canonical search_method={search_method!r}")

        for field_name in video:
            if field_name not in VIDEO_ALLOWED_FIELDS and field_name != "id":
                report.unknown_fields[field_name] += 1
                report.errors.append(f"{code}: 未知欄位 {field_name}")

        if "id" in video:
            if str(video["id"]) == code:
                report.redundant_ids.append(code)
                report.warnings.append(f"{code}: 仍保留可移除的重複 id 欄位")
            else:
                report.mismatched_ids.append(code)
                report.errors.append(f"{code}: id 與 code 不一致 ({video['id']!r})")

    return report


def print_counter(title: str, counter: Counter) -> None:
    if not counter:
        return
    print(f"\n{title}")
    for item, count in counter.most_common():
        print(f"  - {item!r}: {count}")


def print_examples(title: str, items: list[str], limit: int = 10) -> None:
    if not items:
        return
    print(f"\n{title}")
    for item in items[:limit]:
        print(f"  - {item}")
    if len(items) > limit:
        print(f"  ... 另外 {len(items) - limit} 筆")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="驗證 JSON 資料庫影片 schema")
    parser.add_argument(
        "input",
        nargs="?",
        default=str(REPO_ROOT / "data" / "json_db" / "data.json"),
        help="要驗證的 data.json 路徑",
    )
    parser.add_argument(
        "--max-errors",
        type=int,
        default=20,
        help="終端最多顯示幾筆錯誤明細",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).resolve()

    if not input_path.exists():
        print(f"找不到輸入檔案: {input_path}")
        return 1

    data = load_json(input_path)
    report = verify_database(data)

    print("驗證摘要")
    print(f"  檔案: {input_path}")
    print(f"  影片總數: {report.total_videos}")
    print(f"  錯誤數: {len(report.errors)}")
    print(f"  警告數: {len(report.warnings)}")

    if report.errors:
        print("\n錯誤明細")
        for message in report.errors[: args.max_errors]:
            print(f"  - {message}")
        if len(report.errors) > args.max_errors:
            print(f"  ... 另外 {len(report.errors) - args.max_errors} 筆錯誤")

    if report.warnings:
        print("\n警告明細")
        for message in report.warnings[: args.max_errors]:
            print(f"  - {message}")
        if len(report.warnings) > args.max_errors:
            print(f"  ... 另外 {len(report.warnings) - args.max_errors} 筆警告")

    print_counter("非法 search_status 統計", report.invalid_statuses)
    print_counter("非法 search_method 統計", report.invalid_methods)
    print_counter("未知欄位統計", report.unknown_fields)
    print_counter("缺漏欄位統計", report.missing_fields)
    print_examples("id 與 code 不一致的影片", report.mismatched_ids)
    print_examples("仍保留重複 id 的影片", report.redundant_ids)

    if report.errors:
        return 1

    print("\n驗證通過")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
