"""
重試與退避工具模組

提供指數退避與自適應併發控制器，用於改善批次搜尋的穩定性與速度。
"""

import logging
import random

logger = logging.getLogger(__name__)


class ExponentialBackoff:
    """指數退避計算器

    用於暫時性錯誤的延遲計算，遵循指數退避策略以避免頻繁重試。

    Args:
        base_delay: 基礎延遲時間（秒），預設 0.5
        max_delay: 最大延遲上限（秒），預設 30.0
        multiplier: 每次失敗的乘數，預設 2.0（2 倍遞增）
        jitter: 是否加入隨機抖動（±20%），預設 True

    Example:
        >>> backoff = ExponentialBackoff()
        >>> backoff.next_delay()  # 0.5s
        >>> backoff.next_delay()  # 1.0s
        >>> backoff.next_delay()  # 2.0s
        >>> backoff.reset()
        >>> backoff.next_delay()  # 回到 0.5s
    """

    def __init__(
        self,
        base_delay: float = 0.5,
        max_delay: float = 30.0,
        multiplier: float = 2.0,
        jitter: bool = True,
    ):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.multiplier = multiplier
        self.jitter = jitter
        self.attempt = 0

    def next_delay(self) -> float:
        """計算下一次應等待的延遲時間，並遞增內部計數"""
        # 計算延遲：base_delay × (multiplier ^ attempt)，上限 max_delay
        delay = min(
            self.base_delay * (self.multiplier ** self.attempt),
            self.max_delay
        )

        # 加入隨機抖動，避免雷同時機（±20%）
        if self.jitter:
            jitter_factor = random.uniform(0.8, 1.2)
            delay *= jitter_factor

        # 遞增計數器
        self.attempt += 1

        return delay

    def reset(self):
        """重置計數器（成功後呼叫）"""
        self.attempt = 0

    def current_attempt(self) -> int:
        """取得目前已重試次數"""
        return self.attempt


class AdaptiveConcurrencyController:
    """自適應併發控制器

    根據成功/失敗率動態調整併發數，達到最佳吞吐量同時避免過載。

    Args:
        initial: 初始併發數，預設 15
        minimum: 最低併發數，預設 2
        maximum: 最高併發數，預設 30
        decrease_threshold: 連續失敗達此數值則降載，預設 3
        increase_threshold: 連續成功達此數值則升載，預設 10
        decrease_factor: 降載時的乘數，預設 0.5（減半）
        increase_step: 升載時的增量，預設 2

    Example:
        >>> controller = AdaptiveConcurrencyController(initial=15)
        >>> controller.get_concurrency()  # 15

        # 連續失敗 3 次
        >>> controller.report_failure()
        >>> controller.report_failure()
        >>> controller.report_failure()
        >>> controller.get_concurrency()  # 8（降載）

        # 連續成功 10 次
        >>> for _ in range(10):
        ...     controller.report_success()
        >>> controller.get_concurrency()  # 10（升載）
    """

    def __init__(
        self,
        initial: int = 15,
        minimum: int = 2,
        maximum: int = 30,
        decrease_threshold: int = 3,
        increase_threshold: int = 10,
        decrease_factor: float = 0.5,
        increase_step: int = 2,
    ):
        self.concurrency = initial
        self.minimum = minimum
        self.maximum = maximum
        self.decrease_threshold = decrease_threshold
        self.increase_threshold = increase_threshold
        self.decrease_factor = decrease_factor
        self.increase_step = increase_step

        # 計數器
        self.consecutive_successes = 0
        self.consecutive_failures = 0

    def report_success(self):
        """回報成功，累計成功計數"""
        self.consecutive_successes += 1
        self.consecutive_failures = 0  # 重置失敗計數

        # 檢查是否需要升載
        if self.consecutive_successes >= self.increase_threshold:
            old_concurrency = self.concurrency
            self.concurrency = min(
                self.maximum,
                self.concurrency + self.increase_step
            )
            if self.concurrency > old_concurrency:
                logger.debug(
                    f"📈 併發升載: {old_concurrency} → {self.concurrency} "
                    f"(連續成功 {self.consecutive_successes})"
                )
            self.consecutive_successes = 0  # 升載後重置

    def report_failure(self):
        """回報失敗，累計失敗計數"""
        self.consecutive_failures += 1
        self.consecutive_successes = 0  # 重置成功計數

        # 檢查是否需要降載
        if self.consecutive_failures >= self.decrease_threshold:
            old_concurrency = self.concurrency
            self.concurrency = max(
                self.minimum,
                int(self.concurrency * self.decrease_factor)
            )
            if self.concurrency < old_concurrency:
                logger.debug(
                    f"📉 併發降載: {old_concurrency} → {self.concurrency} "
                    f"(連續失敗 {self.consecutive_failures})"
                )
            self.consecutive_failures = 0  # 降載後重置

    def get_concurrency(self) -> int:
        """取得目前建議的併發數"""
        return self.concurrency

    def reset(self):
        """重置所有計數器和併發數到初始狀態"""
        self.consecutive_successes = 0
        self.consecutive_failures = 0
        # 注意：不重置 concurrency，保留目前的併發狀態

    def get_stats(self) -> dict:
        """取得統計資訊"""
        return {
            "current_concurrency": self.concurrency,
            "consecutive_successes": self.consecutive_successes,
            "consecutive_failures": self.consecutive_failures,
            "minimum": self.minimum,
            "maximum": self.maximum,
        }
