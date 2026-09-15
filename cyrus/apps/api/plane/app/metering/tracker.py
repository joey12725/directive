from __future__ import annotations

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from django.db.models import Count, Q, Sum

from plane.db.models import ComputePool, CyrusSession, PoolType, PoolUsageRecord

logger = logging.getLogger(__name__)


class ComputeTracker:
    """
    Mirror session usage into pool metering records.

    API-billing pools compute an exact token price from the pool's input/output token rates.
    Subscription pools currently estimate cost as 0 because the spend is sunk, but they still
    retain token volume so we can plan capacity and compare relative usage across agents.

    Enhanced with:
    - Structured logging
    - Division by zero protection
    """

    COST_PRECISION = Decimal("0.000001")

    def __init__(self, pool: ComputePool | None = None) -> None:
        self.pool = pool

    def calculate_session_cost(self, session: CyrusSession) -> Decimal:
        """Calculate session cost based on pool type and token usage."""
        if session.pool.pool_type == PoolType.API_BILLING:
            input_rate = session.pool.cost_per_input_token_usd or Decimal("0")
            output_rate = session.pool.cost_per_output_token_usd or Decimal("0")
            input_tokens = session.input_tokens or 0
            output_tokens = session.output_tokens or 0

            cost = self._quantize(
                (Decimal(input_tokens) * input_rate) + (Decimal(output_tokens) * output_rate)
            )

            logger.debug(
                f"Calculated API billing cost for session {session.id}",
                extra={
                    "session_id": str(session.id),
                    "pool_id": str(session.pool.id),
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost_usd": float(cost)
                }
            )

            return cost

        return self.estimate_subscription_cost(session)

    def estimate_subscription_cost(self, session: CyrusSession) -> Decimal:
        return self._quantize(Decimal("0"))

    def record_session(self, session: CyrusSession) -> PoolUsageRecord:
        """Record session usage in pool metering records."""
        cost = self.calculate_session_cost(session)
        session_identifier = session.acpx_session_id or str(session.id)

        logger.debug(
            f"Recording session usage for session {session.id}",
            extra={
                "session_id": str(session.id),
                "pool_id": str(session.pool.id),
                "total_tokens": session.total_tokens,
                "cost_usd": float(cost),
                "was_rate_limited": session.was_rate_limited
            }
        )

        record = PoolUsageRecord.objects.update_or_create(
            pool=session.pool,
            session_id=session_identifier,
            defaults={
                "agent": session.agent,
                "goal": session.goal,
                "project": session.project,
                "work_item": session.work_item,
                "input_tokens": session.input_tokens,
                "output_tokens": session.output_tokens,
                "total_tokens": session.total_tokens,
                "estimated_cost_usd": cost,
                "duration_seconds": session.duration_seconds,
                "model_name": session.model_name,
                "was_rate_limited": session.was_rate_limited,
                "rate_limit_wait_seconds": session.rate_limit_wait_seconds,
            },
        )[0]

        logger.info(
            f"Session usage recorded for session {session.id}",
            extra={
                "session_id": str(session.id),
                "pool_id": str(session.pool.id),
                "usage_record_id": str(record.id)
            }
        )

        return record

    def get_pool_budget_state(self) -> dict[str, Any]:
        """Get comprehensive budget state for a pool."""
        pool = self.pool
        if pool is None:
            raise ValueError("ComputeTracker requires a pool for budget aggregation.")

        logger.debug(
            f"Getting budget state for pool {pool.name}",
            extra={"pool_id": str(pool.id), "pool_name": pool.name}
        )

        aggregates = pool.usage_records.aggregate(
            total_cost=Sum("estimated_cost_usd"),
            total_tokens=Sum("total_tokens"),
            total_input_tokens=Sum("input_tokens"),
            total_output_tokens=Sum("output_tokens"),
            session_count=Count("id"),
            rate_limit_hits=Count("id", filter=Q(was_rate_limited=True)),
        )

        total_cost = aggregates["total_cost"] or Decimal("0")
        configured_rate_limits = pool.rate_limits or {}
        safe_rate_limits = (
            self._apply_uncertainty(configured_rate_limits, pool.uncertainty_pct)
            if pool.pool_type == PoolType.SUBSCRIPTION
            else configured_rate_limits
        )

        budget_remaining = None
        if pool.budget_limit_usd is not None:
            budget_remaining = max(pool.budget_limit_usd - total_cost, Decimal("0"))

        state = {
            "pool_id": pool.id,
            "pool_type": pool.pool_type,
            "budget_limit_usd": pool.budget_limit_usd,
            "budget_remaining_usd": budget_remaining,
            "total_cost_usd": self._quantize(total_cost),
            "total_tokens": aggregates["total_tokens"] or 0,
            "total_input_tokens": aggregates["total_input_tokens"] or 0,
            "total_output_tokens": aggregates["total_output_tokens"] or 0,
            "session_count": aggregates["session_count"] or 0,
            "rate_limit_hits": aggregates["rate_limit_hits"] or 0,
            "configured_rate_limits": configured_rate_limits,
            "safe_rate_limits": safe_rate_limits,
            "uncertainty_pct": pool.uncertainty_pct,
        }

        logger.info(
            f"Budget state retrieved for pool {pool.name}",
            extra={
                "pool_id": str(pool.id),
                "total_cost_usd": float(total_cost),
                "budget_remaining_usd": float(budget_remaining) if budget_remaining else None,
                "session_count": state["session_count"],
                "rate_limit_hits": state["rate_limit_hits"]
            }
        )

        return state

    def _apply_uncertainty(self, value: Any, uncertainty_pct: int) -> Any:
        """Apply uncertainty percentage to rate limits for subscription pools."""
        try:
            # Division by zero protection (100 should never be 0, but being defensive)
            if uncertainty_pct >= 100:
                logger.warning(
                    f"Uncertainty percentage >= 100: {uncertainty_pct}, clamping to 99",
                    extra={"uncertainty_pct": uncertainty_pct}
                )
                uncertainty_pct = 99

            safety_factor = Decimal(100 - uncertainty_pct) / Decimal(100)
        except (ZeroDivisionError, ValueError) as exc:
            logger.error(f"Error calculating safety factor: {exc}", extra={"uncertainty_pct": uncertainty_pct})
            safety_factor = Decimal("1")  # Default to no adjustment

        if isinstance(value, dict):
            return {key: self._apply_uncertainty(child, uncertainty_pct) for key, child in value.items()}

        if isinstance(value, list):
            return [self._apply_uncertainty(child, uncertainty_pct) for child in value]

        if isinstance(value, bool):
            return value

        if isinstance(value, (int, float, Decimal)):
            try:
                adjusted = Decimal(str(value)) * safety_factor
                if isinstance(value, int):
                    return int(adjusted)
                return float(adjusted)
            except (ValueError, TypeError) as exc:
                logger.error(f"Error adjusting value: {exc}", extra={"value": value, "safety_factor": safety_factor})
                return value

        return value

    def _quantize(self, value: Decimal) -> Decimal:
        return value.quantize(self.COST_PRECISION, rounding=ROUND_HALF_UP)
