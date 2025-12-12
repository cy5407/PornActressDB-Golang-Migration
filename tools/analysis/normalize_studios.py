#!/usr/bin/env python3
"""Normalize legacy video studios based on code prefixes."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

# Ensure project src/ is importable
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.models.studio import StudioIdentifier  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Normalize studios in data/json_db/data.json so major studios match the"
            " canonical names defined in studios.json."
        )
    )
    parser.add_argument(
        "--studios",
        help=(
            "Comma-separated list of canonical studios to normalize. "
            "Default: include every studio listed in studios.json."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist the normalized studios back to data.json (defaults to dry-run).",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=20,
        help="Number of sample changes to display in the summary (default: 20).",
    )
    return parser.parse_args()


def load_data(data_path: Path) -> dict:
    if not data_path.exists():
        raise FileNotFoundError(f"Cannot locate data file: {data_path}")
    return json.loads(data_path.read_text(encoding="utf-8"))


def determine_targets(identifier: StudioIdentifier, override: str | None) -> list[str]:
    if override:
        return [studio.strip() for studio in override.split(",") if studio.strip()]
    # Preserve ordering defined in studios.json and cover all entries
    return list(identifier.studio_patterns.keys())


def normalize_studios(data: dict, target_set: set[str]) -> dict:
    videos = data.get("videos", {})
    identifier = StudioIdentifier(rules_file=str(REPO_ROOT / "studios.json"))
    matched_counts = Counter()
    change_records = []

    # Precompute canonical matches for every video once so we can inspect stats
    for code, info in videos.items():
        canonical = identifier.identify_studio(code)
        if canonical == "UNKNOWN":
            continue
        if canonical.upper() not in target_set:
            continue

        matched_counts[canonical] += 1
        current = info.get("studio")
        if current == canonical:
            continue

        change_records.append(
            {
                "code": code,
                "old": current,
                "new": canonical,
            }
        )

    return {
        "matched_counts": matched_counts,
        "change_records": change_records,
    }


def write_updates(data_path: Path, data: dict) -> Path:
    backup_dir = data_path.parent / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"data_backup_{timestamp}_pre_studio_fix.json"
    shutil.copy2(data_path, backup_path)

    data["updated_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    data_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return backup_path


def main() -> None:
    args = parse_args()
    data_path = REPO_ROOT / "data" / "json_db" / "data.json"
    data = load_data(data_path)

    identifier = StudioIdentifier(rules_file=str(REPO_ROOT / "studios.json"))
    targets = determine_targets(identifier, args.studios)
    target_set = {studio.upper() for studio in targets}

    stats = normalize_studios(data, target_set)
    change_records = stats["change_records"]

    print("=== Studio Normalization Summary ===")
    print(f"Videos scanned : {len(data.get('videos', {}))}")
    print(f"Target studios : {', '.join(targets)}")
    print(f"Matched videos : {sum(stats['matched_counts'].values())}")
    print(f"Pending updates: {len(change_records)}")

    if stats["matched_counts"]:
        print("\nTop studio matches:")
        for studio, count in stats["matched_counts"].most_common():
            print(f"  - {studio}: {count}")

    if change_records:
        print("\nSample changes:")
        for record in change_records[: args.sample]:
            print(f"  {record['code']}: {record['old'] or 'None'} -> {record['new']}")
    else:
        print("\nNo studio entries require normalization.")

    if args.apply and change_records:
        for record in change_records:
            data["videos"][record["code"]]["studio"] = record["new"]
        backup_path = write_updates(data_path, data)
        print(
            f"\n✅ Updated {len(change_records)} entries. Backup saved to: {backup_path}"
        )
    elif args.apply and not change_records:
        print("\nNothing to update; skipping file write.")
    else:
        print("\nDry run complete; rerun with --apply to persist changes.")


if __name__ == "__main__":
    main()
