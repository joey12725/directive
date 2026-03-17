from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db.models import Avg, Count, Min

from plane.db.models import ComputePool, RateLimitEvent, PoolUsageRecord


class PoolRateModel:
    """Estimate safe throughput from configured limits plus observed 429 events."""

    def __init__(self, pool: ComputePool) -> None:
        self.pool = pool

    def get_effective_throughput(self) -> dict[str, Any]:
        aggregates = RateLimitEvent.objects.filter(
            pool=self.pool, deleted_at__isnull=True
        ).aggregate(
            event_count=Count("id"),
            min_request_count=Min("request_count"),
            min_token_count=Min("token_count"),
            avg_retry_after_seconds=Avg("retry_after_seconds"),
        )

        configured_requests = self._extract_limit(kind="request")
        configured_tokens = self._extract_limit(kind="token")

        learned_requests = aggregates["min_request_count"] or configured_requests
        learned_tokens = aggregates["min_token_count"] or configured_tokens

        return {
            "configured": {
                "requests": configured_requests,
                "tokens": configured_tokens,
            },
            "learned": {
                "requests": learned_requests,
                "tokens": learned_tokens,
            },
            "safe": {
                "requests": self._apply_safety_margin(learned_requests),
                "tokens": self._apply_safety_margin(learned_tokens),
            },
            "event_count": aggregates["event_count"] or 0,
            "avg_retry_after_seconds": float(aggregates["avg_retry_after_seconds"] or 0),
        }

    def _extract_limit(self, *, kind: str) -> int | None:
        candidates = self._flatten_numeric_limits(self.pool.rate_limits or {})
        matching_values = [value for key, value in candidates if kind in key.lower()]
        if not matching_values:
            return None
        return min(matching_values)

    def _flatten_numeric_limits(self, data: Any, prefix: str = "") -> list[tuple[str, int]]:
        flattened: list[tuple[str, int]] = []

        if isinstance(data, dict):
            for key, value in data.items():
                child_prefix = f"{prefix}.{key}" if prefix else str(key)
                flattened.extend(self._flatten_numeric_limits(value, prefix=child_prefix))
            return flattened

        if isinstance(data, list):
            for index, value in enumerate(data):
                flattened.extend(self._flatten_numeric_limits(value, prefix=f"{prefix}[{index}]"))
            return flattened

        if isinstance(data, (int, float, Decimal)):
            flattened.append((prefix, int(data)))

        return flattened

    def get_average_task_cost(self) -> dict[str, Any]:
        """
        Calculate average cost, tokens, and duration per session for this pool.

        Returns:
            Dictionary containing:
                - avg_cost: Average cost per session in USD (Decimal or None)
                - avg_tokens: Average total tokens per session (int or None)
                - avg_duration: Average duration per session in seconds (float or None)
        """
        aggregates = PoolUsageRecord.objects.filter(
            pool=self.pool, deleted_at__isnull=True
        ).aggregate(
            avg_cost=Avg("estimated_cost_usd"),
            avg_tokens=Avg("total_tokens"),
            avg_duration=Avg("duration_seconds"),
        )

        return {
            "avg_cost": aggregates["avg_cost"],
            "avg_tokens": int(aggregates["avg_tokens"]) if aggregates["avg_tokens"] is not None else None,
            "avg_duration": float(aggregates["avg_duration"]) if aggregates["avg_duration"] is not None else None,
        }

    @staticmethod
    def _apply_safety_margin(value: int | None) -> int | None:
        if value is None:
            return None
        return max(int(value * 0.9), 1)
