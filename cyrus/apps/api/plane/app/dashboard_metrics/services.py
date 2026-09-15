from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Case, Count, F, Max, Q, Sum, Value, When
from django.db.models.functions import TruncDate
from django.utils import timezone

from plane.db.models import (
    Agent,
    Approval,
    ApprovalStatus,
    ComputeAllocation,
    ComputePool,
    CyrusSession,
    Goal,
    GoalKPI,
    GoalStatus,
    PoolUsageRecord,
    RateLimitEvent,
    SchedulingDecision,
    SessionStatus,
    AgentStatus,
)


class AgentMetricProvider:
    """Aggregates Cyrus metrics for dashboard consumption (Tremor.so charts)."""

    def __init__(self, workspace_id):
        self.workspace_id = workspace_id

    # ------------------------------------------------------------------ #
    # Token consumption time-series
    # ------------------------------------------------------------------ #
    def get_token_consumption(self, days=7):
        """Daily token consumption from PoolUsageRecord."""
        cutoff = timezone.now() - timedelta(days=days)
        qs = (
            PoolUsageRecord.objects.filter(
                pool__workspace_id=self.workspace_id,
                timestamp__gte=cutoff,
                deleted_at__isnull=True,
            )
            .annotate(date=TruncDate("timestamp"))
            .values("date")
            .annotate(
                input_tokens=Sum("input_tokens"),
                output_tokens=Sum("output_tokens"),
                total_tokens=Sum("total_tokens"),
            )
            .order_by("date")
        )
        return [
            {
                "date": row["date"].isoformat(),
                "input_tokens": row["input_tokens"] or 0,
                "output_tokens": row["output_tokens"] or 0,
                "total_tokens": row["total_tokens"] or 0,
            }
            for row in qs
        ]

    # ------------------------------------------------------------------ #
    # Cost time-series grouped by ComputePool
    # ------------------------------------------------------------------ #
    def get_cost_incurred(self, days=7):
        """Daily cost grouped by ComputePool name."""
        cutoff = timezone.now() - timedelta(days=days)
        qs = (
            PoolUsageRecord.objects.filter(
                pool__workspace_id=self.workspace_id,
                timestamp__gte=cutoff,
                deleted_at__isnull=True,
            )
            .annotate(date=TruncDate("timestamp"))
            .values("date", pool_name=F("pool__name"))
            .annotate(cost_usd=Sum("estimated_cost_usd"))
            .order_by("date", "pool_name")
        )
        return [
            {
                "date": row["date"].isoformat(),
                "pool": row["pool_name"],
                "cost_usd": float(row["cost_usd"] or Decimal("0")),
            }
            for row in qs
        ]

    # ------------------------------------------------------------------ #
    # Session statistics (last 7 days)
    # ------------------------------------------------------------------ #
    def get_session_stats(self):
        """Total sessions, success rate %, avg duration over last 7 days."""
        cutoff = timezone.now() - timedelta(days=7)
        qs = CyrusSession.objects.filter(
            pool__workspace_id=self.workspace_id,
            started_at__gte=cutoff,
            deleted_at__isnull=True,
        )
        agg = qs.aggregate(
            total=Count("id"),
            completed=Count("id", filter=Q(status=SessionStatus.COMPLETED)),
            avg_duration=Avg("duration_seconds"),
        )
        total = agg["total"] or 0
        completed = agg["completed"] or 0
        success_rate = round((completed / total) * 100, 1) if total else 0.0
        return {
            "total_sessions": total,
            "completed_sessions": completed,
            "success_rate_pct": success_rate,
            "avg_duration_seconds": round(agg["avg_duration"] or 0, 2),
        }

    # ------------------------------------------------------------------ #
    # Active alerts
    # ------------------------------------------------------------------ #
    def get_active_alerts(self):
        """Blockers, pending approvals, and alignment-drift flags."""
        active_blockers = CyrusSession.objects.filter(
            pool__workspace_id=self.workspace_id,
            status__in=[SessionStatus.FAILED, SessionStatus.RATE_LIMITED],
            deleted_at__isnull=True,
        ).count()

        pending_approvals = Approval.objects.filter(
            agent__workspace_id=self.workspace_id,
            status=ApprovalStatus.PENDING,
            deleted_at__isnull=True,
        ).count()

        alignment_drift = Agent.objects.filter(
            workspace_id=self.workspace_id,
            status__in=[AgentStatus.DEGRADED, AgentStatus.ERRORED],
            deleted_at__isnull=True,
        ).count()

        return {
            "active_blockers": active_blockers,
            "pending_approvals": pending_approvals,
            "alignment_drift": alignment_drift,
        }

    # ------------------------------------------------------------------ #
    # Convenience: full dashboard payload
    # ------------------------------------------------------------------ #
    def get_all(self, days=7):
        return {
            "token_consumption": self.get_token_consumption(days=days),
            "cost_incurred": self.get_cost_incurred(days=days),
            "session_stats": self.get_session_stats(),
            "active_alerts": self.get_active_alerts(),
        }

    # ================================================================== #
    #  PHASE 6 — Additional Dashboard Endpoints
    # ================================================================== #

    # ------------------------------------------------------------------ #
    # Agent health roster
    # ------------------------------------------------------------------ #
    def get_agent_health(self):
        """Per-agent status, heartbeat age, active/recent session counts."""
        now = timezone.now()
        cutoff_7d = now - timedelta(days=7)

        agents = (
            Agent.objects.filter(
                workspace_id=self.workspace_id,
                deleted_at__isnull=True,
            )
            .annotate(
                active_sessions=Count(
                    "sessions",
                    filter=Q(sessions__status=SessionStatus.RUNNING, sessions__deleted_at__isnull=True),
                ),
                sessions_7d=Count(
                    "sessions",
                    filter=Q(sessions__started_at__gte=cutoff_7d, sessions__deleted_at__isnull=True),
                ),
                completed_7d=Count(
                    "sessions",
                    filter=Q(
                        sessions__started_at__gte=cutoff_7d,
                        sessions__status=SessionStatus.COMPLETED,
                        sessions__deleted_at__isnull=True,
                    ),
                ),
                failed_7d=Count(
                    "sessions",
                    filter=Q(
                        sessions__started_at__gte=cutoff_7d,
                        sessions__status=SessionStatus.FAILED,
                        sessions__deleted_at__isnull=True,
                    ),
                ),
                total_tokens_7d=Sum(
                    "sessions__total_tokens",
                    filter=Q(sessions__started_at__gte=cutoff_7d, sessions__deleted_at__isnull=True),
                ),
                total_cost_7d=Sum(
                    "sessions__estimated_cost_usd",
                    filter=Q(sessions__started_at__gte=cutoff_7d, sessions__deleted_at__isnull=True),
                ),
            )
            .order_by("name")
        )

        result = []
        for a in agents:
            heartbeat_age_sec = None
            if a.last_heartbeat:
                heartbeat_age_sec = round((now - a.last_heartbeat).total_seconds())
            success_rate = (
                round((a.completed_7d / a.sessions_7d) * 100, 1) if a.sessions_7d else 0.0
            )
            result.append({
                "id": str(a.id),
                "name": a.name,
                "agent_type": a.agent_type,
                "status": a.status,
                "last_heartbeat": a.last_heartbeat.isoformat() if a.last_heartbeat else None,
                "heartbeat_age_seconds": heartbeat_age_sec,
                "active_sessions": a.active_sessions,
                "sessions_7d": a.sessions_7d,
                "success_rate_7d_pct": success_rate,
                "failed_7d": a.failed_7d,
                "total_tokens_7d": a.total_tokens_7d or 0,
                "total_cost_7d_usd": float(a.total_cost_7d or Decimal("0")),
            })
        return result

    # ------------------------------------------------------------------ #
    # Pool budget & utilization
    # ------------------------------------------------------------------ #
    def get_pool_budgets(self):
        """Per-pool budget state: limit, spent, remaining, burn rate, runway."""
        now = timezone.now()

        pools = ComputePool.objects.filter(
            workspace_id=self.workspace_id,
            deleted_at__isnull=True,
        )

        result = []
        for pool in pools:
            # Determine the budget period window
            period_start = self._get_period_start(pool.budget_period, now)

            usage_agg = PoolUsageRecord.objects.filter(
                pool=pool,
                timestamp__gte=period_start,
                deleted_at__isnull=True,
            ).aggregate(
                total_cost=Sum("estimated_cost_usd"),
                total_tokens=Sum("total_tokens"),
                record_count=Count("id"),
                rate_limited_count=Count("id", filter=Q(was_rate_limited=True)),
            )

            total_cost = float(usage_agg["total_cost"] or Decimal("0"))
            budget_limit = float(pool.budget_limit_usd or Decimal("0"))
            remaining = max(budget_limit - total_cost, 0.0)
            utilization_pct = round((total_cost / budget_limit) * 100, 1) if budget_limit > 0 else 0.0

            # Burn rate: avg daily cost over the period so far
            days_in_period = max((now - period_start).total_seconds() / 86400, 1)
            daily_burn = round(total_cost / days_in_period, 4)
            runway_days = round(remaining / daily_burn, 1) if daily_burn > 0 else None

            result.append({
                "id": str(pool.id),
                "name": pool.name,
                "provider": pool.provider,
                "pool_type": pool.pool_type,
                "budget_period": pool.budget_period,
                "budget_limit_usd": budget_limit,
                "spent_usd": round(total_cost, 6),
                "remaining_usd": round(remaining, 6),
                "utilization_pct": utilization_pct,
                "daily_burn_usd": daily_burn,
                "runway_days": runway_days,
                "total_tokens": usage_agg["total_tokens"] or 0,
                "usage_records": usage_agg["record_count"] or 0,
                "rate_limited_records": usage_agg["rate_limited_count"] or 0,
            })
        return result

    # ------------------------------------------------------------------ #
    # Scheduling decision analytics
    # ------------------------------------------------------------------ #
    def get_scheduling_decisions(self, days=7):
        """Decision breakdown, reason frequency, intensity distribution."""
        cutoff = timezone.now() - timedelta(days=days)
        base_qs = SchedulingDecision.objects.filter(
            allocation__workspace_id=self.workspace_id,
            timestamp__gte=cutoff,
            deleted_at__isnull=True,
        )

        # Decision breakdown by type
        decision_counts = dict(
            base_qs.values_list("decision")
            .annotate(count=Count("id"))
            .values_list("decision", "count")
        )

        # Intensity distribution
        intensity_counts = dict(
            base_qs.exclude(intensity="")
            .values_list("intensity")
            .annotate(count=Count("id"))
            .values_list("intensity", "count")
        )

        # Reason frequency — reasons is a JSONField (list of strings)
        # We need to unpack in Python since DB-level JSON array unnest varies
        reason_freq = {}
        for row in base_qs.values_list("reasons", flat=True):
            if row:
                for reason in row:
                    reason_freq[reason] = reason_freq.get(reason, 0) + 1
        # Sort by frequency descending
        reason_freq = dict(sorted(reason_freq.items(), key=lambda x: -x[1]))

        # Time-series: decisions per day
        daily = (
            base_qs.annotate(date=TruncDate("timestamp"))
            .values("date")
            .annotate(
                dispatched=Count("id", filter=Q(decision="dispatched")),
                skipped=Count("id", filter=Q(decision="skipped")),
                blocked=Count("id", filter=Q(decision="blocked")),
                total=Count("id"),
            )
            .order_by("date")
        )
        time_series = [
            {
                "date": row["date"].isoformat(),
                "dispatched": row["dispatched"],
                "skipped": row["skipped"],
                "blocked": row["blocked"],
                "total": row["total"],
            }
            for row in daily
        ]

        return {
            "decision_counts": decision_counts,
            "intensity_distribution": intensity_counts,
            "reason_frequency": reason_freq,
            "time_series": time_series,
        }

    # ------------------------------------------------------------------ #
    # Rate limit events timeline
    # ------------------------------------------------------------------ #
    def get_rate_limit_events(self, days=7):
        """Rate limit events grouped by day and pool."""
        cutoff = timezone.now() - timedelta(days=days)

        # Daily totals
        daily = (
            RateLimitEvent.objects.filter(
                pool__workspace_id=self.workspace_id,
                timestamp__gte=cutoff,
                deleted_at__isnull=True,
            )
            .annotate(date=TruncDate("timestamp"))
            .values("date", pool_name=F("pool__name"))
            .annotate(
                event_count=Count("id"),
                avg_retry_seconds=Avg("retry_after_seconds"),
                total_tokens_affected=Sum("token_count"),
            )
            .order_by("date", "pool_name")
        )

        time_series = [
            {
                "date": row["date"].isoformat(),
                "pool": row["pool_name"],
                "event_count": row["event_count"],
                "avg_retry_seconds": round(row["avg_retry_seconds"] or 0, 2),
                "total_tokens_affected": row["total_tokens_affected"] or 0,
            }
            for row in daily
        ]

        # Summary stats
        summary = RateLimitEvent.objects.filter(
            pool__workspace_id=self.workspace_id,
            timestamp__gte=cutoff,
            deleted_at__isnull=True,
        ).aggregate(
            total_events=Count("id"),
            avg_retry=Avg("retry_after_seconds"),
            max_retry=Max("retry_after_seconds"),
            pools_affected=Count("pool", distinct=True),
            agents_affected=Count("agent", distinct=True),
        )

        return {
            "time_series": time_series,
            "summary": {
                "total_events": summary["total_events"] or 0,
                "avg_retry_seconds": round(summary["avg_retry"] or 0, 2),
                "max_retry_seconds": round(summary["max_retry"] or 0, 2),
                "pools_affected": summary["pools_affected"] or 0,
                "agents_affected": summary["agents_affected"] or 0,
            },
        }

    # ------------------------------------------------------------------ #
    # Goal progress & KPI overview
    # ------------------------------------------------------------------ #
    def get_goal_progress(self):
        """Goal status distribution, deadline proximity, KPI summary."""
        now = timezone.now()

        goals = Goal.objects.filter(
            workspace_id=self.workspace_id,
            deleted_at__isnull=True,
        )

        # Status distribution
        status_dist = dict(
            goals.values_list("status")
            .annotate(count=Count("id"))
            .values_list("status", "count")
        )

        # Deadline proximity — active goals with deadlines
        approaching = []
        for g in goals.filter(status=GoalStatus.ACTIVE, deadline__isnull=False).order_by("deadline"):
            days_left = (g.deadline - now).total_seconds() / 86400
            approaching.append({
                "id": str(g.id),
                "name": g.name,
                "deadline": g.deadline.isoformat(),
                "days_remaining": round(days_left, 1),
                "is_overdue": days_left < 0,
            })

        # KPI overview — latest values for active goals
        kpis = (
            GoalKPI.objects.filter(
                goal__workspace_id=self.workspace_id,
                goal__status=GoalStatus.ACTIVE,
                deleted_at__isnull=True,
            )
            .select_related("goal")
            .order_by("goal__name", "name")
        )
        kpi_list = [
            {
                "goal_id": str(k.goal_id),
                "goal_name": k.goal.name,
                "kpi_name": k.name,
                "unit": k.unit,
                "current_value": float(k.current_value) if k.current_value is not None else None,
                "last_collected": k.last_collected.isoformat() if k.last_collected else None,
                "history_points": len(k.history) if isinstance(k.history, list) else 0,
            }
            for k in kpis
        ]

        return {
            "status_distribution": status_dist,
            "total_goals": sum(status_dist.values()),
            "approaching_deadlines": approaching,
            "kpis": kpi_list,
        }

    # ------------------------------------------------------------------ #
    # Allocation health (circuit breakers, cooldowns, failures)
    # ------------------------------------------------------------------ #
    def get_allocation_health(self):
        """Allocation failure rates, circuit breaker status, dispatch frequency."""
        allocations = (
            ComputeAllocation.objects.filter(
                workspace_id=self.workspace_id,
                deleted_at__isnull=True,
            )
            .select_related("agent", "pool", "goal")
            .order_by("-consecutive_failures", "priority")
        )

        result = []
        for a in allocations:
            result.append({
                "id": str(a.id),
                "agent_name": a.agent.name,
                "pool_name": a.pool.name,
                "goal_name": a.goal.name if a.goal else None,
                "priority": a.priority,
                "consecutive_failures": a.consecutive_failures,
                "circuit_breaker_open": a.consecutive_failures >= 5,
                "cooldown_minutes": a.cooldown_minutes,
                "last_dispatched_at": a.last_dispatched_at.isoformat() if a.last_dispatched_at else None,
            })
        return result

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _get_period_start(budget_period, now):
        """Return the start of the current budget period."""
        if budget_period == "daily":
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif budget_period == "weekly":
            return (now - timedelta(days=now.weekday())).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        else:  # monthly
            return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
