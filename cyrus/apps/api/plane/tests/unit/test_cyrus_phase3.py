# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from plane.app.metering.budget_service import BudgetService
from plane.app.metering.rate_model import PoolRateModel
from plane.app.metering.tracker import ComputeTracker
from plane.db.models import (
    Agent,
    AgentStatus,
    ComputePool,
    CyrusSession,
    PoolUsageRecord,
    RateLimitEvent,
)
from plane.db.models.cyrus import PoolType


@pytest.fixture
def api_billing_pool(workspace):
    """Create an API billing pool for testing."""
    return ComputePool.objects.create(
        workspace=workspace,
        name="API Billing Pool",
        pool_type=PoolType.API_BILLING,
        provider="openai",
        cost_per_input_token_usd=Decimal("0.000003"),
        cost_per_output_token_usd=Decimal("0.000015"),
        budget_limit_usd=Decimal("100.00"),
    )


@pytest.fixture
def subscription_pool(workspace):
    """Create a subscription pool for testing."""
    return ComputePool.objects.create(
        workspace=workspace,
        name="Subscription Pool",
        pool_type=PoolType.SUBSCRIPTION,
        provider="anthropic",
        rate_limits={"requests_per_minute": 50, "tokens_per_minute": 40000},
        uncertainty_pct=10,
        budget_limit_usd=Decimal("200.00"),
    )


@pytest.fixture
def api_agent(workspace, api_billing_pool):
    """Create an agent using API billing pool."""
    return Agent.objects.create(
        workspace=workspace,
        name="API Agent",
        agent_type="codex",
        relay_url="https://api-relay.example.com",
        relay_secret="secret",
        acpx_agent_name="codex",
        pool=api_billing_pool,
        status=AgentStatus.ONLINE,
    )


@pytest.fixture
def subscription_agent(workspace, subscription_pool):
    """Create an agent using subscription pool."""
    return Agent.objects.create(
        workspace=workspace,
        name="Subscription Agent",
        agent_type="claude_code",
        relay_url="https://sub-relay.example.com",
        relay_secret="secret",
        acpx_agent_name="claude",
        pool=subscription_pool,
        status=AgentStatus.ONLINE,
    )


# =============================================================================
# BudgetService.get_all_pool_states() Tests
# =============================================================================


@pytest.mark.django_db
def test_get_all_pool_states_returns_empty_list_for_workspace_with_no_pools(workspace):
    """Test that get_all_pool_states returns empty list when workspace has no pools."""
    service = BudgetService()
    states = service.get_all_pool_states(workspace.id)

    assert states == []


@pytest.mark.django_db
def test_get_all_pool_states_returns_states_for_all_pools(workspace, api_billing_pool, subscription_pool):
    """Test that get_all_pool_states returns budget states for all pools in workspace."""
    service = BudgetService()
    states = service.get_all_pool_states(workspace.id)

    assert len(states) == 2
    pool_ids = {state["pool_id"] for state in states}
    assert api_billing_pool.id in pool_ids
    assert subscription_pool.id in pool_ids


@pytest.mark.django_db
def test_get_all_pool_states_excludes_deleted_pools(workspace, api_billing_pool):
    """Test that get_all_pool_states excludes soft-deleted pools."""
    deleted_pool = ComputePool.objects.create(
        workspace=workspace,
        name="Deleted Pool",
        pool_type=PoolType.API_BILLING,
        provider="openai",
        deleted_at=timezone.now(),
    )

    service = BudgetService()
    states = service.get_all_pool_states(workspace.id)

    assert len(states) == 1
    assert states[0]["pool_id"] == api_billing_pool.id
    assert deleted_pool.id not in {state["pool_id"] for state in states}


# =============================================================================
# BudgetService.can_dispatch() Tests - Financial Checks
# =============================================================================


@pytest.mark.django_db
def test_can_dispatch_allows_dispatch_when_budget_available(api_billing_pool):
    """Test can_dispatch allows dispatch when budget is available."""
    service = BudgetService()
    result = service.can_dispatch(api_billing_pool)

    assert result["can_dispatch"] is True
    assert result["reasons"] == []
    assert result["budget_state"]["budget_remaining_usd"] == Decimal("100.00")


@pytest.mark.django_db
def test_can_dispatch_blocks_when_budget_exhausted(api_billing_pool, api_agent):
    """Test can_dispatch blocks dispatch when budget is exhausted."""
    # Create usage that exhausts the budget
    PoolUsageRecord.objects.create(
        pool=api_billing_pool,
        agent=api_agent,
        session_id="session-1",
        input_tokens=1000000,
        output_tokens=2000000,
        total_tokens=3000000,
        estimated_cost_usd=Decimal("33.00"),
    )
    PoolUsageRecord.objects.create(
        pool=api_billing_pool,
        agent=api_agent,
        session_id="session-2",
        input_tokens=1000000,
        output_tokens=2000000,
        total_tokens=3000000,
        estimated_cost_usd=Decimal("33.00"),
    )
    PoolUsageRecord.objects.create(
        pool=api_billing_pool,
        agent=api_agent,
        session_id="session-3",
        input_tokens=1000000,
        output_tokens=2000000,
        total_tokens=3000000,
        estimated_cost_usd=Decimal("34.00"),
    )

    service = BudgetService()
    result = service.can_dispatch(api_billing_pool)

    assert result["can_dispatch"] is False
    assert "budget_exhausted" in result["reasons"]
    assert result["budget_state"]["budget_remaining_usd"] == Decimal("0")


@pytest.mark.django_db
def test_can_dispatch_warns_at_90_percent_utilization(api_billing_pool, api_agent):
    """Test can_dispatch warns when budget utilization exceeds 90%."""
    # Create usage at 91% of budget
    PoolUsageRecord.objects.create(
        pool=api_billing_pool,
        agent=api_agent,
        session_id="session-high",
        input_tokens=3000000,
        output_tokens=2000000,
        total_tokens=5000000,
        estimated_cost_usd=Decimal("91.00"),
    )

    service = BudgetService()
    result = service.can_dispatch(api_billing_pool)

    assert result["can_dispatch"] is True  # Still allows dispatch
    assert "budget_warning_90pct" in result["reasons"]
    assert result["budget_state"]["budget_remaining_usd"] == Decimal("9.00")


@pytest.mark.django_db
def test_can_dispatch_allows_when_no_budget_limit_set(workspace):
    """Test can_dispatch allows dispatch when pool has no budget limit."""
    unlimited_pool = ComputePool.objects.create(
        workspace=workspace,
        name="Unlimited Pool",
        pool_type=PoolType.API_BILLING,
        provider="openai",
        budget_limit_usd=None,
    )

    service = BudgetService()
    result = service.can_dispatch(unlimited_pool)

    assert result["can_dispatch"] is True
    assert result["budget_state"]["budget_remaining_usd"] is None


# =============================================================================
# BudgetService.can_dispatch() Tests - Rate Limit Checks
# =============================================================================


@pytest.mark.django_db
def test_can_dispatch_blocks_subscription_pool_with_recent_rate_limits(subscription_pool, subscription_agent):
    """Test can_dispatch blocks subscription pools with >3 rate limit events in last 5 min."""
    now = timezone.now()
    session = CyrusSession.objects.create(
        agent=subscription_agent,
        pool=subscription_pool,
        project=None,
        work_item=None,
        goal=None,
    )

    # Create 4 rate limit events in the last 5 minutes
    for i in range(4):
        event = RateLimitEvent.objects.create(
            pool=subscription_pool,
            agent=subscription_agent,
            session=session,
            request_count=50,
            token_count=40000,
            retry_after_seconds=60,
        )
        # Manually set timestamp to be within 5 minutes
        event.timestamp = now - timedelta(minutes=i)
        event.save()

    service = BudgetService()
    result = service.can_dispatch(subscription_pool)

    assert result["can_dispatch"] is False
    assert "rate_limited_recently" in result["reasons"]


@pytest.mark.django_db
def test_can_dispatch_allows_subscription_pool_with_few_rate_limits(subscription_pool, subscription_agent):
    """Test can_dispatch allows subscription pools with <=3 rate limit events in last 5 min."""
    now = timezone.now()
    session = CyrusSession.objects.create(
        agent=subscription_agent,
        pool=subscription_pool,
        project=None,
        work_item=None,
        goal=None,
    )

    # Create only 3 rate limit events
    for i in range(3):
        event = RateLimitEvent.objects.create(
            pool=subscription_pool,
            agent=subscription_agent,
            session=session,
            request_count=50,
            token_count=40000,
            retry_after_seconds=60,
        )
        event.timestamp = now - timedelta(minutes=i)
        event.save()

    service = BudgetService()
    result = service.can_dispatch(subscription_pool)

    assert result["can_dispatch"] is True
    assert "rate_limited_recently" not in result["reasons"]


@pytest.mark.django_db
def test_can_dispatch_ignores_old_rate_limit_events(subscription_pool, subscription_agent):
    """Test can_dispatch ignores rate limit events older than 5 minutes."""
    now = timezone.now()
    session = CyrusSession.objects.create(
        agent=subscription_agent,
        pool=subscription_pool,
        project=None,
        work_item=None,
        goal=None,
    )

    # Create 4 rate limit events, but all older than 5 minutes
    for i in range(4):
        event = RateLimitEvent.objects.create(
            pool=subscription_pool,
            agent=subscription_agent,
            session=session,
            request_count=50,
            token_count=40000,
            retry_after_seconds=60,
        )
        event.timestamp = now - timedelta(minutes=6 + i)
        event.save()

    service = BudgetService()
    result = service.can_dispatch(subscription_pool)

    assert result["can_dispatch"] is True
    assert "rate_limited_recently" not in result["reasons"]


@pytest.mark.django_db
def test_can_dispatch_skips_rate_limit_check_for_api_billing_pools(api_billing_pool, api_agent):
    """Test can_dispatch does not check rate limits for API billing pools."""
    now = timezone.now()
    session = CyrusSession.objects.create(
        agent=api_agent,
        pool=api_billing_pool,
        project=None,
        work_item=None,
        goal=None,
    )

    # Create many rate limit events for API billing pool
    for i in range(10):
        event = RateLimitEvent.objects.create(
            pool=api_billing_pool,
            agent=api_agent,
            session=session,
            request_count=100,
            token_count=50000,
            retry_after_seconds=60,
        )
        event.timestamp = now - timedelta(minutes=i)
        event.save()

    service = BudgetService()
    result = service.can_dispatch(api_billing_pool)

    # Should not block due to rate limits (API billing pools are pay-per-use)
    assert result["can_dispatch"] is True
    assert "rate_limited_recently" not in result["reasons"]


# =============================================================================
# BudgetService.can_dispatch() Tests - Throughput Checks
# =============================================================================


@pytest.mark.django_db
def test_can_dispatch_warns_when_estimated_tokens_exceed_safe_throughput(subscription_pool):
    """Test can_dispatch warns when estimated tokens exceed safe throughput."""
    service = BudgetService()

    # Subscription pool has tokens_per_minute: 40000, safe is 90% = 36000
    result = service.can_dispatch(subscription_pool, estimated_tokens=50000)

    # Should warn but not block
    assert "throughput_insufficient" in result["reasons"]


@pytest.mark.django_db
def test_can_dispatch_allows_when_estimated_tokens_within_safe_throughput(subscription_pool):
    """Test can_dispatch allows when estimated tokens are within safe throughput."""
    service = BudgetService()

    # Well within safe throughput
    result = service.can_dispatch(subscription_pool, estimated_tokens=10000)

    assert "throughput_insufficient" not in result["reasons"]


@pytest.mark.django_db
def test_can_dispatch_skips_throughput_check_when_no_estimated_tokens(subscription_pool):
    """Test can_dispatch skips throughput check when estimated_tokens is None."""
    service = BudgetService()
    result = service.can_dispatch(subscription_pool, estimated_tokens=None)

    assert "throughput_insufficient" not in result["reasons"]


# =============================================================================
# BudgetService.can_dispatch() Tests - Combined Scenarios
# =============================================================================


@pytest.mark.django_db
def test_can_dispatch_blocks_with_multiple_issues(subscription_pool, subscription_agent):
    """Test can_dispatch correctly identifies multiple blocking issues."""
    # Exhaust budget
    PoolUsageRecord.objects.create(
        pool=subscription_pool,
        agent=subscription_agent,
        session_id="session-exhaust",
        input_tokens=10000000,
        output_tokens=5000000,
        total_tokens=15000000,
        estimated_cost_usd=Decimal("200.00"),
    )

    # Add recent rate limits
    now = timezone.now()
    session = CyrusSession.objects.create(
        agent=subscription_agent,
        pool=subscription_pool,
        project=None,
        work_item=None,
        goal=None,
    )
    for i in range(4):
        event = RateLimitEvent.objects.create(
            pool=subscription_pool,
            agent=subscription_agent,
            session=session,
            request_count=50,
            token_count=40000,
            retry_after_seconds=60,
        )
        event.timestamp = now - timedelta(minutes=i)
        event.save()

    service = BudgetService()
    result = service.can_dispatch(subscription_pool, estimated_tokens=50000)

    assert result["can_dispatch"] is False
    assert "budget_exhausted" in result["reasons"]
    assert "rate_limited_recently" in result["reasons"]
    assert "throughput_insufficient" in result["reasons"]


# =============================================================================
# BudgetService.forecast_remaining_capacity() Tests
# =============================================================================


@pytest.mark.django_db
def test_forecast_remaining_capacity_calculates_with_historical_data(api_billing_pool, api_agent):
    """Test forecast_remaining_capacity calculates correctly with historical data."""
    # Create 3 sessions with known costs
    for i in range(3):
        PoolUsageRecord.objects.create(
            pool=api_billing_pool,
            agent=api_agent,
            session_id=f"session-{i}",
            input_tokens=1000,
            output_tokens=500,
            total_tokens=1500,
            estimated_cost_usd=Decimal("10.50"),
            duration_seconds=15.0,
        )

    service = BudgetService()
    forecast = service.forecast_remaining_capacity(api_billing_pool, hours_ahead=24)

    assert forecast["pool_id"] == api_billing_pool.id
    assert forecast["hours_ahead"] == 24
    assert forecast["budget_remaining_usd"] == Decimal("68.50")  # 100 - 31.5
    assert forecast["avg_cost_per_session"] == Decimal("10.50")
    assert forecast["estimated_remaining_sessions"] == 6  # 68.5 / 10.5 = 6.52
    assert forecast["avg_tokens_per_session"] == 1500
    assert forecast["avg_duration_per_session"] == 15.0


@pytest.mark.django_db
def test_forecast_remaining_capacity_returns_none_when_no_historical_data(api_billing_pool):
    """Test forecast_remaining_capacity returns None for estimates when no data."""
    service = BudgetService()
    forecast = service.forecast_remaining_capacity(api_billing_pool)

    assert forecast["pool_id"] == api_billing_pool.id
    assert forecast["budget_remaining_usd"] == Decimal("100.00")
    assert forecast["avg_cost_per_session"] is None
    assert forecast["estimated_remaining_sessions"] is None
    assert forecast["avg_tokens_per_session"] is None
    assert forecast["avg_duration_per_session"] is None


@pytest.mark.django_db
def test_forecast_remaining_capacity_handles_zero_budget_remaining(api_billing_pool, api_agent):
    """Test forecast_remaining_capacity when budget is exhausted."""
    # Exhaust budget
    PoolUsageRecord.objects.create(
        pool=api_billing_pool,
        agent=api_agent,
        session_id="session-exhaust",
        input_tokens=3333333,
        output_tokens=2000000,
        total_tokens=5333333,
        estimated_cost_usd=Decimal("100.00"),
    )

    service = BudgetService()
    forecast = service.forecast_remaining_capacity(api_billing_pool)

    assert forecast["budget_remaining_usd"] == Decimal("0")
    assert forecast["estimated_remaining_sessions"] == 0


@pytest.mark.django_db
def test_forecast_remaining_capacity_handles_no_budget_limit(workspace):
    """Test forecast_remaining_capacity when pool has no budget limit."""
    unlimited_pool = ComputePool.objects.create(
        workspace=workspace,
        name="Unlimited Pool",
        pool_type=PoolType.API_BILLING,
        provider="openai",
        budget_limit_usd=None,
    )

    service = BudgetService()
    forecast = service.forecast_remaining_capacity(unlimited_pool)

    assert forecast["budget_remaining_usd"] is None
    assert forecast["estimated_remaining_sessions"] is None


@pytest.mark.django_db
def test_forecast_remaining_capacity_custom_hours_ahead(api_billing_pool, api_agent):
    """Test forecast_remaining_capacity respects custom hours_ahead parameter."""
    PoolUsageRecord.objects.create(
        pool=api_billing_pool,
        agent=api_agent,
        session_id="session-1",
        input_tokens=1000,
        output_tokens=500,
        total_tokens=1500,
        estimated_cost_usd=Decimal("5.00"),
        duration_seconds=10.0,
    )

    service = BudgetService()
    forecast = service.forecast_remaining_capacity(api_billing_pool, hours_ahead=48)

    assert forecast["hours_ahead"] == 48


# =============================================================================
# Integration Tests
# =============================================================================


@pytest.mark.django_db
def test_budget_service_integrates_with_compute_tracker(api_billing_pool, api_agent):
    """Test BudgetService correctly integrates with ComputeTracker."""
    # Create usage
    PoolUsageRecord.objects.create(
        pool=api_billing_pool,
        agent=api_agent,
        session_id="session-1",
        input_tokens=1000,
        output_tokens=500,
        total_tokens=1500,
        estimated_cost_usd=Decimal("7.50"),
    )

    service = BudgetService()
    result = service.can_dispatch(api_billing_pool)

    # Verify integration with ComputeTracker
    assert result["budget_state"]["total_cost_usd"] == Decimal("7.50")
    assert result["budget_state"]["total_tokens"] == 1500
    assert result["budget_state"]["session_count"] == 1


@pytest.mark.django_db
def test_budget_service_integrates_with_pool_rate_model(subscription_pool, subscription_agent):
    """Test BudgetService correctly integrates with PoolRateModel."""
    # Create a rate limit event
    session = CyrusSession.objects.create(
        agent=subscription_agent,
        pool=subscription_pool,
        project=None,
        work_item=None,
        goal=None,
    )
    RateLimitEvent.objects.create(
        pool=subscription_pool,
        agent=subscription_agent,
        session=session,
        request_count=40,
        token_count=30000,
        retry_after_seconds=60,
    )

    service = BudgetService()
    result = service.can_dispatch(subscription_pool)

    # Verify integration with PoolRateModel
    assert result["throughput"]["learned"]["requests"] == 40
    assert result["throughput"]["learned"]["tokens"] == 30000
    assert result["throughput"]["safe"]["requests"] == 36  # 90% of 40
    assert result["throughput"]["safe"]["tokens"] == 27000  # 90% of 30000
