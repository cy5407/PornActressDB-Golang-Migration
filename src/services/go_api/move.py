"""Go CLI 搬移與歷史 API。"""

import json
import tempfile
from dataclasses import dataclass
from typing import Optional

try:
    from ..go_runner import GoBridgeError, GoCommandRunner, _cleanup_temp_file
except ImportError:
    from services.go_runner import GoBridgeError, GoCommandRunner, _cleanup_temp_file


@dataclass
class MoveResult:
    """移動結果。"""

    source: str
    destination: str
    success: bool
    error: Optional[str] = None
    skipped: bool = False
    renamed: Optional[str] = None


@dataclass
class BatchMoveResult:
    """批次移動結果。"""

    operation_id: Optional[str]
    total_items: int
    success_count: int
    failed_count: int
    skipped_count: int
    results: list[MoveResult]
    status: str
    summary: str
    duration: str


@dataclass
class OperationLog:
    """操作日誌。"""

    id: str
    timestamp: str
    type: str
    status: str
    items: list[dict]
    total_items: int = 0
    success_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0


def _get_bridge():
    try:
        from ..go_bridge import get_bridge
    except ImportError:
        from services.go_bridge import get_bridge

    return get_bridge()


def _get_runner(runner: GoCommandRunner | None) -> GoCommandRunner:
    """取得 GoCommandRunner 實例，若未提供則使用全域橋接層的 runner。"""
    if runner is not None:
        return runner
    return _get_bridge()._runner


def _get_tempfile_module():
    try:
        from .. import go_bridge
    except ImportError:
        import services.go_bridge as go_bridge

    return getattr(go_bridge, "tempfile", tempfile)


def _get_context(
    *,
    runner: GoCommandRunner | None,
    log_dir: str | None,
    default_strategy: str | None,
) -> tuple[GoCommandRunner, str, str]:
    if runner is not None and log_dir is not None and default_strategy is not None:
        return runner, log_dir, default_strategy

    bridge = _get_bridge()
    return (
        _get_runner(runner),
        log_dir or bridge.log_dir,
        default_strategy or bridge.default_strategy,
    )


def _normalize_operation_type(operation_type: str) -> str:
    """正規化操作類型，保留舊日誌相容性。"""
    if operation_type == "move_batch":
        return "batch_move"
    return operation_type


def _build_batch_move_result(
    data: dict,
    default_total_items: int = 0,
) -> BatchMoveResult:
    results = [
        MoveResult(
            source=item.get("source", ""),
            destination=item.get("destination", ""),
            success=item.get("success", False),
            error=item.get("error"),
            skipped=item.get("skipped", False),
            renamed=item.get("renamed"),
        )
        for item in data.get("results", [])
    ]
    return BatchMoveResult(
        operation_id=data.get("operation_id"),
        total_items=data.get("total_items", default_total_items),
        success_count=data.get("success_count", 0),
        failed_count=data.get("failed_count", 0),
        skipped_count=data.get("skipped_count", 0),
        results=results,
        status=data.get("status", ""),
        summary=data.get("summary", ""),
        duration=data.get("duration", ""),
    )


def _build_operation_log(
    data: dict,
    default_operation_id: str = "",
) -> OperationLog:
    return OperationLog(
        id=data.get("id", default_operation_id),
        timestamp=data.get("timestamp", ""),
        type=_normalize_operation_type(data.get("type", "")),
        status=data.get("status", ""),
        items=data.get("items", []),
        total_items=data.get("total_items", len(data.get("items", []))),
        success_count=data.get("success_count", 0),
        failed_count=data.get("failed_count", 0),
        skipped_count=data.get("skipped_count", 0),
    )


def move_file(
    source: str,
    destination: str,
    strategy: Optional[str] = None,
    dry_run: bool = False,
    *,
    runner: GoCommandRunner | None = None,
    log_dir: str | None = None,
    default_strategy: str | None = None,
) -> MoveResult:
    """移動單一檔案。"""
    runner, log_dir, default_strategy = _get_context(
        runner=runner,
        log_dir=log_dir,
        default_strategy=default_strategy,
    )
    effective_strategy = strategy or default_strategy
    args = [
        "move",
        "-src",
        source,
        "-dst",
        destination,
        "-strategy",
        effective_strategy,
        "-log-dir",
        log_dir,
    ]
    if dry_run:
        args.append("-dry-run")

    data = runner.run_json(args, check=False)
    return MoveResult(
        source=data.get("source", source),
        destination=data.get("destination", destination),
        success=data.get("success", False),
        error=data.get("error"),
        skipped=data.get("skipped", False),
        renamed=data.get("renamed"),
    )


def move_dir(
    source: str,
    destination: str,
    strategy: Optional[str] = None,
    dry_run: bool = False,
    *,
    runner: GoCommandRunner | None = None,
    log_dir: str | None = None,
    default_strategy: str | None = None,
) -> dict:
    """移動整個目錄。"""
    runner, log_dir, default_strategy = _get_context(
        runner=runner,
        log_dir=log_dir,
        default_strategy=default_strategy,
    )
    effective_strategy = strategy or default_strategy
    args = [
        "move",
        "-kind",
        "dir",
        "-src",
        source,
        "-dst",
        destination,
        "-strategy",
        effective_strategy,
        "-log-dir",
        log_dir,
    ]
    if dry_run:
        args.append("-dry-run")

    data = runner.run_json(args, check=False)
    errors = data.get("errors", [])
    return {
        "source": data.get("source_dir", source),
        "destination": data.get("dest_dir", destination),
        "success": data.get("success", False),
        "files_moved": data.get("files_moved", 0),
        "files_total": data.get("files_total", 0),
        "deleted_source": data.get("deleted_src", False),
        "errors": errors,
        "error": "; ".join(
            err.get("error", "") for err in errors if isinstance(err, dict) and err.get("error")
        )
        or None,
        "skipped": False,
    }


def batch_move(
    items: list[dict],
    strategy: Optional[str] = None,
    dry_run: bool = False,
    *,
    runner: GoCommandRunner | None = None,
    log_dir: str | None = None,
    default_strategy: str | None = None,
) -> BatchMoveResult:
    """批次移動檔案。"""
    runner, log_dir, default_strategy = _get_context(
        runner=runner,
        log_dir=log_dir,
        default_strategy=default_strategy,
    )
    effective_strategy = strategy or default_strategy

    tempfile_module = _get_tempfile_module()
    with tempfile_module.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        delete=False,
        encoding="utf-8",
    ) as handle:
        payload = [
            item if "on_conflict" in item else {**item, "on_conflict": effective_strategy}
            for item in items
        ]
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        batch_file = handle.name

    try:
        args = ["move", "-batch", batch_file, "-log-dir", log_dir]
        if dry_run:
            args.append("-dry-run")

        result = runner.run(args, check=False, timeout=300)
        if result.returncode != 0:
            raise GoBridgeError(
                result.stderr.strip() or f"命令失敗，返回碼: {result.returncode}"
            )
        data = runner.parse_json(result.stdout)
        return _build_batch_move_result(data, default_total_items=len(items))
    finally:
        _cleanup_temp_file(batch_file, "batch_move")


def list_operations(
    limit: Optional[int] = None,
    *,
    runner: GoCommandRunner | None = None,
    log_dir: str | None = None,
) -> list[OperationLog]:
    """列出操作歷史。"""
    runner, log_dir, _ = _get_context(
        runner=runner,
        log_dir=log_dir,
        default_strategy="skip",
    )
    try:
        data = runner.run_json(["history", "list", "-log-dir", log_dir, "-json"], check=False)
    except GoBridgeError:
        return []

    logs = [_build_operation_log(item) for item in data]
    return logs[:limit] if limit is not None else logs


def get_operation(
    operation_id: str,
    *,
    runner: GoCommandRunner | None = None,
    log_dir: str | None = None,
) -> Optional[OperationLog]:
    """取得指定操作的詳細資訊。"""
    runner, log_dir, _ = _get_context(
        runner=runner,
        log_dir=log_dir,
        default_strategy="skip",
    )
    try:
        data = runner.run_json(["history", "show", "-log-dir", log_dir, "-json", operation_id])
    except GoBridgeError:
        return None
    return _build_operation_log(data, default_operation_id=operation_id)


def rollback(
    operation_id: str,
    *,
    runner: GoCommandRunner | None = None,
    log_dir: str | None = None,
) -> BatchMoveResult:
    """回滾指定操作。"""
    runner, log_dir, _ = _get_context(
        runner=runner,
        log_dir=log_dir,
        default_strategy="skip",
    )
    result = runner.run(
        ["history", "rollback", "-log-dir", log_dir, "-json", operation_id],
        check=False,
    )
    if result.returncode != 0:
        raise GoBridgeError(result.stderr.strip() or f"命令失敗，返回碼: {result.returncode}")
    return _build_batch_move_result(runner.parse_json(result.stdout))


def rollback_last(
    *,
    runner: GoCommandRunner | None = None,
    log_dir: str | None = None,
) -> BatchMoveResult:
    """回滾最近一次操作。"""
    return rollback("--last", runner=runner, log_dir=log_dir)
