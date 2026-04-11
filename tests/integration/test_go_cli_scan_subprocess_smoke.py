from pathlib import Path

from src.services import go_cli


ROOT_DIR = Path(__file__).resolve().parents[2]
CLASSIFIER_EXE = ROOT_DIR / "classifier.exe"


def test_go_cli_run_scan_returns_real_json_list(tmp_path):
    videos_dir = tmp_path / "videos"
    videos_dir.mkdir()
    (videos_dir / "SONE-001.mp4").touch()
    (videos_dir / "IPX-002.mkv").touch()

    payload = go_cli.run(
        ["scan", "-dir", str(videos_dir), "-workers", "2", "-recursive=false"],
        exe_path=str(CLASSIFIER_EXE),
    )

    assert isinstance(payload, list)
    names = {Path(item["path"]).name for item in payload}
    assert names == {"SONE-001.mp4", "IPX-002.mkv"}


def test_go_cli_run_scan_recursive_includes_nested(tmp_path):
    videos_dir = tmp_path / "videos"
    videos_dir.mkdir()
    (videos_dir / "SONE-001.mp4").touch()
    nested = videos_dir / "nested"
    nested.mkdir()
    (nested / "STARS-700.mp4").touch()

    payload = go_cli.run(["scan", "-dir", str(videos_dir), "-workers", "2"], exe_path=str(CLASSIFIER_EXE))

    assert isinstance(payload, list)
    names = {Path(item["path"]).name for item in payload}
    assert "SONE-001.mp4" in names
    assert "STARS-700.mp4" in names
