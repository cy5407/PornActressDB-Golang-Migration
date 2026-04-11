import json
import subprocess
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
CLASSIFIER_EXE = ROOT_DIR / "classifier.exe"


def test_classifier_scan_subprocess_returns_real_paths(tmp_path):
    videos_dir = tmp_path / "videos"
    videos_dir.mkdir()
    (videos_dir / "SONE-001.mp4").touch()
    (videos_dir / "IPX-002.mkv").touch()

    result = subprocess.run(
        [str(CLASSIFIER_EXE), "scan", "-dir", str(videos_dir), "-workers", "2", "-recursive=false"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    names = {Path(item["path"]).name for item in payload}
    assert names == {"SONE-001.mp4", "IPX-002.mkv"}


def test_classifier_scan_subprocess_recursive_includes_nested(tmp_path):
    videos_dir = tmp_path / "videos"
    videos_dir.mkdir()
    (videos_dir / "SONE-001.mp4").touch()
    nested = videos_dir / "nested"
    nested.mkdir()
    (nested / "STARS-700.mp4").touch()

    result = subprocess.run(
        [str(CLASSIFIER_EXE), "scan", "-dir", str(videos_dir), "-workers", "2"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    names = {Path(item["path"]).name for item in payload}
    assert "SONE-001.mp4" in names
    assert "STARS-700.mp4" in names
