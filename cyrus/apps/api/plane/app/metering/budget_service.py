from __future__ import annotations

import json
import logging
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

from plane.db.models import ComputePool, PoolType, RateLimitEvent

from .rate_model import PoolRateModel
from .tracker import ComputeTracker

logger = logging.getLogger(__name__)


class BudgetService:
    """
    Intelligence layer for budget and capacity management.

    Provides real-time budget intelligence to the scheduling engine,
    determining whether a compute pool has the financial and rate-limit
    capacity to accept new dispatches.

    Enhanced with:
    - Two-tier caching (memory + Django cache)
    - Structured logging
    - Division by zero protection
    - Optimized batch queries
    """

    CACHE_TTL_SECONDS = 300  # 5 minutes

    def __init__(self):
        self._memory_cache: dict[str, Any] = {}

    def _get_cache_key(self, key_type: str, identifier: str) -> str:
        """Generate cache key."""
        return f"budget_service:{key_type}:{identifier}"

    def _get_cached_pool_state(self, pool_id: str) -> dict[str, Any] | None:
        """Get cached pool state from memory or Django cache."""
        # Try memory cache first
        cache_key = self._get_cache_key("pool_state", pool_id)
        if cache_key in self._memory_cache:
            logger.debug(f"Pool state cache hit (memory) for pool {pool_id}")
            return self._memory_cache[cache_key]

        # Try Django cache
        try:
            cached = cache.get(cache_key)
            if cached is not None:
                # Store in memory cache too
                self._memory_cache[cache_key] = cached
                logger.debug(f"Pool state cache hit (django) for pool {pool_id}")
                return cached
        except Exception as exc:
            logger.warning(f"Cache read failed: {exc}")

        return None

    def _set_cached_pool_state(self, pool_id: str, state: dict[str, Any]) -> None:
        """Set pool state in both memory and Django cache."""
        cache_key = self._get_cache_key("pool_state", pool_id)

        # Store in memory cache
        self._memory_cache[cache_key] = state

        # Store in Django cache
        try:
            cache.set(cache_key, state, self.CACHE_TTL_SECONDS)
        except Exception as exc:
            logger.warning(f"Cache write failed: {exc}")

    def get_all_pool_states(self, workspace_id: str) -> list[dict[str, Any]]:
        """
        Query all ComputePool objects for the given workspace and return their budget states.

        Enhanced with:
        - Two-tier caching for pool states
        - Batch query optimization
        - Structured logging

        Args:
            workspace_id: The workspace ID to query pools for

        Returns:
            List of dictionaries containing budget state for each pool
        """
        logger.debug(f"Getting all pool states for workspace {workspace_id}")

        pools = ComputePool.objects.filter(
            workspace_id=workspace_id,
            deleted_at__isnull=True
        ).prefetch_related('usage_records', 'rate_limit_events')

        states = []
        cache_hits = 0
        cache_misses = 0

        for pool in pools:
            pool_id = str(pool.id)

            # Try cache first
            cached_state = self._get_cached_pool_state(pool_id)
            if cached_state is not None:
                states.append(cached_state)
                cache_hits += 1
                continue

            # Cache miss - compute state
            cache_misses += 1
            tracker = ComputeTracker(pool=pool)
            state = tracker.get_pool_budget_state()
            states.append(state)

            # Cache the result
            self._set_cached_pool_state(pool_id, state)

        logger.info(
            f"Pool states retrieved for workspace {workspace_id}",
            extra={
                "workspace_id": workspace_id,
                "pool_count": len(pools),
                "cache_hits": cache_hits,
                "cache_misses": cache_misses,
            }
        )

        return states

    def can_dispatch(self, pool: ComputePool, estimated_tokens: int | None = None) -> dict[str, Any]:
        """
        Pre-dispatch check to verify if this pool can accept work right now.

        Performs financial, rate limit, and throughput checks to determine
        if the pool has capacity for a new dispatch.

        Enhanced with:
        - Division by zero protection
        - Structured logging
        - Caching of pool state

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
        logger.debug(
            f"Checking dispatch eligibility for pool {pool.name}",
            extra={"pool_id": str(pool.id), "pool_name": pool.name, "estimated_tokens": estimated_tokens}
        )

        # Try to get cached state first
        pool_id = str(pool.id)
        state = self._get_cached_pool_state(pool_id)

        if state is None:
            tracker = ComputeTracker(pool=pool)
            state = tracker.get_pool_budget_state()
            self._set_cached_pool_state(pool_id, state)

        can_go = True
        reasons = []

        # Financial Check (Both Pool Types)
        if state["budget_remaining_usd"] is not None:
            if state["budget_remaining_usd"] <= 0:
                can_go = False
                reasons.append("budget_exhausted")
                logger.info(
                    f"Pool {pool.name} budget exhausted",
                    extra={"pool_id": pool_id, "budget_remaining": 0}
                )
            else:
                # Calculate utilization percentage with division by zero protection
                budget_limit = state["budget_limit_usd"]
                if budget_limit and budget_limit > 0:
                    try:
                        utilization_pct = float(
                            (state["total_cost_usd"] / budget_limit) * Decimal("100")
                        )
                        if utilization_pct > 90:
                            reasons.append("budget_warning_90pct")
                            logger.warning(
                                f"Pool {pool.name} budget at {utilization_pct:.1f}%",
                                extra={"pool_id": pool_id, "utilization_pct": utilization_pct}
                            )
                    except (ZeroDivisionError, TypeError, ValueError) as exc:
                        logger.error(
                            f"Error calculating budget utilization: {exc}",
                            extra={"pool_id": pool_id, "budget_limit": budget_limit}
                        )

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
                logger.warning(
                    f"Pool {pool.name} rate limited recently",
                    extra={"pool_id": pool_id, "rate_limit_count": recent_rate_limit_count}
                )

        # Throughput Check (Optional but recommended)
        rate_model = PoolRateModel(pool)
        throughput = rate_model.get_effective_throughput()

        if estimated_tokens is not None:
            safe_tokens = throughput.get("safe", {}).get("tokens")
            if safe_tokens is not None and safe_tokens < estimated_tokens:
                reasons.append("throughput_insufficient")
                logger.debug(
                    f"Pool {pool.name} throughput insufficient",
                    extra={"pool_id": pool_id, "safe_tokens": safe_tokens, "estimated_tokens": estimated_tokens}
                )

        logger.info(
            f"Dispatch eligibility check for pool {pool.name}",
            extra={
                "pool_id": pool_id,
                "can_dispatch": can_go,
                "reasons": reasons,
                "budget_remaining_usd": state["budget_remaining_usd"]
            }
        )

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

        Enhanced with:
        - Division by zero protection
        - Structured logging
        - Error handling for edge cases

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
        logger.debug(
            f"Forecasting capacity for pool {pool.name}",
            extra={"pool_id": str(pool.id), "pool_name": pool.name, "hours_ahead": hours_ahead}
        )

        rate_model = PoolRateModel(pool)
        avg_task = rate_model.get_average_task_cost()

        tracker = ComputeTracker(pool=pool)
        state = tracker.get_pool_budget_state()

        estimated_remaining_sessions = None
        budget_remaining = state["budget_remaining_usd"]
        avg_cost = avg_task.get("avg_cost")

        # Division by zero protection
        if budget_remaining is not None and avg_cost is not None and avg_cost > 0:
            try:
                estimated_remaining_sessions = int(budget_remaining / avg_cost)
                logger.info(
                    f"Pool {pool.name} forecast: ~{estimated_remaining_sessions} sessions remaining",
                    extra={
                        "pool_id": str(pool.id),
                        "budget_remaining_usd": float(budget_remaining),
                        "avg_cost_per_session": float(avg_cost),
                        "estimated_remaining_sessions": estimated_remaining_sessions
                    }
                )
            except (ZeroDivisionError, TypeError, ValueError) as exc:
                logger.error(
                    f"Error calculating forecast: {exc}",
                    extra={
                        "pool_id": str(pool.id),
                        "budget_remaining": budget_remaining,
                        "avg_cost": avg_cost
                    }
                )
        else:
            logger.debug(
                f"Cannot forecast for pool {pool.name}: insufficient data",
                extra={
                    "pool_id": str(pool.id),
                    "budget_remaining": budget_remaining,
                    "avg_cost": avg_cost
                }
            )

        return {
            "pool_id": pool.id,
            "hours_ahead": hours_ahead,
            "budget_remaining_usd": budget_remaining,
            "avg_cost_per_session": avg_cost,
            "estimated_remaining_sessions": estimated_remaining_sessions,
            "avg_tokens_per_session": avg_task.get("avg_tokens"),
            "avg_duration_per_session": avg_task.get("avg_duration"),
        }
