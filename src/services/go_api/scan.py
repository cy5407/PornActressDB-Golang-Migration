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


def scan_directory(
    directory: str,
    workers: Optional[int] = None,
    recursive: bool = True,
    *,
    runner: GoCommandRunner | None = None,
    default_workers: int | None = None,
) -> list[ScanResult]:
    """掃描目錄中的影片檔案，提取番號。"""
    if runner is None or default_workers is None:
        bridge = _get_bridge()
        runner = runner or bridge._runner
        default_workers = default_workers or bridge.default_workers

    effective_workers = workers or default_workers or 10
    args = ["scan", "-dir", directory, "-workers", str(effective_workers)]
    if not recursive:
        args.append("-recursive=false")

    data = runner.run_json(args)
    return [ScanResult(path=item["path"], code=item["code"]) for item in data]
