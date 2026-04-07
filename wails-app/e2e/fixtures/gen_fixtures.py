#!/usr/bin/env python3
"""Generate E2E video fixtures and a matching JSON database snapshot.

Creates:
- videos/: 100 zero-byte dummy video files
- test_db/data.json: database payload compatible with pkg/database/types.go
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

PREFIXES = ["STARS", "ABW", "IPX", "MIAA", "SSIS", "HMN", "MIDV", "FSDSS", "WAAA", "JUL"]
EXTENSIONS = [".mp4", ".mkv", ".avi"]
MAJOR_STUDIOS = [
    "S1", "MOODYZ", "PREMIUM", "FALENO", "KAWAII", "ATTACKERS", "E-BODY", "SOD", "PRESTIGE", "MADONNA", "OPPAI", "FITCH", "WANZ",
]

ROOT = Path(__file__).resolve().parent
VIDEOS_DIR = ROOT / "videos"
TEST_DB_DIR = ROOT / "test_db"
DB_PATH = TEST_DB_DIR / "data.json"


@dataclass(frozen=True)
class FixtureItem:
    code: str
    filename: str
    prefix: str
    studio: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> None:
    random.seed(42)
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    TEST_DB_DIR.mkdir(parents=True, exist_ok=True)

    counts = {prefix: 10 for prefix in PREFIXES}
    items: list[FixtureItem] = []
    used_codes: set[str] = set()

    # Generate 100 unique codes, 10 per prefix.
    studio_map = {
        prefix: MAJOR_STUDIOS[i % len(MAJOR_STUDIOS)]
        for i, prefix in enumerate(PREFIXES)
    }

    for prefix in PREFIXES:
        while len([item for item in items if item.prefix == prefix]) < counts[prefix]:
            number = random.randint(1, 999)
            code = f"{prefix}-{number:03d}"
            if code in used_codes:
                continue
            used_codes.add(code)
            ext = random.choice(EXTENSIONS)
            filename = f"{code}{ext}"
            items.append(
                FixtureItem(
                    code=code,
                    filename=filename,
                    prefix=prefix,
                    studio=studio_map[prefix],
                )
            )

    # Create zero-byte files.
    for item in items:
        (VIDEOS_DIR / item.filename).touch(exist_ok=True)

    now = utc_now()
    videos = {}
    for item in items:
        videos[item.code] = {
            "code": item.code,
            "title": "",
            "studio": item.studio,
            "actresses": [],
            "search_status": "failed",
            "original_filename": item.filename,
            "file_path": f"videos/{item.filename}",
            "created_at": now,
            "updated_at": now,
        }

    db_payload = {
        "schema_version": "1.0.0",
        "metadata": {
            "description": "E2E fixture database snapshot",
            "encoding": "UTF-8",
        },
        "data_hash": "",
        "created_at": now,
        "updated_at": now,
        "videos": videos,
        "actresses": {},
        "links": [],
        "statistics": {
            "total_videos": len(videos),
            "total_actresses": 0,
            "total_links": 0,
        },
    }

    with DB_PATH.open("w", encoding="utf-8") as fh:
        json.dump(db_payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print(f"已建立 {len(items)} 個檔案，DB 已寫入")


if __name__ == "__main__":
    main()
