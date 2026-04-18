from pathlib import Path

from src.utils.scanner import UnifiedFileScanner


ROOT_DIR = Path(__file__).resolve().parents[2]
import sys as _sys
CLASSIFIER_EXE = ROOT_DIR / ("classifier.exe" if _sys.platform == "win32" else "classifier")


def test_scanner_scan_directory_uses_real_go_cli(tmp_path):
    videos_dir = tmp_path / "videos"
    videos_dir.mkdir()
    (videos_dir / "SONE-001.mp4").touch()
    (videos_dir / "IPX-002.mkv").touch()

    scanner = UnifiedFileScanner(use_go=True, go_exe_path=str(CLASSIFIER_EXE), go_workers=2)

    results = scanner.scan_directory(str(videos_dir), recursive=False)

    names = {path.name for path in results}
    assert "SONE-001.mp4" in names
    assert "IPX-002.mkv" in names


def test_scanner_scan_with_codes_uses_real_go_cli(tmp_path):
    videos_dir = tmp_path / "videos"
    videos_dir.mkdir()
    (videos_dir / "SONE-001.mp4").touch()
    (videos_dir / "STARS-700.avi").touch()

    scanner = UnifiedFileScanner(use_go=True, go_exe_path=str(CLASSIFIER_EXE), go_workers=2)

    results = scanner.scan_with_codes(str(videos_dir), recursive=False)

    by_name = {Path(item["path"]).name: item["code"] for item in results}
    assert by_name["SONE-001.mp4"] == "SONE-001"
    assert by_name["STARS-700.avi"] == "STARS-700"


def test_scanner_non_recursive_skips_subdirectory_when_using_real_go_cli(tmp_path):
    videos_dir = tmp_path / "videos"
    videos_dir.mkdir()
    (videos_dir / "SONE-001.mp4").touch()
    sub_dir = videos_dir / "subdir"
    sub_dir.mkdir()
    (sub_dir / "STARS-700.mp4").touch()

    scanner = UnifiedFileScanner(use_go=True, go_exe_path=str(CLASSIFIER_EXE), go_workers=2)

    results = scanner.scan_directory(str(videos_dir), recursive=False)
    names = {path.name for path in results}

    assert "SONE-001.mp4" in names
    assert "STARS-700.mp4" not in names


def test_scanner_recursive_includes_subdirectory_when_using_real_go_cli(tmp_path):
    videos_dir = tmp_path / "videos"
    videos_dir.mkdir()
    (videos_dir / "SONE-001.mp4").touch()
    sub_dir = videos_dir / "subdir"
    sub_dir.mkdir()
    (sub_dir / "STARS-700.mp4").touch()

    scanner = UnifiedFileScanner(use_go=True, go_exe_path=str(CLASSIFIER_EXE), go_workers=2)

    results = scanner.scan_directory(str(videos_dir), recursive=True)
    names = {path.name for path in results}

    assert "SONE-001.mp4" in names
    assert "STARS-700.mp4" in names
