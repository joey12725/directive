from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Q
from django.utils import timezone

from plane.db.models import ComputePool, PoolType, RateLimitEvent

from .rate_model import PoolRateModel
from .tracker import ComputeTracker


class BudgetService:
    """
    Intelligence layer for budget and capacity management.

    Provides real-time budget intelligence to the scheduling engine,
    determining whether a compute pool has the financial and rate-limit
    capacity to accept new dispatches.
    """

    def get_all_pool_states(self, workspace_id: str) -> list[dict[str, Any]]:
        """
        Query all ComputePool objects for the given workspace and return their budget states.

        Args:
            workspace_id: The workspace ID to query pools for

        Returns:
            List of dictionaries containing budget state for each pool
        """
        pools = ComputePool.objects.filter(workspace_id=workspace_id, deleted_at__isnull=True)

        states = []
        for pool in pools:
            tracker = ComputeTracker(pool=pool)
            state = tracker.get_pool_budget_state()
            states.append(state)

        return states

    def can_dispatch(self, pool: ComputePool, estimated_tokens: int | None = None) -> dict[str, Any]:
        """
        Pre-dispatch check to verify if this pool can accept work right now.

        Performs financial, rate limit, and throughput checks to determine
        if the pool has capacity for a new dispatch.

        Args:
            pool: The ComputePool to check
            estimated_tokens: Optional estimated token count for the dispatch

        Returns:
            Dictionary with:
                - can_dispatch: Boolean indicating if dispatch is allowed
                - reasons: List of reason codes explaining the decision
                - budget_state: Current budget state from ComputeTracker
                - throughput: Throughput data from PoolRateModel
        """
        tracker = ComputeTracker(pool=pool)
        state = tracker.get_pool_budget_state()

        can_go = True
        reasons = []

        # Financial Check (Both Pool Types)
        if state["budget_remaining_usd"] is not None:
            if state["budget_remaining_usd"] <= 0:
                can_go = False
                reasons.append("budget_exhausted")
            else:
                # Calculate utilization percentage
                budget_limit = state["budget_limit_usd"]
                if budget_limit and budget_limit > 0:
                    utilization_pct = float(
                        (state["total_cost_usd"] / budget_limit) * Decimal("100")
                    )
                    if utilization_pct > 90:
                        reasons.append("budget_warning_90pct")

        # Rate Limit Check (Subscription Pools Only)
        if pool.pool_type == PoolType.SUBSCRIPTION:
            five_minutes_ago = timezone.now() - timedelta(minutes=5)
            recent_rate_limit_count = RateLimitEvent.objects.filter(
                pool=pool,
                timestamp__gte=five_minutes_ago,
                deleted_at__isnull=True
            ).count()

            if recent_rate_limit_count > 3:
                can_go = False
                reasons.append("rate_limited_recently")

        # Throughput Check (Optional but recommended)
        rate_model = PoolRateModel(pool)
        throughput = rate_model.get_effective_throughput()

        if estimated_tokens is not None:
            safe_tokens = throughput.get("safe", {}).get("tokens")
            if safe_tokens is not None and safe_tokens < estimated_tokens:
                reasons.append("throughput_insufficient")

        return {
            "can_dispatch": can_go,
            "reasons": reasons,
            "budget_state": state,
            "throughput": throughput,
        }

    def forecast_remaining_capacity(
        self, pool: ComputePool, hours_ahead: int = 24
    ) -> dict[str, Any]:
        """
        Estimate how many sessions/tokens this pool can handle in the near future.

        Based on historical averages and remaining budget, calculates the
        estimated capacity for upcoming work.

        Args:
            pool: The ComputePool to forecast
            hours_ahead: Number of hours to forecast (default: 24)

        Returns:
            Dictionary containing:
                - pool_id: Pool identifier
                - hours_ahead: Forecast window
                - budget_remaining_usd: Remaining budget
                - avg_cost_per_session: Average cost from historical data
                - estimated_remaining_sessions: Estimated number of sessions possible
                - avg_tokens_per_session: Average tokens from historical data
                - avg_duration_per_session: Average duration from historical data
        """
        rate_model = PoolRateModel(pool)
        avg_task = rate_model.get_average_task_cost()

        tracker = ComputeTracker(pool=pool)
        state = tracker.get_pool_budget_state()

        estimated_remaining_sessions = None
        budget_remaining = state["budget_remaining_usd"]
        avg_cost = avg_task.get("avg_cost")

        if budget_remaining is not None and avg_cost is not None and avg_cost > 0:
            estimated_remaining_sessions = int(budget_remaining / avg_cost)

        return {
            "pool_id": pool.id,
            "hours_ahead": hours_ahead,
            "budget_remaining_usd": budget_remaining,
            "avg_cost_per_session": avg_cost,
            "estimated_remaining_sessions": estimated_remaining_sessions,
            "avg_tokens_per_session": avg_task.get("avg_tokens"),
            "avg_duration_per_session": avg_task.get("avg_duration"),
        }
