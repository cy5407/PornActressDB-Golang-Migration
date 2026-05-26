"""Project audit helper.

掃描 untracked 檔案並依風險分類；本模組只做分類回報，不做任何刪檔動作。
"""

from __future__ import annotations

import subprocess
from pathlib import PurePosixPath
from typing import Any

# 視為 live source 的副檔名（出現在 src/ cmd/ pkg/ internal/ wails-app/ 之下會被視為高風險）
SOURCE_EXTENSIONS = {
    ".py", ".pyi", ".go", ".rs", ".ts", ".tsx", ".js", ".jsx",
    ".c", ".cc", ".cpp", ".h", ".hpp", ".java", ".kt", ".rb",
}
SOURCE_DIR_PARTS = {"src", "cmd", "pkg", "internal", "wails-app", "tools-rs", "scripts"}

DOC_EXTENSIONS = {".md", ".rst", ".txt", ".adoc"}
CORE_DOC_DIR_PARTS = {"docs", "wiki"}

BUILD_DIR_PARTS = {"build", "dist", "bin", "obj", "out", "target", "node_modules", "__pycache__"}
BUILD_EXTENSIONS = {".exe", ".dll", ".so", ".dylib", ".o", ".a", ".class", ".pyc"}

GENERATED_REPORT_NAMES = {".audit_report.json", "audit_report.json"}
GENERATED_REPORT_SUFFIXES = (".audit_report.json",)


def _list_untracked(root) -> list[str]:
    """Return untracked, non-ignored file paths (forward-slash) under root."""
    result = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=str(root),
        check=True,
        capture_output=True,
    )
    raw = result.stdout.decode("utf-8", errors="replace")
    return [item for item in raw.split("\0") if item]


def _path(rel_path: str) -> PurePosixPath:
    return PurePosixPath(rel_path)


def _is_source_like(rel_path: str) -> bool:
    p = _path(rel_path)
    if p.suffix.lower() not in SOURCE_EXTENSIONS:
        return False
    return any(part in SOURCE_DIR_PARTS for part in p.parts)


def _is_doc(rel_path: str) -> bool:
    return _path(rel_path).suffix.lower() in DOC_EXTENSIONS


def _is_core_doc_location(rel_path: str) -> bool:
    p = _path(rel_path)
    if len(p.parts) == 1:
        return True  # 根目錄頂層的 .md，例如 MIGRATION_STATUS.md
    return any(part in CORE_DOC_DIR_PARTS for part in p.parts)


def _is_build_artifact(rel_path: str) -> bool:
    p = _path(rel_path)
    if any(part in BUILD_DIR_PARTS for part in p.parts):
        return True
    return p.suffix.lower() in BUILD_EXTENSIONS


def _is_generated_report(rel_path: str) -> bool:
    p = _path(rel_path)
    if p.name in GENERATED_REPORT_NAMES:
        return True
    return any(rel_path.endswith(suffix) for suffix in GENERATED_REPORT_SUFFIXES)


def _classify(rel_path: str) -> tuple[str, dict[str, Any]]:
    p = _path(rel_path)

    # 1. 備份檔（.bak）— 若 strip 掉 .bak 後仍像 live source，視為高風險手動 review
    if p.suffix == ".bak":
        body = rel_path[: -len(".bak")]
        if _is_source_like(body):
            return "backup_artifacts", {
                "file": rel_path,
                "action": "manual_review",
                "risk_level": "high",
                "recommendation": "看似 live source 的 .bak 備份，需人工確認沒有未提交的修改後再決定處置",
            }
        return "backup_artifacts", {
            "file": rel_path,
            "action": "delete_candidate",
            "risk_level": "low",
            "recommendation": "一般備份檔，可考慮刪除",
        }

    # 2. 自動產生的 audit / report — 可安全刪除
    if _is_generated_report(rel_path):
        return "generated_reports", {
            "file": rel_path,
            "action": "delete_candidate",
            "risk_level": "low",
            "recommendation": "audit 自動產生的報告檔，可刪除或加入 .gitignore",
        }

    # 3. 建置產出物 — 預設略過（建議加入 .gitignore，不入版控）
    if _is_build_artifact(rel_path):
        return "build_artifacts", {
            "file": rel_path,
            "action": "ignore_candidate",
            "risk_level": "low",
            "recommendation": "建置產出物，建議加入 .gitignore，不需入版控",
        }

    # 4. 看似 live source code 的 untracked 檔案 — 高風險，禁止盲目刪除
    if _is_source_like(rel_path):
        return "untracked_files", {
            "file": rel_path,
            "action": "manual_review",
            "risk_level": "high",
            "recommendation": "看似 live source code，不可直接刪除；請確認是否漏 add 或為私人 WIP",
        }

    # 5. 文件草稿（.md / .rst 等）— 中等風險，建議納入版控
    if _is_doc(rel_path) and _is_core_doc_location(rel_path):
        return "untracked_files", {
            "file": rel_path,
            "action": "manual_review",
            "risk_level": "medium",
            "recommendation": "未追蹤的文件草稿，建議納入版控或歸檔",
        }

    # 6. 其他 — 預設保守處理
    return "untracked_files", {
        "file": rel_path,
        "action": "manual_review",
        "risk_level": "medium",
        "recommendation": "未分類的 untracked 檔案，需人工判斷",
    }


def scan_project(root) -> dict[str, Any]:
    """Scan ``root`` for untracked files and group them into risk categories.

    回傳的 dict 結構：
        {
            "categories": {
                "untracked_files":  {"files": [...]},
                "generated_reports": {"files": [...]},
                "backup_artifacts":  {"files": [...]},
                "build_artifacts":   {"files": [...]},
            }
        }

    每一個 entry 含 ``file`` / ``action`` / ``risk_level`` / ``recommendation``。
    本函式不做任何刪檔動作，只做分類回報。
    """
    categories: dict[str, dict[str, list[dict[str, Any]]]] = {
        "untracked_files": {"files": []},
        "generated_reports": {"files": []},
        "backup_artifacts": {"files": []},
        "build_artifacts": {"files": []},
    }
    for rel_path in _list_untracked(root):
        category, entry = _classify(rel_path)
        categories[category]["files"].append(entry)
    return {"categories": categories}
