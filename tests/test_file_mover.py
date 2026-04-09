from src.utils.file_mover import FileMover


def test_file_mover_uses_explicit_go_exe_path(monkeypatch):
    captured = {}

    def fake_is_available(exe_path=None):
        captured["is_available_exe_path"] = exe_path
        return True

    def fake_move_file(source, destination, strategy, exe_path=None):
        captured["move_file_exe_path"] = exe_path
        return {
            "success": True,
            "source": source,
            "destination": destination,
            "skipped": False,
            "renamed": None,
        }

    monkeypatch.setattr("src.services.go_cli.is_available", fake_is_available)
    monkeypatch.setattr("src.services.go_cli.move_file", fake_move_file)

    mover = FileMover(use_go=True, go_exe_path=r"C:\custom\classifier.exe")
    result = mover.move_file(r"C:\source.mp4", r"C:\dest.mp4")

    assert result["success"] is True
    assert captured["is_available_exe_path"] == r"C:\custom\classifier.exe"
    assert captured["move_file_exe_path"] == r"C:\custom\classifier.exe"
