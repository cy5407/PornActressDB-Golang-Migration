"""Integration contract tests for `classifier.exe db ...` against the
SQLite-only runtime (Phase C2 onwards).

These tests exercise the real prebuilt CLI binary against a temporary
data dir. They are deliberately thin — wrapper-level expectations live in
``tests/test_go_cli_contracts.py``; here we lock end-to-end exit codes,
file layout, and contract surfaces that Python wrappers and operators rely
on.
"""

import json
import shutil
import subprocess
import sys as _sys
from pathlib import Path

import pytest


ROOT_DIR = Path(__file__).resolve().parents[2]
CLASSIFIER_EXE = ROOT_DIR / ("classifier.exe" if _sys.platform == "win32" else "classifier")


def _classifier_exe_available() -> bool:
    return CLASSIFIER_EXE.exists()


pytestmark = pytest.mark.skipif(
    not _classifier_exe_available(),
    reason="classifier.exe not built; run `go build -o classifier.exe ./cmd/scanner` first",
)


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


def _run_classifier(args, check: bool = True) -> subprocess.CompletedProcess:
    """Invoke classifier.exe with stable args. Captures text output."""
    cp = subprocess.run(
        [str(CLASSIFIER_EXE), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if check and cp.returncode != 0:
        raise AssertionError(
            f"classifier.exe {args} exit={cp.returncode}\nstdout:\n{cp.stdout}\nstderr:\n{cp.stderr}"
        )
    return cp


def _seed_fixture_data_dir(tmp_path: Path, name: str = "json_db_minimal") -> Path:
    """Copy the CI verify-sync fixture into a writable temp dir.

    The same fixture is used by `.github/workflows/sqlite-verify-sync.yml`,
    so this keeps local tests aligned with what CI sees.
    """
    src = ROOT_DIR / "tests" / "fixtures" / name
    dst = tmp_path / name
    shutil.copytree(src, dst)
    return dst


def test_db_merge_accepts_source_with_data_dir(tmp_path):
    """`db merge -source <other/data.json> -data-dir <target>` adds the
    source videos into the SQLite mirror at `<target>/db.sqlite` (custom
    `-data-dir` puts SQLite as a direct child per spec § 7.1; default
    `data/json_db` is the only path that maps to a sibling).
    """
    source_dir = tmp_path / "source_db"
    target_dir = tmp_path / "target_db"
    _write_data_json(source_dir, "TEST-001")
    _write_data_json(target_dir, "EXISTING-001")

    _run_classifier(
        [
            "db",
            "merge",
            "-source",
            str(source_dir / "data.json"),
            "-data-dir",
            str(target_dir),
        ]
    )

    # Custom -data-dir → sibling SQLite is a direct child, not the
    # sibling-rule reserved for the default data/json_db path.
    assert (target_dir / "db.sqlite").exists(), "merge target SQLite must exist post-merge"

    # Verify merge took effect via the SQLite-backed contract surface,
    # not by reading data.json (which is no longer the source of truth).
    # Flag must precede positional — Go's flag.Parse stops at first non-flag
    # arg, mirroring how src/services/go_cli.py:db_get_video builds the cmd.
    got = _run_classifier(["db", "get", "-data-dir", str(target_dir), "TEST-001"])
    record = json.loads(got.stdout)
    assert record.get("code") == "TEST-001", f"unexpected db get payload: {record!r}"

    # The pre-existing entry must still be reachable too (merge != replace).
    got_existing = _run_classifier(["db", "get", "-data-dir", str(target_dir), "EXISTING-001"])
    record_existing = json.loads(got_existing.stdout)
    assert record_existing.get("code") == "EXISTING-001"


# ---------------------------------------------------------------------------
# Phase D contract audit additions — `migrate-from-json` / `verify-sync` /
# `resync-from-json` / `export-json` / `backup-*` against the SQLite-only
# runtime. These lock spec § 7.1 (sibling lookup), the dual-snapshot backup
# contract, and the exit-2 mutual-exclusion shape.
# ---------------------------------------------------------------------------


def test_db_migrate_from_json_imports_fixture_to_sibling_sqlite(tmp_path):
    """`-data-dir <json_db>` where the directory's basename is `json_db`
    maps SQLite to a SIBLING `db.sqlite`. Phase D rebinds the test against
    a fresh copy of the CI fixture so we exercise the same path the
    workflow uses.

    Important: spec § 7.1 only fires the sibling rule for the *default*
    `data/json_db` directory (matched by absolute-path equality with
    `database.DefaultDataDir`). Any other directory — even one literally
    named `json_db` under a different parent — gets `<dir>/db.sqlite` as
    a direct child. The test uses the literal default to lock the
    documented behaviour without depending on the cwd.
    """
    # Use the default `data/json_db` so the sibling rule fires. We
    # rebuild it from the CI fixture under tmp_path and chdir there so
    # `data/db.sqlite` lands inside tmp_path, not the worktree.
    fixture = _seed_fixture_data_dir(tmp_path, "json_db_minimal")
    data_root = tmp_path / "data"
    data_root.mkdir()
    target_json_dir = data_root / "json_db"
    shutil.copytree(fixture, target_json_dir)

    cp = subprocess.run(
        [
            str(CLASSIFIER_EXE),
            "db",
            "migrate-from-json",
            "-data-dir",
            "data/json_db",
        ],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert cp.returncode == 0, cp.stderr

    report = json.loads(cp.stdout)
    for key in ("videos_imported", "actresses_imported", "links_imported"):
        assert key in report, f"migrate report missing {key}: {report!r}"
    assert report["videos_imported"] >= 1

    # Spec § 7.1: sibling, not nested.
    assert (data_root / "db.sqlite").exists(), "default -data-dir must place db.sqlite as sibling"
    assert not (target_json_dir / "db.sqlite").exists(), \
        "default -data-dir must NOT nest db.sqlite under json_db/"


def test_db_verify_sync_passes_after_migrate(tmp_path):
    """`db verify-sync` must exit 0 immediately after a successful
    migrate-from-json against the CI fixture.
    """
    data_root = tmp_path / "data"
    data_root.mkdir()
    fixture = _seed_fixture_data_dir(tmp_path, "json_db_minimal")
    shutil.copytree(fixture, data_root / "json_db")

    common = dict(cwd=str(tmp_path), capture_output=True, text=True, encoding="utf-8", check=False)
    mig = subprocess.run(
        [str(CLASSIFIER_EXE), "db", "migrate-from-json", "-data-dir", "data/json_db"],
        **common,
    )
    assert mig.returncode == 0, mig.stderr

    vs = subprocess.run(
        [str(CLASSIFIER_EXE), "db", "verify-sync", "-data-dir", "data/json_db"],
        **common,
    )
    assert vs.returncode == 0, f"verify-sync stdout={vs.stdout}\nstderr={vs.stderr}"


def test_db_export_json_round_trips_with_verify_sync(tmp_path):
    """migrate → export-json → verify-sync stays green; the exported file
    is consistent with the live SQLite.
    """
    data_root = tmp_path / "data"
    data_root.mkdir()
    fixture = _seed_fixture_data_dir(tmp_path, "json_db_minimal")
    shutil.copytree(fixture, data_root / "json_db")

    common = dict(cwd=str(tmp_path), capture_output=True, text=True, encoding="utf-8", check=False)
    mig = subprocess.run(
        [str(CLASSIFIER_EXE), "db", "migrate-from-json", "-data-dir", "data/json_db"],
        **common,
    )
    assert mig.returncode == 0, mig.stderr

    exported_path = data_root / "json_db" / "data.json"
    exp = subprocess.run(
        [
            str(CLASSIFIER_EXE), "db", "export-json",
            "-data-dir", "data/json_db",
            "-output", str(exported_path),
        ],
        **common,
    )
    assert exp.returncode == 0, exp.stderr
    assert exported_path.exists()

    vs = subprocess.run(
        [str(CLASSIFIER_EXE), "db", "verify-sync", "-data-dir", "data/json_db"],
        **common,
    )
    assert vs.returncode == 0, f"verify-sync after export stdout={vs.stdout}\nstderr={vs.stderr}"


def test_db_backup_create_emits_dual_snapshot_pair(tmp_path):
    """`db backup-create` must produce a `.sqlite` + `.json` pair with the
    same timestamp stem. The JSON snapshot is derived from SQLite (not
    from `data.json`), so it must be consistent with the live mirror.
    """
    data_root = tmp_path / "data"
    data_root.mkdir()
    fixture = _seed_fixture_data_dir(tmp_path, "json_db_minimal")
    shutil.copytree(fixture, data_root / "json_db")

    common = dict(cwd=str(tmp_path), capture_output=True, text=True, encoding="utf-8", check=False)
    mig = subprocess.run(
        [str(CLASSIFIER_EXE), "db", "migrate-from-json", "-data-dir", "data/json_db"],
        **common,
    )
    assert mig.returncode == 0, mig.stderr

    bc = subprocess.run(
        [str(CLASSIFIER_EXE), "db", "backup-create", "-data-dir", "data/json_db", "-json"],
        **common,
    )
    assert bc.returncode == 0, bc.stderr

    payload = json.loads(bc.stdout)
    assert payload.get("success") is True
    backup_path = payload.get("backup_path")
    json_export_path = payload.get("json_export_path")
    legacy_alias = payload.get("path")

    assert backup_path, f"backup-create missing backup_path: {payload!r}"
    assert json_export_path, f"backup-create missing json_export_path: {payload!r}"
    # Legacy alias kept for src/models/json_database.py.create_backup().
    assert legacy_alias == json_export_path, \
        f"legacy `path` alias must mirror json_export_path: {payload!r}"

    # backup_path / json_export_path are emitted relative to the CLI's
    # cwd (which we set to tmp_path), so resolve them under that root.
    backup_path_p = (tmp_path / backup_path).resolve()
    json_export_path_p = (tmp_path / json_export_path).resolve()
    assert backup_path_p.exists() and backup_path_p.suffix == ".sqlite", \
        f"sqlite backup missing: {backup_path_p}"
    assert json_export_path_p.exists() and json_export_path_p.suffix == ".json", \
        f"json backup missing: {json_export_path_p}"
    # Both files share the same stem (e.g. backup_<timestamp>).
    assert backup_path_p.stem == json_export_path_p.stem


def test_db_backup_restore_mutual_exclusion_exit_code_2(tmp_path):
    """`-backup-path` and `-from-json` are mutually exclusive; combining
    them must exit 2 (the convention for "bad CLI input", distinct from
    runtime failures which exit 1).
    """
    data_root = tmp_path / "data"
    data_root.mkdir()
    fixture = _seed_fixture_data_dir(tmp_path, "json_db_minimal")
    shutil.copytree(fixture, data_root / "json_db")

    common = dict(cwd=str(tmp_path), capture_output=True, text=True, encoding="utf-8", check=False)
    cp = subprocess.run(
        [
            str(CLASSIFIER_EXE), "db", "backup-restore",
            "-data-dir", "data/json_db",
            "-backup-path", str(data_root / "json_db" / "data.json"),
            "-from-json", str(data_root / "json_db" / "data.json"),
        ],
        **common,
    )
    assert cp.returncode == 2, (
        f"mutual-exclusion violation should exit 2, got {cp.returncode}\n"
        f"stdout={cp.stdout}\nstderr={cp.stderr}"
    )


def test_db_backup_restore_accepts_sqlite_and_json_extensions(tmp_path):
    """`db backup-restore -backup-path <path>` must succeed for both
    `.sqlite` (canonical Phase C1 path) and `.json` (legacy alias kept
    alive for src/services/go_cli.py:db_backup_restore callers). The
    `restored` field on the JSON payload distinguishes the two paths
    so wrappers can detect which restore flow ran.
    """
    data_root = tmp_path / "data"
    data_root.mkdir()
    fixture = _seed_fixture_data_dir(tmp_path, "json_db_minimal")
    shutil.copytree(fixture, data_root / "json_db")

    common = dict(cwd=str(tmp_path), capture_output=True, text=True, encoding="utf-8", check=False)
    mig = subprocess.run(
        [str(CLASSIFIER_EXE), "db", "migrate-from-json", "-data-dir", "data/json_db"],
        **common,
    )
    assert mig.returncode == 0, mig.stderr

    bc = subprocess.run(
        [str(CLASSIFIER_EXE), "db", "backup-create", "-data-dir", "data/json_db", "-json"],
        **common,
    )
    assert bc.returncode == 0, bc.stderr
    bc_payload = json.loads(bc.stdout)
    sqlite_backup = bc_payload["backup_path"]
    json_backup = bc_payload["json_export_path"]

    # Path 1: `.sqlite` extension → runBackupRestoreFromSQLite branch.
    restore_sqlite = subprocess.run(
        [
            str(CLASSIFIER_EXE), "db", "backup-restore",
            "-data-dir", "data/json_db",
            "-backup-path", sqlite_backup,
        ],
        **common,
    )
    assert restore_sqlite.returncode == 0, (
        f"sqlite restore failed: stdout={restore_sqlite.stdout}\n"
        f"stderr={restore_sqlite.stderr}"
    )
    sqlite_payload = json.loads(restore_sqlite.stdout)
    assert sqlite_payload.get("success") is True
    assert sqlite_payload.get("restored") == "sqlite", (
        f"sqlite extension must route to sqlite restore: {sqlite_payload!r}"
    )

    # Path 2: `.json` extension → legacy BackupRestore branch.
    restore_json = subprocess.run(
        [
            str(CLASSIFIER_EXE), "db", "backup-restore",
            "-data-dir", "data/json_db",
            "-backup-path", json_backup,
        ],
        **common,
    )
    assert restore_json.returncode == 0, (
        f"json restore failed: stdout={restore_json.stdout}\n"
        f"stderr={restore_json.stderr}"
    )
    json_payload = json.loads(restore_json.stdout)
    assert json_payload.get("success") is True
    assert json_payload.get("restored") == "json", (
        f"json extension must route to legacy json restore: {json_payload!r}"
    )


def test_db_resync_from_json_wipes_then_repopulates(tmp_path):
    """`db resync-from-json` (C-DB9) must wipe `videos` /
    `video_actress_links` / `actresses` / `actress_aliases` and rebuild
    them from the JSON source — so a row deleted from SQLite via the CLI
    reappears after resync. db_meta is upserted (not wiped), so prior
    metadata stays consistent.
    """
    data_root = tmp_path / "data"
    data_root.mkdir()
    fixture = _seed_fixture_data_dir(tmp_path, "json_db_minimal")
    shutil.copytree(fixture, data_root / "json_db")

    common = dict(cwd=str(tmp_path), capture_output=True, text=True, encoding="utf-8", check=False)
    mig = subprocess.run(
        [str(CLASSIFIER_EXE), "db", "migrate-from-json", "-data-dir", "data/json_db"],
        **common,
    )
    assert mig.returncode == 0, mig.stderr

    # Force drift: delete one of the fixture videos from SQLite. After
    # this the SQLite mirror diverges from data.json, which is exactly
    # the drift scenario resync-from-json exists to repair.
    target_code = "STARS-707"
    deleted = subprocess.run(
        [str(CLASSIFIER_EXE), "db", "delete", "-data-dir", "data/json_db", target_code],
        **common,
    )
    assert deleted.returncode == 0, deleted.stderr

    # Sanity: the deleted video really is gone (db get returns exit 1).
    missing = subprocess.run(
        [str(CLASSIFIER_EXE), "db", "get", "-data-dir", "data/json_db", target_code],
        **common,
    )
    assert missing.returncode != 0, (
        f"pre-resync setup broken; expected db get {target_code} to fail, "
        f"got stdout={missing.stdout}"
    )

    # Resync — wipe + rebuild in a single transaction. Report struct
    # mirrors MigrationReport so the same required keys apply.
    resync = subprocess.run(
        [
            str(CLASSIFIER_EXE), "db", "resync-from-json",
            "-data-dir", "data/json_db",
        ],
        **common,
    )
    assert resync.returncode == 0, (
        f"resync failed: stdout={resync.stdout}\nstderr={resync.stderr}"
    )
    report = json.loads(resync.stdout)
    assert report.get("success") is True
    assert report.get("videos_imported", 0) >= 3, (
        f"resync should re-import every fixture video, got {report!r}"
    )

    # The wipe + rebuild must restore the deleted row.
    restored = subprocess.run(
        [str(CLASSIFIER_EXE), "db", "get", "-data-dir", "data/json_db", target_code],
        **common,
    )
    assert restored.returncode == 0, (
        f"resync did not restore {target_code}: stdout={restored.stdout}\n"
        f"stderr={restored.stderr}"
    )
    record = json.loads(restored.stdout)
    assert record.get("code") == target_code

    # And SQLite ↔ JSON must be back in sync.
    vs = subprocess.run(
        [str(CLASSIFIER_EXE), "db", "verify-sync", "-data-dir", "data/json_db"],
        **common,
    )
    assert vs.returncode == 0, (
        f"verify-sync after resync failed: stdout={vs.stdout}\nstderr={vs.stderr}"
    )
