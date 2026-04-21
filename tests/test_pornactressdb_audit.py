import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT_DIR / "docs" / "pornactressdb_audit.py"

spec = importlib.util.spec_from_file_location("pornactressdb_audit", MODULE_PATH)
audit = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = audit
assert spec.loader is not None
spec.loader.exec_module(audit)


def _init_git_repo(repo: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)


def test_scan_keeps_live_source_and_core_docs_as_review_only_when_untracked(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / "src/services").mkdir(parents=True)
    (tmp_path / "src/services/go_cli.py").write_text("print('live')\n", encoding="utf-8")
    (tmp_path / "MIGRATION_STATUS.md").write_text("current summary\n", encoding="utf-8")
    (tmp_path / ".audit_report.json").write_text("{}\n", encoding="utf-8")

    findings = audit.scan_project(tmp_path)
    untracked = findings["categories"]["untracked_files"]["files"]
    source_entry = next(item for item in untracked if item["file"] == "src/services/go_cli.py")
    doc_entry = next(item for item in untracked if item["file"] == "MIGRATION_STATUS.md")

    generated = findings["categories"]["generated_reports"]["files"]
    report_entry = next(item for item in generated if item["file"] == ".audit_report.json")

    assert source_entry["action"] == "manual_review"
    assert source_entry["risk_level"] == "high"
    assert "不可直接刪除" in source_entry["recommendation"]

    assert doc_entry["action"] == "manual_review"
    assert doc_entry["risk_level"] == "medium"
    assert "納入版控" in doc_entry["recommendation"]

    assert report_entry["action"] == "delete_candidate"
    assert report_entry["risk_level"] == "low"


def test_source_like_backup_is_manual_review_not_delete_candidate(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / "src/services").mkdir(parents=True)
    target = tmp_path / "src/services/safe_searcher.py.bak"
    target.write_text("backup\n", encoding="utf-8")

    findings = audit.scan_project(tmp_path)
    backup_files = findings["categories"]["backup_artifacts"]["files"]
    entry = next(item for item in backup_files if item["file"] == "src/services/safe_searcher.py.bak")

    assert entry["action"] == "manual_review"
    assert entry["risk_level"] == "high"


def test_untracked_docs_are_review_only_not_delete_candidates(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / "docs/plans").mkdir(parents=True)
    plan_file = tmp_path / "docs/plans/new-plan.md"
    plan_file.write_text("draft plan\n", encoding="utf-8")

    findings = audit.scan_project(tmp_path)
    untracked = findings["categories"]["untracked_files"]["files"]
    entry = next(item for item in untracked if item["file"] == "docs/plans/new-plan.md")

    assert entry["action"] == "manual_review"
    assert entry["risk_level"] == "medium"
    assert "納入版控" in entry["recommendation"]


def test_build_artifact_defaults_to_ignore_candidate(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / "build").mkdir(parents=True)
    artifact = tmp_path / "build" / "app.exe"
    artifact.write_bytes(b"binary")

    findings = audit.scan_project(tmp_path)
    build_files = findings["categories"]["build_artifacts"]["files"]
    entry = next(item for item in build_files if item["file"] == "build/app.exe")

    assert entry["action"] == "ignore_candidate"
    assert entry["risk_level"] == "low"
