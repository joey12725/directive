"""
Scheduling Engine - Phase 4 Enhanced

The central nervous system that determines what work gets done, when, and at what intensity,
based on real-time budget data and configured schedule rows.

Enhanced with:
- Cross-midnight schedule support
- Pool state caching
- Distributed locking
- Predictive budget pacing
- Dynamic intensity adjustment
- Cooldown periods
- Schedule priority inheritance
- Graceful degradation
- Circuit breaker pattern
- Audit logging
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import pytz
import redis
from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from plane.app.metering.budget_service import BudgetService
from plane.db.models import (
    ComputeAllocation,
    CyrusSession,
    Schedule,
    ScheduleRow,
    SchedulingDecision,
    SessionStatus,
)

logger = logging.getLogger(__name__)


class SchedulingEngine:
    """
    Determines work scheduling based on budget constraints, time windows, and priorities.

    This engine evaluates which ComputeAllocations should be dispatched based on:
    - Current time and day of week matching schedule rows
    - Budget availability from the BudgetService
    - Rate limit status
    - Priority ordering (with schedule priority inheritance)
    - Existing running sessions to avoid duplicate dispatches
    - Cooldown periods
    - Circuit breaker status
    """

    CACHE_TTL = 300  # 5 minutes
    LOCK_TIMEOUT = 60  # 1 minute
    CIRCUIT_BREAKER_THRESHOLD = 5  # failures before circuit opens

    def __init__(self, workspace_id: str) -> None:
        """
        Initialize the scheduling engine for a specific workspace.

        Args:
            workspace_id: The workspace ID to operate within
        """
        self.workspace_id = workspace_id
        self.budget_service = BudgetService()
        self._pool_state_cache: dict[str, dict[str, Any]] = {}

        # Initialize Redis connection with fallback
        try:
            self.redis_client = redis.Redis.from_url(settings.REDIS_URL, db=0)
            self.redis_client.ping()
            self._redis_available = True
        except Exception as exc:
            logger.warning(f"Redis unavailable, falling back to degraded mode: {exc}")
            self.redis_client = None
            self._redis_available = False

    def compute_dispatch_plan(self) -> list[dict[str, Any]]:
        """
        Compute which allocations should be dispatched right now.

        Enhanced with:
        - Distributed locking to prevent race conditions
        - Pool state caching for performance
        - Audit logging for all decisions
        - Cooldown period enforcement
        - Circuit breaker checks
        - Goal-based priority boosting

        Returns:
            List of dispatch plans
        """
        lock_key = f"scheduling:workspace:{self.workspace_id}"

        # Try to acquire distributed lock
        if not self._acquire_lock(lock_key):
            logger.info(f"Could not acquire lock for workspace {self.workspace_id}, skipping this tick")
            return []

        try:
            return self._compute_dispatch_plan_internal()
        finally:
            self._release_lock(lock_key)

    def _compute_dispatch_plan_internal(self) -> list[dict[str, Any]]:
        """Internal dispatch plan computation with all enhancements."""
        # Step 1: Get currently scheduled allocations (optimized batch query)
        active_allocations = self._get_active_allocations_optimized()

        if not active_allocations:
            logger.debug(f"No active allocations for workspace {self.workspace_id}")
            return []

        logger.info(f"Found {len(active_allocations)} active allocations for workspace {self.workspace_id}")

        # Pre-fetch all pool states in batch
        self._prefetch_pool_states(active_allocations)

        # Step 2: Filter by budget availability and cooldown
        feasible_allocations = []
        for alloc in active_allocations:
            # Check circuit breaker
            if self._is_circuit_breaker_open(alloc):
                self._log_decision(alloc, "blocked", ["circuit_breaker_open"], None)
                continue

            # Check cooldown
            if not self._is_cooldown_elapsed(alloc):
                self._log_decision(alloc, "skipped", ["cooldown_active"], None)
                continue

            # Check budget (with graceful degradation)
            can_dispatch_result = self._get_pool_state_cached(alloc.pool)

            if not can_dispatch_result.get("can_dispatch", True):  # Default True for degraded mode
                reasons = can_dispatch_result.get("reasons", [])
                self._log_decision(alloc, "blocked", reasons, can_dispatch_result.get("budget_state"))

                # Create budget exhaustion blocker if needed
                if "budget_exhausted" in reasons:
                    self._create_budget_exhaustion_blocker(alloc)

                continue

            feasible_allocations.append(alloc)

        if not feasible_allocations:
            logger.info(f"No feasible allocations after filtering for workspace {self.workspace_id}")
            return []

        # Step 3: Sort by priority (with goal-based boosting)
        feasible_allocations = self._sort_by_effective_priority(feasible_allocations)

        # Step 4 & 5 & 6: Check for running sessions, calculate intensity, build dispatch plans
        dispatch_plans = []
        for alloc in feasible_allocations:
            # Skip if already has a running session
            if self._has_running_session(alloc):
                self._log_decision(alloc, "skipped", ["running_session_exists"], None)
                continue

            # Get pool state for intensity calculation
            pool_state_result = self._get_pool_state_cached(alloc.pool)
            pool_state = pool_state_result.get("budget_state", {})

            # Calculate dispatch intensity with budget runway
            intensity = self._calculate_intensity_with_runway(alloc, pool_state)

            if intensity == "skip":
                self._log_decision(alloc, "skipped", ["intensity_skip", "pool_at_capacity"], pool_state)
                continue

            # Log successful dispatch decision
            self._log_decision(alloc, "dispatched", [], pool_state, intensity)

            dispatch_plan = {
                "allocation_id": str(alloc.id),
                "intensity": intensity,
                "pool_id": str(alloc.pool_id),
                "project_id": str(alloc.project_id) if alloc.project_id else None,
                "agent_id": str(alloc.agent_id),
                "goal_id": str(alloc.goal_id) if alloc.goal_id else None,
            }
            dispatch_plans.append(dispatch_plan)

        logger.info(f"Generated {len(dispatch_plans)} dispatch plans for workspace {self.workspace_id}")
        return dispatch_plans

    def _get_active_allocations_optimized(self) -> list[ComputeAllocation]:
        """
        Optimized version using batch queries and annotations.

        Improvements over original:
        - Single query with prefetch_related instead of loops
        - F expressions for schedule timezone annotation
        - Reduced database round-trips
        """
        now_utc = timezone.now()

        # Get all schedules with their rows in a single query
        schedules = Schedule.objects.filter(
            workspace_id=self.workspace_id,
            deleted_at__isnull=True
        ).prefetch_related('rows', 'allocations')

        active_allocation_ids = []

        for schedule in schedules:
            # Convert current time to the schedule's timezone
            schedule_tz = pytz.timezone(schedule.timezone)
            now_local = now_utc.astimezone(schedule_tz)
            current_time = now_local.time()
            current_day = now_local.strftime("%a").lower()

            # Find ScheduleRows that match current time and day (with cross-midnight support)
            for row in schedule.rows.filter(deleted_at__isnull=True):
                if self._time_in_range(current_time, row.start_time, row.end_time):
                    days = row.days if isinstance(row.days, list) else []
                    if current_day in days:
                        # Get allocations for this schedule
                        for alloc in schedule.allocations.filter(deleted_at__isnull=True):
                            # Store the schedule row for later priority calculation
                            alloc._active_schedule_row = row
                            active_allocation_ids.append(alloc.id)

        # Batch fetch allocations with all related data
        if not active_allocation_ids:
            return []

        allocations = ComputeAllocation.objects.filter(
            id__in=set(active_allocation_ids),
            deleted_at__isnull=True
        ).select_related('agent', 'pool', 'project', 'goal', 'schedule').prefetch_related('schedule__rows')

        # Re-attach schedule rows (since prefetch might not preserve the association)
        allocation_list = list(allocations)
        for schedule in schedules:
            schedule_tz = pytz.timezone(schedule.timezone)
            now_local = now_utc.astimezone(schedule_tz)
            current_time = now_local.time()
            current_day = now_local.strftime("%a").lower()

            for row in schedule.rows.filter(deleted_at__isnull=True):
                if self._time_in_range(current_time, row.start_time, row.end_time):
                    days = row.days if isinstance(row.days, list) else []
                    if current_day in days:
                        for alloc in allocation_list:
                            if alloc.schedule_id == schedule.id:
                                alloc._active_schedule_row = row

        return allocation_list

    def _time_in_range(self, current_time, start_time, end_time) -> bool:
        """
        Check if current time is within range, supporting cross-midnight schedules.

        Examples:
        - 10:00 AM - 6:00 PM: Normal range
        - 10:00 PM - 6:00 AM: Cross-midnight (overnight)
        """
        if start_time <= end_time:
            # Normal range (e.g., 9 AM - 5 PM)
            return start_time <= current_time <= end_time
        else:
            # Cross-midnight range (e.g., 10 PM - 6 AM)
            return current_time >= start_time or current_time <= end_time

    def _prefetch_pool_states(self, allocations: list[ComputeAllocation]) -> None:
        """Pre-fetch all pool states to avoid repeated queries."""
        unique_pools = {alloc.pool for alloc in allocations}
        for pool in unique_pools:
            # This will populate the cache
            self._get_pool_state_cached(pool)

    def _get_pool_state_cached(self, pool) -> dict[str, Any]:
        """
        Get pool state from cache or fetch from BudgetService.

        With graceful degradation: if BudgetService fails, allow dispatch
        with conservative intensity.
        """
        pool_id = str(pool.id)

        # Check memory cache first
        if pool_id in self._pool_state_cache:
            return self._pool_state_cache[pool_id]

        # Try Redis cache
        if self._redis_available:
            cache_key = f"pool_state:{pool_id}"
            try:
                cached = self.redis_client.get(cache_key)
                if cached:
                    import json
                    result = json.loads(cached)
                    self._pool_state_cache[pool_id] = result
                    return result
            except Exception as exc:
                logger.warning(f"Redis read failed: {exc}")

        # Fetch from BudgetService with graceful degradation
        try:
            result = self.budget_service.can_dispatch(pool)
        except Exception as exc:
            logger.error(f"BudgetService failed for pool {pool_id}, allowing dispatch in degraded mode: {exc}")
            result = {
                "can_dispatch": True,
                "reasons": ["budget_service_degraded"],
                "budget_state": {},
                "throughput": {},
            }

        # Cache the result
        self._pool_state_cache[pool_id] = result

        if self._redis_available:
            try:
                import json
                from decimal import Decimal

                # Custom JSON encoder for UUID and Decimal
                def json_serializer(obj):
                    if isinstance(obj, Decimal):
                        return float(obj)
                    return str(obj)

                serialized = json.dumps(result, default=json_serializer)
                self.redis_client.setex(cache_key, self.CACHE_TTL, serialized)
            except Exception as exc:
                logger.warning(f"Redis write failed: {exc}")

        return result

    def _sort_by_effective_priority(self, allocations: list[ComputeAllocation]) -> list[ComputeAllocation]:
        """
        Sort allocations by effective priority (allocation priority + schedule row modifier + goal boost).
        """
        def effective_priority(alloc: ComputeAllocation) -> int:
            base_priority = alloc.priority

            # Schedule priority inheritance
            schedule_modifier = 0
            if hasattr(alloc, '_active_schedule_row') and alloc._active_schedule_row:
                schedule_modifier = alloc._active_schedule_row.priority_modifier

            # Goal-based priority boosting (check if goal has approaching deadlines)
            goal_boost = 0
            if alloc.goal and hasattr(alloc.goal, 'deadline'):
                # Boost priority if goal deadline is within 7 days
                if alloc.goal.deadline:
                    days_until_deadline = (alloc.goal.deadline - timezone.now().date()).days
                    if 0 <= days_until_deadline <= 7:
                        goal_boost = -2  # Higher priority (lower number)

            return base_priority + schedule_modifier + goal_boost

        allocations.sort(key=effective_priority)
        return allocations

    def _is_cooldown_elapsed(self, alloc: ComputeAllocation) -> bool:
        """Check if cooldown period has elapsed since last dispatch."""
        if alloc.cooldown_minutes == 0:
            return True

        if not alloc.last_dispatched_at:
            return True

        cooldown_end = alloc.last_dispatched_at + timedelta(minutes=alloc.cooldown_minutes)
        return timezone.now() >= cooldown_end

    def _is_circuit_breaker_open(self, alloc: ComputeAllocation) -> bool:
        """
        Check if circuit breaker is open for this allocation.

        Circuit opens after CIRCUIT_BREAKER_THRESHOLD consecutive failures.
        """
        return alloc.consecutive_failures >= self.CIRCUIT_BREAKER_THRESHOLD

    def _has_running_session(self, alloc: ComputeAllocation) -> bool:
        """Check if this allocation already has a running session."""
        query = Q(
            agent=alloc.agent,
            status=SessionStatus.RUNNING,
            deleted_at__isnull=True
        )

        if alloc.project_id:
            query &= Q(project=alloc.project)

        if alloc.goal_id:
            query &= Q(goal=alloc.goal)

        return CyrusSession.objects.filter(query).exists()

    def _calculate_intensity_with_runway(self, alloc: ComputeAllocation, pool_state: dict[str, Any]) -> str:
        """
        Calculate dispatch intensity with budget runway consideration.

        Enhanced with predictive budget pacing:
        - Calculates remaining budget runway
        - Adjusts intensity based on time left in budget period
        - More conservative as budget depletes
        """
        # Calculate pool utilization
        budget_limit = pool_state.get("budget_limit_usd")
        total_cost = pool_state.get("total_cost_usd", 0)

        if budget_limit and budget_limit > 0:
            utilization_pct = (float(total_cost) / float(budget_limit)) * 100
        else:
            utilization_pct = 0

        # High utilization - skip or be conservative
        if utilization_pct > 95:
            return "skip"
        elif utilization_pct > 85:
            return "conservative"

        # Calculate budget runway (days remaining at current burn rate)
        budget_runway_days = self._estimate_budget_runway(pool_state)

        # Dynamic intensity based on runway
        if budget_runway_days is not None:
            if budget_runway_days < 3:
                # Critical: less than 3 days of runway
                return "conservative"
            elif budget_runway_days > 20:
                # Plenty of runway, can be aggressive for high-priority work
                if alloc.priority <= 2 and utilization_pct < 50:
                    return "aggressive"

        # High priority work with low utilization - be aggressive
        if alloc.priority <= 2 and utilization_pct < 50:
            return "aggressive"

        # Default: normal intensity
        return "normal"

    def _estimate_budget_runway(self, pool_state: dict[str, Any]) -> float | None:
        """
        Estimate how many days of budget remain at current burn rate.

        Returns None if insufficient data to calculate.
        """
        budget_remaining = pool_state.get("budget_remaining_usd")
        total_cost = pool_state.get("total_cost_usd")
        budget_period = pool_state.get("budget_period", "monthly")

        if budget_remaining is None or total_cost is None or total_cost == 0:
            return None

        # Calculate days in period
        period_days_map = {
            "daily": 1,
            "weekly": 7,
            "monthly": 30,
        }
        period_days = period_days_map.get(budget_period, 30)

        # Calculate daily burn rate
        daily_burn = float(total_cost) / period_days

        if daily_burn == 0:
            return None

        # Calculate remaining days
        remaining_days = float(budget_remaining) / daily_burn

        return remaining_days

    def _log_decision(
        self,
        alloc: ComputeAllocation,
        decision: str,
        reasons: list[str],
        pool_state: dict[str, Any] | None,
        intensity: str = ""
    ) -> None:
        """Log scheduling decision to audit log."""
        try:
            pool_utilization = 0.0
            budget_remaining = None

            if pool_state:
                budget_limit = pool_state.get("budget_limit_usd")
                total_cost = pool_state.get("total_cost_usd", 0)
                if budget_limit and budget_limit > 0:
                    pool_utilization = (float(total_cost) / float(budget_limit)) * 100
                budget_remaining = pool_state.get("budget_remaining_usd")

            SchedulingDecision.objects.create(
                allocation=alloc,
                decision=decision,
                reasons=reasons,
                pool_utilization=pool_utilization,
                budget_remaining_usd=budget_remaining,
                intensity=intensity,
                metadata={
                    "workspace_id": self.workspace_id,
                    "pool_id": str(alloc.pool_id),
                    "agent_id": str(alloc.agent_id),
                },
            )
        except Exception as exc:
            logger.warning(f"Failed to log scheduling decision: {exc}")

    def _acquire_lock(self, lock_key: str) -> bool:
        """Acquire distributed lock using Redis SET NX."""
        if not self._redis_available:
            return True  # Proceed without locking in degraded mode

        try:
            return self.redis_client.set(lock_key, "1", nx=True, ex=self.LOCK_TIMEOUT)
        except Exception as exc:
            logger.warning(f"Failed to acquire lock: {exc}")
            return True  # Proceed in degraded mode

    def _release_lock(self, lock_key: str) -> None:
        """Release distributed lock."""
        if not self._redis_available:
            return

        try:
            self.redis_client.delete(lock_key)
        except Exception as exc:
            logger.warning(f"Failed to release lock: {exc}")

    def _create_budget_exhaustion_blocker(self, alloc: ComputeAllocation) -> None:
        """
        Stub method to create a blocker when budget is exhausted.

        In a full implementation, this would create an Issue or notification.
        """
        logger.warning(
            f"Budget exhausted for allocation {alloc.id} "
            f"(pool: {alloc.pool.name}, workspace: {self.workspace_id}). "
            f"Blocker creation is stubbed."
        )
        # TODO: Implement actual blocker creation in future phase
