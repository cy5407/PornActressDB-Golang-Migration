#!/usr/bin/env python3
"""
Python integration example - call Go scanner via subprocess
"""

import json
import subprocess
import sys
from pathlib import Path


def scan_directory_go(directory: str, workers: int = 10) -> list[dict]:
    """Call Go scanner and return results"""

    # Path to compiled Go executable (in project root)
    scanner_exe = Path(__file__).parent.parent.parent / "classifier.exe"

    if not scanner_exe.exists():
        raise FileNotFoundError(f"Scanner not found: {scanner_exe}")

    # Run scanner
    result = subprocess.run(
        [str(scanner_exe), "-dir", directory, "-workers", str(workers)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    if result.returncode != 0:
        raise RuntimeError(f"Scanner failed: {result.stderr}")

    # Parse JSON output
    return json.loads(result.stdout)


def main():
    if len(sys.argv) < 2:
        print("Usage: python go_integration.py <directory>")
        sys.exit(1)

    directory = sys.argv[1]

    print(f"Scanning: {directory}")
    results = scan_directory_go(directory, workers=20)

    print(f"\nFound {len(results)} videos:")
    for item in results[:10]:  # Show first 10
        print(f"  {item['code']}: {item['path']}")

    if len(results) > 10:
        print(f"  ... and {len(results) - 10} more")


if __name__ == "__main__":
    main()
