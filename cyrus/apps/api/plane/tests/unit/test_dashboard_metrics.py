# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""
Comprehensive tests for Phase 6 dashboard metrics:
  - AgentMetricProvider service (unit tests for each method)
  - All 7 dashboard API endpoints (contract tests via api_key_client)
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework import status

from plane.app.dashboard_metrics.services import AgentMetricProvider
from plane.db.models import (
    Agent,
    AgentStatus,
    Approval,
    ApprovalStatus,
    ComputeAllocation,
    ComputePool,
    CyrusSession,
    Goal,
    GoalKPI,
    GoalStatus,
    Issue,
    PoolUsageRecord,
    Project,
    ProjectMember,
    RateLimitEvent,
    Schedule,
    SchedulingDecision,
    SessionStatus,
    State,
)
from plane.db.models.cyrus import PoolType
from plane.db.models.state import StateGroup


# ====================================================================== #
#  Fixtures
# ====================================================================== #


@pytest.fixture
def pool_api(workspace):
    return ComputePool.objects.create(
        workspace=workspace,
        name="API Pool",
        pool_type=PoolType.API_BILLING,
        provider="openai",
        cost_per_input_token_usd=Decimal("0.000003"),
        cost_per_output_token_usd=Decimal("0.000006"),
        budget_limit_usd=Decimal("100.00"),
        budget_period="monthly",
    )


@pytest.fixture
def pool_sub(workspace):
    return ComputePool.objects.create(
        workspace=workspace,
        name="Subscription Pool",
        pool_type=PoolType.SUBSCRIPTION,
        provider="anthropic",
        budget_limit_usd=Decimal("50.00"),
        budget_period="daily",
    )


@pytest.fixture
def agent_online(workspace, pool_api):
    return Agent.objects.create(
        workspace=workspace,
        name="Agent Alpha",
        agent_type="claude_code",
        relay_url="https://alpha.example.com",
        pool=pool_api,
        status=AgentStatus.ONLINE,
        last_heartbeat=timezone.now() - timedelta(seconds=30),
    )


@pytest.fixture
def agent_degraded(workspace, pool_sub):
    return Agent.objects.create(
        workspace=workspace,
        name="Agent Beta",
        agent_type="codex",
        relay_url="https://beta.example.com",
        pool=pool_sub,
        status=AgentStatus.DEGRADED,
        last_heartbeat=timezone.now() - timedelta(minutes=10),
    )


@pytest.fixture
def agent_errored(workspace, pool_api):
    return Agent.objects.create(
        workspace=workspace,
        name="Agent Gamma",
        agent_type="gemini",
        relay_url="https://gamma.example.com",
        pool=pool_api,
        status=AgentStatus.ERRORED,
    )


@pytest.fixture
def goal_active(workspace):
    return Goal.objects.create(
        workspace=workspace,
        name="Ship v1",
        status=GoalStatus.ACTIVE,
        deadline=timezone.now() + timedelta(days=5),
    )


@pytest.fixture
def goal_overdue(workspace):
    return Goal.objects.create(
        workspace=workspace,
        name="Fix bugs",
        status=GoalStatus.ACTIVE,
        deadline=timezone.now() - timedelta(days=2),
    )


@pytest.fixture
def goal_archived(workspace):
    return Goal.objects.create(
        workspace=workspace,
        name="Old initiative",
        status=GoalStatus.ARCHIVED,
    )


@pytest.fixture
def kpis(goal_active):
    kpi1 = GoalKPI.objects.create(
        goal=goal_active,
        name="Coverage",
        unit="%",
        current_value=Decimal("82.5"),
        last_collected=timezone.now(),
        history=[{"date": "2026-03-15", "value": 75}, {"date": "2026-03-17", "value": 82.5}],
    )
    kpi2 = GoalKPI.objects.create(
        goal=goal_active,
        name="Latency p99",
        unit="ms",
        current_value=Decimal("110.0"),
        last_collected=timezone.now() - timedelta(hours=6),
        history=[],
    )
    return [kpi1, kpi2]


@pytest.fixture
def sessions(agent_online, agent_degraded, pool_api, pool_sub, goal_active):
    """Create a mix of sessions with different statuses."""
    now = timezone.now()
    results = []
    # 3 completed sessions for agent_online
    for i in range(3):
        results.append(
            CyrusSession.objects.create(
                agent=agent_online,
                pool=pool_api,
                goal=goal_active,
                status=SessionStatus.COMPLETED,
                started_at=now - timedelta(hours=i + 1),
                ended_at=now - timedelta(hours=i),
                total_tokens=1000 * (i + 1),
                input_tokens=700 * (i + 1),
                output_tokens=300 * (i + 1),
                estimated_cost_usd=Decimal("0.01") * (i + 1),
                duration_seconds=60.0 * (i + 1),
            )
        )
    # 1 failed session
    results.append(
        CyrusSession.objects.create(
            agent=agent_online,
            pool=pool_api,
            status=SessionStatus.FAILED,
            started_at=now - timedelta(hours=4),
            total_tokens=500,
            input_tokens=400,
            output_tokens=100,
            duration_seconds=15.0,
        )
    )
    # 1 running session
    results.append(
        CyrusSession.objects.create(
            agent=agent_degraded,
            pool=pool_sub,
            status=SessionStatus.RUNNING,
            started_at=now - timedelta(minutes=10),
            total_tokens=200,
            input_tokens=150,
            output_tokens=50,
            duration_seconds=0,
        )
    )
    # 1 rate_limited session
    results.append(
        CyrusSession.objects.create(
            agent=agent_degraded,
            pool=pool_sub,
            status=SessionStatus.RATE_LIMITED,
            started_at=now - timedelta(hours=2),
            total_tokens=0,
            was_rate_limited=True,
            duration_seconds=5.0,
        )
    )
    return results


@pytest.fixture
def usage_records(pool_api, pool_sub, agent_online, agent_degraded):
    """Usage records across two pools, spanning today and yesterday."""
    now = timezone.now()
    records = []
    # Today — pool_api
    records.append(
        PoolUsageRecord.objects.create(
            pool=pool_api,
            agent=agent_online,
            session_id="s1",
            input_tokens=5000,
            output_tokens=1000,
            total_tokens=6000,
            estimated_cost_usd=Decimal("0.021"),
            duration_seconds=45.0,
        )
    )
    # Today — pool_sub
    records.append(
        PoolUsageRecord.objects.create(
            pool=pool_sub,
            agent=agent_degraded,
            session_id="s2",
            input_tokens=3000,
            output_tokens=500,
            total_tokens=3500,
            estimated_cost_usd=Decimal("0.010"),
            duration_seconds=30.0,
            was_rate_limited=True,
        )
    )
    # Yesterday — pool_api
    yesterday_record = PoolUsageRecord.objects.create(
        pool=pool_api,
        agent=agent_online,
        session_id="s3",
        input_tokens=8000,
        output_tokens=2000,
        total_tokens=10000,
        estimated_cost_usd=Decimal("0.036"),
        duration_seconds=90.0,
    )
    PoolUsageRecord.objects.filter(pk=yesterday_record.pk).update(
        timestamp=now - timedelta(days=1)
    )
    records.append(yesterday_record)
    return records


@pytest.fixture
def rate_limit_events(pool_api, pool_sub, agent_online, agent_degraded):
    events = []
    events.append(
        RateLimitEvent.objects.create(
            pool=pool_api,
            agent=agent_online,
            retry_after_seconds=10.0,
            token_count=2000,
        )
    )
    events.append(
        RateLimitEvent.objects.create(
            pool=pool_api,
            agent=agent_online,
            retry_after_seconds=30.0,
            token_count=5000,
        )
    )
    events.append(
        RateLimitEvent.objects.create(
            pool=pool_sub,
            agent=agent_degraded,
            retry_after_seconds=60.0,
            token_count=1000,
        )
    )
    return events


@pytest.fixture
def schedule(workspace):
    return Schedule.objects.create(workspace=workspace, name="Business Hours")


@pytest.fixture
def allocations(workspace, agent_online, agent_degraded, pool_api, pool_sub, schedule, goal_active):
    alloc_healthy = ComputeAllocation.objects.create(
        workspace=workspace,
        agent=agent_online,
        pool=pool_api,
        schedule=schedule,
        goal=goal_active,
        priority=3,
        consecutive_failures=0,
        cooldown_minutes=10,
        last_dispatched_at=timezone.now() - timedelta(minutes=5),
    )
    alloc_broken = ComputeAllocation.objects.create(
        workspace=workspace,
        agent=agent_degraded,
        pool=pool_sub,
        schedule=schedule,
        priority=7,
        consecutive_failures=8,
        cooldown_minutes=30,
        last_dispatched_at=timezone.now() - timedelta(hours=1),
    )
    return [alloc_healthy, alloc_broken]


@pytest.fixture
def scheduling_decisions(allocations):
    alloc_healthy, alloc_broken = allocations
    decisions = []
    decisions.append(
        SchedulingDecision.objects.create(
            allocation=alloc_healthy,
            decision="dispatched",
            reasons=["budget_ok", "schedule_active"],
            pool_utilization=40.0,
            budget_remaining_usd=Decimal("80.00"),
            intensity="normal",
        )
    )
    decisions.append(
        SchedulingDecision.objects.create(
            allocation=alloc_healthy,
            decision="dispatched",
            reasons=["budget_ok"],
            pool_utilization=55.0,
            budget_remaining_usd=Decimal("60.00"),
            intensity="aggressive",
        )
    )
    decisions.append(
        SchedulingDecision.objects.create(
            allocation=alloc_broken,
            decision="blocked",
            reasons=["circuit_breaker_open", "budget_exhausted"],
            pool_utilization=96.0,
            budget_remaining_usd=Decimal("0.00"),
            intensity="skip",
        )
    )
    decisions.append(
        SchedulingDecision.objects.create(
            allocation=alloc_broken,
            decision="skipped",
            reasons=["cooldown_active"],
            pool_utilization=70.0,
            budget_remaining_usd=Decimal("5.00"),
            intensity="conservative",
        )
    )
    return decisions


@pytest.fixture
def approvals(agent_online, agent_degraded, goal_active):
    return [
        Approval.objects.create(
            agent=agent_online,
            goal=goal_active,
            threshold_matched="cost > $50",
            status=ApprovalStatus.PENDING,
        ),
        Approval.objects.create(
            agent=agent_degraded,
            threshold_matched="scope change",
            status=ApprovalStatus.PENDING,
        ),
        Approval.objects.create(
            agent=agent_online,
            threshold_matched="old request",
            status=ApprovalStatus.APPROVED,
        ),
    ]


@pytest.fixture
def provider(workspace):
    return AgentMetricProvider(workspace_id=workspace.id)


# ====================================================================== #
#  Unit Tests — AgentMetricProvider Service
# ====================================================================== #


@pytest.mark.unit
class TestTokenConsumption:
    @pytest.mark.django_db
    def test_returns_daily_aggregated_tokens(self, provider, usage_records):
        result = provider.get_token_consumption(days=7)
        assert len(result) == 2  # today + yesterday
        assert all({"date", "input_tokens", "output_tokens", "total_tokens"} == set(r.keys()) for r in result)
        # Yesterday's row
        yesterday = result[0]
        assert yesterday["input_tokens"] == 8000
        assert yesterday["output_tokens"] == 2000
        assert yesterday["total_tokens"] == 10000
        # Today's row (two records summed)
        today = result[1]
        assert today["input_tokens"] == 5000 + 3000
        assert today["output_tokens"] == 1000 + 500
        assert today["total_tokens"] == 6000 + 3500

    @pytest.mark.django_db
    def test_empty_when_no_records(self, provider):
        assert provider.get_token_consumption(days=7) == []

    @pytest.mark.django_db
    def test_respects_days_window(self, provider, usage_records):
        # days=0 effectively means last 0 days → nothing before now
        # days=1 should still catch today
        result = provider.get_token_consumption(days=1)
        # At minimum today's records should appear
        assert len(result) >= 1

    @pytest.mark.django_db
    def test_excludes_other_workspace(self, workspace, usage_records, create_user):
        from plane.db.models import Workspace, WorkspaceMember

        other_ws = Workspace.objects.create(name="Other WS", slug="other-ws", owner=create_user)
        WorkspaceMember.objects.create(workspace=other_ws, member=create_user, role=20)
        other_provider = AgentMetricProvider(workspace_id=other_ws.id)
        assert other_provider.get_token_consumption(days=30) == []


@pytest.mark.unit
class TestCostIncurred:
    @pytest.mark.django_db
    def test_returns_cost_grouped_by_pool(self, provider, usage_records):
        result = provider.get_cost_incurred(days=7)
        assert len(result) >= 2  # At least two pools today
        pools_seen = {r["pool"] for r in result}
        assert "API Pool" in pools_seen
        assert "Subscription Pool" in pools_seen
        for r in result:
            assert "date" in r
            assert "cost_usd" in r
            assert isinstance(r["cost_usd"], float)

    @pytest.mark.django_db
    def test_empty_when_no_records(self, provider):
        assert provider.get_cost_incurred(days=7) == []


@pytest.mark.unit
class TestSessionStats:
    @pytest.mark.django_db
    def test_computes_correct_aggregates(self, provider, sessions):
        result = provider.get_session_stats()
        assert result["total_sessions"] == 6
        assert result["completed_sessions"] == 3
        assert result["success_rate_pct"] == 50.0
        assert result["avg_duration_seconds"] > 0

    @pytest.mark.django_db
    def test_zero_sessions_returns_zero_rate(self, provider):
        result = provider.get_session_stats()
        assert result["total_sessions"] == 0
        assert result["success_rate_pct"] == 0.0
        assert result["avg_duration_seconds"] == 0


@pytest.mark.unit
class TestActiveAlerts:
    @pytest.mark.django_db
    def test_counts_blockers_approvals_and_drift(
        self, provider, sessions, approvals, agent_degraded, agent_errored
    ):
        result = provider.get_active_alerts()
        # 1 failed + 1 rate_limited session
        assert result["active_blockers"] == 2
        # 2 pending approvals
        assert result["pending_approvals"] == 2
        # agent_degraded + agent_errored
        assert result["alignment_drift"] == 2

    @pytest.mark.django_db
    def test_all_zeros_when_healthy(self, provider, pool_api):
        # Only an online agent with no sessions
        Agent.objects.create(
            workspace_id=provider.workspace_id,
            name="Healthy",
            agent_type="codex",
            relay_url="https://h.example.com",
            pool=pool_api,
            status=AgentStatus.ONLINE,
        )
        result = provider.get_active_alerts()
        assert result == {"active_blockers": 0, "pending_approvals": 0, "alignment_drift": 0}


@pytest.mark.unit
class TestGetAll:
    @pytest.mark.django_db
    def test_returns_all_four_sections(self, provider, usage_records, sessions):
        result = provider.get_all(days=7)
        assert set(result.keys()) == {"token_consumption", "cost_incurred", "session_stats", "active_alerts"}
        assert isinstance(result["token_consumption"], list)
        assert isinstance(result["cost_incurred"], list)
        assert isinstance(result["session_stats"], dict)
        assert isinstance(result["active_alerts"], dict)


@pytest.mark.unit
class TestAgentHealth:
    @pytest.mark.django_db
    def test_returns_per_agent_stats(self, provider, agent_online, agent_degraded, sessions):
        result = provider.get_agent_health()
        assert len(result) == 2
        by_name = {r["name"]: r for r in result}

        alpha = by_name["Agent Alpha"]
        assert alpha["status"] == "online"
        assert alpha["agent_type"] == "claude_code"
        assert alpha["heartbeat_age_seconds"] is not None
        assert alpha["heartbeat_age_seconds"] < 120  # within last 2 min
        assert alpha["sessions_7d"] == 4  # 3 completed + 1 failed
        assert alpha["failed_7d"] == 1
        assert alpha["success_rate_7d_pct"] == 75.0  # 3/4
        assert alpha["total_tokens_7d"] > 0

        beta = by_name["Agent Beta"]
        assert beta["status"] == "degraded"
        assert beta["active_sessions"] == 1  # 1 running session
        assert beta["sessions_7d"] == 2  # 1 running + 1 rate_limited

    @pytest.mark.django_db
    def test_no_heartbeat_returns_none(self, provider, agent_errored):
        result = provider.get_agent_health()
        assert len(result) == 1
        assert result[0]["last_heartbeat"] is None
        assert result[0]["heartbeat_age_seconds"] is None

    @pytest.mark.django_db
    def test_empty_when_no_agents(self, provider):
        assert provider.get_agent_health() == []


@pytest.mark.unit
class TestPoolBudgets:
    @pytest.mark.django_db
    def test_computes_budget_state(self, provider, pool_api, usage_records):
        result = provider.get_pool_budgets()
        # usage_records fixture creates records for both pool_api and pool_sub
        api_pool = next(r for r in result if r["name"] == "API Pool")
        assert api_pool["budget_limit_usd"] == 100.0
        assert api_pool["spent_usd"] > 0
        assert api_pool["remaining_usd"] < 100.0
        assert api_pool["utilization_pct"] > 0
        assert api_pool["total_tokens"] > 0

    @pytest.mark.django_db
    def test_runway_none_when_no_spending(self, provider, pool_sub):
        result = provider.get_pool_budgets()
        sub_pool = next(r for r in result if r["name"] == "Subscription Pool")
        assert sub_pool["spent_usd"] == 0
        assert sub_pool["runway_days"] is None

    @pytest.mark.django_db
    def test_rate_limited_records_counted(self, provider, pool_sub, usage_records):
        result = provider.get_pool_budgets()
        sub_pool = next(r for r in result if r["name"] == "Subscription Pool")
        assert sub_pool["rate_limited_records"] == 1

    @pytest.mark.django_db
    def test_daily_budget_period_start(self, provider, pool_sub, agent_degraded):
        """Ensure daily pools only sum today's costs."""
        now = timezone.now()
        # Create a record from yesterday for the daily pool
        old_record = PoolUsageRecord.objects.create(
            pool=pool_sub,
            agent=agent_degraded,
            session_id="old",
            total_tokens=99999,
            estimated_cost_usd=Decimal("49.00"),
        )
        PoolUsageRecord.objects.filter(pk=old_record.pk).update(
            timestamp=now - timedelta(days=1)
        )
        # And one from today
        PoolUsageRecord.objects.create(
            pool=pool_sub,
            agent=agent_degraded,
            session_id="today",
            total_tokens=100,
            estimated_cost_usd=Decimal("1.00"),
        )
        result = provider.get_pool_budgets()
        sub_pool = next(r for r in result if r["name"] == "Subscription Pool")
        # Only today's $1.00 should count (not yesterday's $49.00)
        assert sub_pool["spent_usd"] == 1.0
        assert sub_pool["remaining_usd"] == 49.0


@pytest.mark.unit
class TestSchedulingDecisions:
    @pytest.mark.django_db
    def test_decision_counts(self, provider, scheduling_decisions):
        result = provider.get_scheduling_decisions(days=7)
        assert result["decision_counts"]["dispatched"] == 2
        assert result["decision_counts"]["blocked"] == 1
        assert result["decision_counts"]["skipped"] == 1

    @pytest.mark.django_db
    def test_intensity_distribution(self, provider, scheduling_decisions):
        result = provider.get_scheduling_decisions(days=7)
        dist = result["intensity_distribution"]
        assert dist["normal"] == 1
        assert dist["aggressive"] == 1
        assert dist["skip"] == 1
        assert dist["conservative"] == 1

    @pytest.mark.django_db
    def test_reason_frequency_sorted_descending(self, provider, scheduling_decisions):
        result = provider.get_scheduling_decisions(days=7)
        freq = result["reason_frequency"]
        assert freq["budget_ok"] == 2  # appears in 2 dispatched decisions
        assert freq["circuit_breaker_open"] == 1
        # Verify sorted descending
        values = list(freq.values())
        assert values == sorted(values, reverse=True)

    @pytest.mark.django_db
    def test_time_series_has_daily_breakdown(self, provider, scheduling_decisions):
        result = provider.get_scheduling_decisions(days=7)
        ts = result["time_series"]
        assert len(ts) >= 1
        today = ts[0]
        assert today["dispatched"] == 2
        assert today["blocked"] == 1
        assert today["skipped"] == 1
        assert today["total"] == 4

    @pytest.mark.django_db
    def test_empty_when_no_decisions(self, provider):
        result = provider.get_scheduling_decisions(days=7)
        assert result["decision_counts"] == {}
        assert result["intensity_distribution"] == {}
        assert result["reason_frequency"] == {}
        assert result["time_series"] == []


@pytest.mark.unit
class TestRateLimitEvents:
    @pytest.mark.django_db
    def test_time_series_grouped_by_pool(self, provider, rate_limit_events):
        result = provider.get_rate_limit_events(days=7)
        ts = result["time_series"]
        pools = {r["pool"] for r in ts}
        assert "API Pool" in pools
        assert "Subscription Pool" in pools
        api_row = next(r for r in ts if r["pool"] == "API Pool")
        assert api_row["event_count"] == 2
        assert api_row["avg_retry_seconds"] == 20.0  # (10 + 30) / 2
        assert api_row["total_tokens_affected"] == 7000

    @pytest.mark.django_db
    def test_summary_stats(self, provider, rate_limit_events):
        result = provider.get_rate_limit_events(days=7)
        summary = result["summary"]
        assert summary["total_events"] == 3
        assert summary["pools_affected"] == 2
        assert summary["agents_affected"] == 2
        assert summary["max_retry_seconds"] == 60.0
        # avg of 10, 30, 60 = 33.33
        assert abs(summary["avg_retry_seconds"] - 33.33) < 0.1

    @pytest.mark.django_db
    def test_empty_when_no_events(self, provider):
        result = provider.get_rate_limit_events(days=7)
        assert result["time_series"] == []
        assert result["summary"]["total_events"] == 0


@pytest.mark.unit
class TestGoalProgress:
    @pytest.mark.django_db
    def test_status_distribution(self, provider, goal_active, goal_overdue, goal_archived):
        result = provider.get_goal_progress()
        assert result["total_goals"] == 3
        assert result["status_distribution"]["active"] == 2  # goal_active + goal_overdue
        assert result["status_distribution"]["archived"] == 1

    @pytest.mark.django_db
    def test_approaching_deadlines(self, provider, goal_active, goal_overdue):
        result = provider.get_goal_progress()
        deadlines = result["approaching_deadlines"]
        assert len(deadlines) == 2
        # Sorted by deadline, so overdue first
        overdue = deadlines[0]
        assert overdue["name"] == "Fix bugs"
        assert overdue["is_overdue"] is True
        assert overdue["days_remaining"] < 0

        upcoming = deadlines[1]
        assert upcoming["name"] == "Ship v1"
        assert upcoming["is_overdue"] is False
        assert 4 < upcoming["days_remaining"] < 6

    @pytest.mark.django_db
    def test_kpis_for_active_goals(self, provider, goal_active, goal_archived, kpis):
        # Also add a KPI on the archived goal — it should be excluded
        GoalKPI.objects.create(goal=goal_archived, name="Dead KPI", unit="x", current_value=0)
        result = provider.get_goal_progress()
        kpi_list = result["kpis"]
        assert len(kpi_list) == 2  # Only the two on goal_active
        coverage = next(k for k in kpi_list if k["kpi_name"] == "Coverage")
        assert coverage["current_value"] == 82.5
        assert coverage["unit"] == "%"
        assert coverage["history_points"] == 2

    @pytest.mark.django_db
    def test_empty_workspace(self, provider):
        result = provider.get_goal_progress()
        assert result["total_goals"] == 0
        assert result["approaching_deadlines"] == []
        assert result["kpis"] == []


@pytest.mark.unit
class TestAllocationHealth:
    @pytest.mark.django_db
    def test_circuit_breaker_detection(self, provider, allocations):
        result = provider.get_allocation_health()
        assert len(result) == 2
        # Sorted by -consecutive_failures, so broken first
        broken = result[0]
        assert broken["consecutive_failures"] == 8
        assert broken["circuit_breaker_open"] is True
        assert broken["agent_name"] == "Agent Beta"

        healthy = result[1]
        assert healthy["consecutive_failures"] == 0
        assert healthy["circuit_breaker_open"] is False

    @pytest.mark.django_db
    def test_goal_name_nullable(self, provider, allocations):
        result = provider.get_allocation_health()
        broken = next(r for r in result if r["agent_name"] == "Agent Beta")
        assert broken["goal_name"] is None
        healthy = next(r for r in result if r["agent_name"] == "Agent Alpha")
        assert healthy["goal_name"] == "Ship v1"

    @pytest.mark.django_db
    def test_empty_when_no_allocations(self, provider):
        assert provider.get_allocation_health() == []


@pytest.mark.unit
class TestPeriodStartHelper:
    def test_daily(self):
        now = timezone.now().replace(hour=15, minute=30, second=45)
        start = AgentMetricProvider._get_period_start("daily", now)
        assert start.hour == 0
        assert start.minute == 0
        assert start.second == 0
        assert start.date() == now.date()

    def test_weekly(self):
        # Pick a known Wednesday
        from datetime import datetime
        import pytz

        wed = datetime(2026, 3, 18, 14, 0, 0, tzinfo=pytz.UTC)  # Wednesday
        start = AgentMetricProvider._get_period_start("weekly", wed)
        assert start.weekday() == 0  # Monday
        assert start.hour == 0

    def test_monthly(self):
        from datetime import datetime
        import pytz

        mid_month = datetime(2026, 3, 18, 10, 0, 0, tzinfo=pytz.UTC)
        start = AgentMetricProvider._get_period_start("monthly", mid_month)
        assert start.day == 1
        assert start.hour == 0


# ====================================================================== #
#  Contract Tests — API Endpoints via api_key_client
# ====================================================================== #

BASE = "/api/v1/workspaces/test-workspace/dashboard"


@pytest.mark.contract
class TestDashboardMetricsEndpoint:
    @pytest.mark.django_db
    def test_returns_200_with_all_sections(self, api_key_client, workspace, usage_records, sessions):
        resp = api_key_client.get(f"{BASE}/metrics/")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert "token_consumption" in data
        assert "cost_incurred" in data
        assert "session_stats" in data
        assert "active_alerts" in data

    @pytest.mark.django_db
    def test_days_param(self, api_key_client, workspace):
        resp = api_key_client.get(f"{BASE}/metrics/?days=30")
        assert resp.status_code == status.HTTP_200_OK

    @pytest.mark.django_db
    def test_days_clamped_to_max(self, api_key_client, workspace):
        resp = api_key_client.get(f"{BASE}/metrics/?days=999")
        assert resp.status_code == status.HTTP_200_OK

    @pytest.mark.django_db
    def test_unauthenticated_returns_401(self, api_client, workspace):
        resp = api_client.get(f"{BASE}/metrics/")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.django_db
    def test_nonexistent_workspace_returns_403(self, api_key_client):
        # Permission check fires before 404 since user has no membership
        resp = api_key_client.get("/api/v1/workspaces/does-not-exist/dashboard/metrics/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.contract
class TestAgentHealthEndpoint:
    @pytest.mark.django_db
    def test_returns_agent_list(self, api_key_client, workspace, agent_online, agent_degraded, sessions):
        resp = api_key_client.get(f"{BASE}/agent-health/")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2
        names = {a["name"] for a in data}
        assert "Agent Alpha" in names
        assert "Agent Beta" in names

    @pytest.mark.django_db
    def test_empty_workspace(self, api_key_client, workspace):
        resp = api_key_client.get(f"{BASE}/agent-health/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json() == []


@pytest.mark.contract
class TestPoolBudgetsEndpoint:
    @pytest.mark.django_db
    def test_returns_pool_list(self, api_key_client, workspace, pool_api, pool_sub, usage_records):
        resp = api_key_client.get(f"{BASE}/pool-budgets/")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2
        for pool in data:
            assert "budget_limit_usd" in pool
            assert "spent_usd" in pool
            assert "remaining_usd" in pool
            assert "runway_days" in pool


@pytest.mark.contract
class TestSchedulingEndpoint:
    @pytest.mark.django_db
    def test_returns_decision_analytics(self, api_key_client, workspace, scheduling_decisions):
        resp = api_key_client.get(f"{BASE}/scheduling/")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert "decision_counts" in data
        assert "intensity_distribution" in data
        assert "reason_frequency" in data
        assert "time_series" in data
        assert data["decision_counts"]["dispatched"] == 2

    @pytest.mark.django_db
    def test_empty_decisions(self, api_key_client, workspace):
        resp = api_key_client.get(f"{BASE}/scheduling/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["decision_counts"] == {}


@pytest.mark.contract
class TestRateLimitsEndpoint:
    @pytest.mark.django_db
    def test_returns_timeline_and_summary(self, api_key_client, workspace, rate_limit_events):
        resp = api_key_client.get(f"{BASE}/rate-limits/")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert len(data["time_series"]) >= 1
        assert data["summary"]["total_events"] == 3

    @pytest.mark.django_db
    def test_with_days_param(self, api_key_client, workspace, rate_limit_events):
        resp = api_key_client.get(f"{BASE}/rate-limits/?days=1")
        assert resp.status_code == status.HTTP_200_OK


@pytest.mark.contract
class TestGoalsEndpoint:
    @pytest.mark.django_db
    def test_returns_goal_progress(self, api_key_client, workspace, goal_active, goal_overdue, kpis):
        resp = api_key_client.get(f"{BASE}/goals/")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["total_goals"] == 2
        assert len(data["approaching_deadlines"]) == 2
        assert len(data["kpis"]) == 2


@pytest.mark.contract
class TestAllocationHealthEndpoint:
    @pytest.mark.django_db
    def test_returns_allocation_list(self, api_key_client, workspace, allocations):
        resp = api_key_client.get(f"{BASE}/allocation-health/")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2
        breaker_open = [a for a in data if a["circuit_breaker_open"]]
        assert len(breaker_open) == 1

    @pytest.mark.django_db
    def test_empty_allocations(self, api_key_client, workspace):
        resp = api_key_client.get(f"{BASE}/allocation-health/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json() == []
