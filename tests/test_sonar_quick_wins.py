from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT_DIR / relative_path).read_text(encoding="utf-8")


def test_go_quick_wins_source_regressions():
    checks = {
        "pkg/database/jsondb.go": [
            "if err2 := db.appendJournalEntry(entry); err2 == nil {",
            "if removeErr := os.Remove(filepath.Join(backupDir, name)); removeErr == nil {",
            "if removeErr := os.Remove(remaining[0]); removeErr == nil {",
            "func (db *JSONDatabase) BackupCleanup(days int, maxCount int) (int, error) {",
        ],
        "pkg/mover/dir_move.go": [
            "if mkErr := safefile.MkdirAll(filepath.Dir(dst), 0700); mkErr == nil {",
            "if renameErr := os.Rename(src, dst); renameErr == nil {",
        ],
        "pkg/studio/identifier.go": [
            "func (si *StudioIdentifier) NormalizeStudioName(studioName string, videoCode string) string {",
        ],
    }

    failures = []
    for relative_path, snippets in checks.items():
        source = _read(relative_path)
        for snippet in snippets:
            if snippet in source:
                failures.append(f"{relative_path}: still contains {snippet!r}")

    assert not failures, "\n".join(failures)


def test_python_quick_wins_source_regressions():
    checks = {
        "src/models/incremental_json_database.py": [
            'logger.info(f"🔄 開始合併 journal（委派 Go CLI）...")',
        ],
        "src/scrapers/base_scraper.py": [
            "retry_on_errors: list[ErrorType] = None",
            "for domain in list(self.domain_health.keys()):",
        ],
        "src/scrapers/cache_manager.py": [
            "for cache_key, entry_data in list(",
        ],
        "src/scrapers/encoding_utils.py": [
            "except (UnicodeDecodeError, UnicodeError):",
        ],
        "src/services/go_cli.py": [
            "except (GoError, Exception) as e:",
        ],
        "src/services/safe_javdb_searcher.py": [
            "if soup is None:",
        ],
    }

    failures = []
    for relative_path, snippets in checks.items():
        source = _read(relative_path)
        for snippet in snippets:
            if snippet in source:
                failures.append(f"{relative_path}: still contains {snippet!r}")

    assert not failures, "\n".join(failures)
