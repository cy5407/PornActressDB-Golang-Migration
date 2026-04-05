"""Go CLI 掃描 API。"""

from dataclasses import dataclass
from typing import Optional

try:
    from ..go_runner import GoCommandRunner
except ImportError:
    from services.go_runner import GoCommandRunner


@dataclass
class ScanResult:
    """掃描結果。"""

    path: str
    code: str


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


def _get_context(
    *,
    runner: GoCommandRunner | None,
    default_workers: int | None,
) -> tuple[GoCommandRunner, int]:
    """取得 runner 與預設 worker 數，若未提供則從全域橋接層取得。"""
    if runner is not None and default_workers is not None:
        return runner, default_workers
    bridge = _get_bridge()
    return (
        _get_runner(runner),
        default_workers if default_workers is not None else bridge.default_workers,
    )


def scan_directory(
    directory: str,
    workers: Optional[int] = None,
    recursive: bool = True,
    *,
    runner: GoCommandRunner | None = None,
    default_workers: int | None = None,
) -> list[ScanResult]:
    """掃描目錄中的影片檔案，提取番號。"""
    r, dw = _get_context(runner=runner, default_workers=default_workers)
    effective_workers = workers or dw or 10
    args = ["scan", "-dir", directory, "-workers", str(effective_workers)]
    if not recursive:
        args.append("-recursive=false")

    data = r.run_json(args)
    return [ScanResult(path=item["path"], code=item["code"]) for item in data]


def extract_code(
    filename: str,
    *,
    runner: GoCommandRunner | None = None,
) -> str | None:
    """從單一檔案名稱提取番號（委託 Go CLI）。"""
    r = _get_runner(runner)
    data = r.run_json(["scan", "-extract", filename])
    if not isinstance(data, dict):
        return None
    code = data.get("code", "")
    return code if code else None
