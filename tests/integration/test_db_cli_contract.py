import json
import subprocess
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
import sys as _sys
CLASSIFIER_EXE = ROOT_DIR / ("classifier.exe" if _sys.platform == "win32" else "classifier")


def _write_data_json(db_dir: Path, code: str) -> None:
    db_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": "1.0",
        "videos": {
            code: {
                "code": code,
                "title": f"title-{code}",
                "studio": "",
                "actresses": [],
                "tags": [],
                "notes": "",
                "metadata": {},
                "created_at": "2024-01-01T00:00:00+00:00",
                "updated_at": "2024-01-01T00:00:00+00:00",
            }
        },
        "actresses": {},
        "links": [],
    }
    (db_dir / "data.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def test_db_merge_accepts_source_with_data_dir(tmp_path):
    source_dir = tmp_path / "source_db"
    target_dir = tmp_path / "target_db"
    _write_data_json(source_dir, "TEST-001")
    _write_data_json(target_dir, "EXISTING-001")

    result = subprocess.run(
        [
            str(CLASSIFIER_EXE),
            "db",
            "merge",
            "-source",
            str(source_dir / "data.json"),
            "-data-dir",
            str(target_dir),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0, result.stderr

    merged = json.loads((target_dir / "data.json").read_text(encoding="utf-8"))
    assert "TEST-001" in merged["videos"]
