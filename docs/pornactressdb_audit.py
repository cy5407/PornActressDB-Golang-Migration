#!/usr/bin/env python3
"""安全版 PornActressDB repo 審計腳本。

目的：盤點 repo 內較可能屬於暫存、產物、備份、或需人工複核的檔案，
避免把 live code / 核心文件直接誤判成可刪項目。

用法：
    python3 docs/pornactressdb_audit.py
    python3 docs/pornactressdb_audit.py --project-root /path/to/repo
    python3 docs/pornactressdb_audit.py --output-dir /tmp/audit-output
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_FILENAMES = (".audit_report.json", ".audit_report.txt")

PROTECTED_PREFIXES = (
    "src/",
    "tests/",
    "tools/",
    "cmd/",
    "pkg/",
    "wails-app/",
    "wiki/",
)

DOC_REVIEW_PREFIXES = (
    "docs/",
    "docs/plans/",
    "docs/internal/",
)

SOURCE_LIKE_SUFFIXES = {
    ".py",
    ".go",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".rs",
    ".java",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".sh",
}

UNTRACKED_REVIEW_SUFFIXES = {
    ".md",
    ".txt",
    ".lock",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
}


@dataclass(frozen=True)
class AuditRule:
    category: str
    rule_id: str
    description: str
    patterns: tuple[str, ...]
    default_action: str
    default_risk: str
    note: str


AUDIT_RULES = (
    AuditRule(
        category="generated_reports",
        rule_id="local_audit_outputs",
        description="本地審計腳本輸出",
        patterns=(".audit_report.json", ".audit_report.txt"),
        default_action="delete_candidate",
        default_risk="low",
        note="屬於本地生成報告，通常不應直接進版控。",
    ),
    AuditRule(
        category="generated_reports",
        rule_id="coverage_reports",
        description="coverage / 測試報告輸出",
        patterns=("coverage.json", "coverage_report.txt", "htmlcov/**/*"),
        default_action="delete_candidate",
        default_risk="low",
        note="屬於測試輸出，可重新生成。",
    ),
    AuditRule(
        category="test_artifacts",
        rule_id="test_file_backups",
        description="test-file 下的備份或暫存檔",
        patterns=(
            "test-file/**/*.bak",
            "test-file/**/*.old",
            "test-file/**/*.tmp",
            "test-file/**/*.temp",
        ),
        default_action="delete_candidate",
        default_risk="low",
        note="測試樣本衍生的備份/暫存檔通常可清理。",
    ),
    AuditRule(
        category="backup_artifacts",
        rule_id="generic_backup_suffix",
        description="一般備份副檔名",
        patterns=("**/*.bak", "**/*.backup", "**/*.old", "**/*.orig", "**/*.rej"),
        default_action="manual_review",
        default_risk="medium",
        note="先看路徑與 git 狀態，不應一律視為可刪。",
    ),
    AuditRule(
        category="build_artifacts",
        rule_id="build_dirs_and_bins",
        description="常見建置產物",
        patterns=(
            "build/**/*",
            "dist/**/*",
            "classifier",
            "scanner",
            "*.exe",
            "*.dll",
            "*.so",
            "*.dylib",
        ),
        default_action="ignore_candidate",
        default_risk="low",
        note="建議由 .gitignore 管理；若已被追蹤需人工確認。",
    ),
    AuditRule(
        category="data_backups",
        rule_id="json_db_backups",
        description="資料庫備份與臨時資料",
        patterns=(
            "data/json_db/*.bak",
            "data/json_db/*.old",
            "data/json_db/*.tmp",
            "data/json_db/*.temp",
            "data/*.tmp",
        ),
        default_action="manual_review",
        default_risk="medium",
        note="資料檔可能是人工保留的保險快照，清理前要確認用途。",
    ),
)


def normalize_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def path_has_protected_prefix(rel_path: str) -> bool:
    return any(rel_path.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def path_is_docs_review_target(rel_path: str) -> bool:
    return any(rel_path.startswith(prefix) for prefix in DOC_REVIEW_PREFIXES)


def path_looks_like_source(rel_path: str) -> bool:
    return Path(rel_path).suffix.lower() in SOURCE_LIKE_SUFFIXES


def run_git(project_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )


def is_git_repo(project_root: Path) -> bool:
    result = run_git(project_root, ["rev-parse", "--is-inside-work-tree"])
    return result.returncode == 0 and result.stdout.strip() == "true"


def is_tracked(project_root: Path, rel_path: str) -> bool:
    result = run_git(project_root, ["ls-files", "--error-unmatch", rel_path])
    return result.returncode == 0


def build_recommendation(action: str, rel_path: str, tracked: bool) -> str:
    tracked_hint = "已被 git 追蹤" if tracked else "目前未被 git 追蹤"
    if action == "delete_candidate":
        return f"低風險候選：可考慮刪除，因為 {tracked_hint} 且屬可重建/暫存產物。"
    if action == "ignore_candidate":
        return f"建議檢查 .gitignore：{tracked_hint}，若非必要產物可忽略而非提交。"
    return f"人工複核：{tracked_hint}，不可因規則命中就直接刪除。"


def classify_action(rule: AuditRule, rel_path: str, tracked: bool) -> tuple[str, str]:
    action = rule.default_action
    risk = rule.default_risk

    if path_has_protected_prefix(rel_path) or path_looks_like_source(rel_path):
        return "manual_review", "high"

    if tracked and action in {"delete_candidate", "ignore_candidate"}:
        return "manual_review", "medium"

    return action, risk


def iter_rule_matches(project_root: Path, rule: AuditRule) -> Iterable[Path]:
    seen: set[Path] = set()
    for pattern in rule.patterns:
        for match in project_root.glob(pattern):
            if match.is_file() and match not in seen:
                seen.add(match)
                yield match


def collect_rule_findings(project_root: Path) -> dict[str, dict]:
    categories: dict[str, dict] = {}

    for rule in AUDIT_RULES:
        files = []
        for match in iter_rule_matches(project_root, rule):
            rel_path = normalize_path(match, project_root)
            tracked = is_tracked(project_root, rel_path) if is_git_repo(project_root) else False
            stat = match.stat()
            action, risk = classify_action(rule, rel_path, tracked)
            files.append(
                {
                    "file": rel_path,
                    "rule_id": rule.rule_id,
                    "description": rule.description,
                    "size_bytes": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "tracked": tracked,
                    "risk_level": risk,
                    "action": action,
                    "note": rule.note,
                    "recommendation": build_recommendation(action, rel_path, tracked),
                }
            )

        if files:
            categories[rule.category] = {
                "description": rule.category,
                "count": len(files),
                "files": sorted(files, key=lambda item: item["file"]),
            }

    return categories


def classify_untracked_file(rel_path: str) -> tuple[str, str, str]:
    path = Path(rel_path)

    if path_has_protected_prefix(rel_path) or path_looks_like_source(rel_path):
        return (
            "manual_review",
            "high",
            "位於程式碼/工具路徑，先確認是否為新功能或暫存實驗，不可直接刪除。",
        )

    if path_is_docs_review_target(rel_path) or path.suffix.lower() in UNTRACKED_REVIEW_SUFFIXES:
        return (
            "manual_review",
            "medium",
            "像是新增文件或鎖檔，應先判斷是否該納入版控，而不是直接忽略或刪除。",
        )

    return (
        "manual_review",
        "low",
        "未追蹤檔案，請確認是要 commit、加入 .gitignore，還是移除。",
    )


def check_untracked_files(project_root: Path) -> list[dict]:
    if not is_git_repo(project_root):
        return []

    result = run_git(project_root, ["ls-files", "--others", "--exclude-standard"])
    if result.returncode != 0:
        return []

    untracked = []
    for line in result.stdout.splitlines():
        rel_path = line.strip()
        if not rel_path:
            continue
        file_path = project_root / rel_path
        if not file_path.exists() or not file_path.is_file():
            continue

        stat = file_path.stat()
        action, risk, recommendation = classify_untracked_file(rel_path)
        untracked.append(
            {
                "file": rel_path,
                "size_bytes": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "tracked": False,
                "risk_level": risk,
                "action": action,
                "recommendation": recommendation,
            }
        )

    return sorted(untracked, key=lambda item: item["file"])


def build_summary(categories: dict[str, dict]) -> dict[str, int]:
    counter: defaultdict[str, int] = defaultdict(int)
    for category in categories.values():
        for file_info in category.get("files", []):
            counter[file_info["action"]] += 1
    return dict(sorted(counter.items()))


def scan_project(project_root: Path) -> dict:
    project_root = Path(project_root).resolve()
    if not project_root.exists():
        return {"error": f"專案目錄不存在: {project_root}"}

    categories = collect_rule_findings(project_root)
    untracked = check_untracked_files(project_root)
    if untracked:
        categories["untracked_files"] = {
            "description": "git 未追蹤檔案（僅提示，不能直接視為可刪）",
            "count": len(untracked),
            "files": untracked,
        }

    findings = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "project_root": str(project_root),
            "scan_type": "safe_repo_audit",
            "is_git_repo": is_git_repo(project_root),
            "protected_prefixes": list(PROTECTED_PREFIXES),
        },
        "summary": build_summary(categories),
        "categories": categories,
        "disclaimer": [
            "本報告只提供候選與風險分級，不可直接當成刪檔指令。",
            "凡是程式碼路徑、核心文件、已追蹤檔案，一律先人工複核。",
            "若命中結果與 live dependency 衝突，應以實際引用與測試結果為準。",
        ],
    }
    return findings


def generate_report(findings: dict) -> str:
    if "error" in findings:
        return findings["error"]

    lines = []
    lines.append("=" * 80)
    lines.append("PornActressDB 安全審計報告")
    lines.append("=" * 80)
    lines.append(f"掃描時間: {findings['metadata']['timestamp']}")
    lines.append(f"專案: {findings['metadata']['project_root']}")
    lines.append(f"Git repo: {findings['metadata']['is_git_repo']}")
    lines.append("")
    lines.append("摘要：")
    if findings.get("summary"):
        for action, count in findings["summary"].items():
            lines.append(f"- {action}: {count}")
    else:
        lines.append("- 無命中項目")

    lines.append("")
    lines.append("重要提醒：")
    for item in findings.get("disclaimer", []):
        lines.append(f"- {item}")

    for category, data in findings.get("categories", {}).items():
        lines.append("")
        lines.append(f"【{category}】{data['description']}（{data['count']}）")
        for file_info in data.get("files", []):
            lines.append(f"  - {file_info['file']}")
            lines.append(f"    action: {file_info['action']} | risk: {file_info['risk_level']} | tracked: {file_info['tracked']}")
            lines.append(f"    reason: {file_info['recommendation']}")
            if file_info.get("note"):
                lines.append(f"    note: {file_info['note']}")

    lines.append("")
    lines.append("=" * 80)
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="安全版 PornActressDB repo 審計腳本")
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--json-only", action="store_true")
    return parser.parse_args()


def write_outputs(findings: dict, report: str, project_root: Path, output_dir: Path | None) -> tuple[Path, Path]:
    target_dir = project_root if output_dir is None else output_dir.resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    json_path = target_dir / DEFAULT_OUTPUT_FILENAMES[0]
    text_path = target_dir / DEFAULT_OUTPUT_FILENAMES[1]

    json_path.write_text(json.dumps(findings, indent=2, ensure_ascii=False), encoding="utf-8")
    text_path.write_text(report, encoding="utf-8")
    return json_path, text_path


def main() -> None:
    args = parse_args()
    project_root = args.project_root.resolve()
    findings = scan_project(project_root)
    report = generate_report(findings)
    json_path, text_path = write_outputs(findings, report, project_root, args.output_dir)

    if args.json_only:
        print(json.dumps(findings, indent=2, ensure_ascii=False))
        return

    print(report)
    print("\n📊 詳細報告已儲存:")
    print(f"   JSON: {json_path}")
    print(f"   TEXT: {text_path}")


if __name__ == "__main__":
    main()
