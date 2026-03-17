# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
import requests

from plane.app.agents.dispatcher import ACPXDispatcher
from plane.app.agents.tasks import check_agent_health
from plane.app.metering.rate_model import PoolRateModel
from plane.app.metering.tracker import ComputeTracker
from plane.db.models import (
    Agent,
    AgentStatus,
    ComputePool,
    CyrusSession,
    Issue,
    PoolUsageRecord,
    Project,
    ProjectMember,
    RateLimitEvent,
    State,
    WorkspaceMember,
)
from plane.db.models.cyrus import PoolType, SessionStatus
from plane.db.models.state import StateGroup


@pytest.fixture
def cyrus_project(db, workspace, create_user):
    project = Project.objects.create(
        name="Phase 2 Project",
        identifier="PH2",
        workspace=workspace,
        created_by=create_user,
        workspace_path="C:\\workspaces\\phase-2",
    )
    ProjectMember.objects.create(project=project, member=create_user, role=20, is_active=True)
    backlog = State.objects.create(
        project=project,
        workspace=workspace,
        name="Backlog",
        color="#60646C",
        group=StateGroup.BACKLOG.value,
        default=True,
    )
    started = State.objects.create(
        project=project,
        workspace=workspace,
        name="In Progress",
        color="#F59E0B",
        group=StateGroup.STARTED.value,
    )
    issue = Issue.objects.create(project=project, workspace=workspace, name="Dispatch work item", state=backlog)
    return {"project": project, "backlog": backlog, "started": started, "issue": issue}


@pytest.fixture
def api_billing_pool(workspace):
    return ComputePool.objects.create(
        workspace=workspace,
        name="API Billing Pool",
        pool_type=PoolType.API_BILLING,
        provider="openai",
        cost_per_input_token_usd=Decimal("0.000001"),
        cost_per_output_token_usd=Decimal("0.000002"),
    )


@pytest.fixture
def subscription_pool(workspace):
    return ComputePool.objects.create(
        workspace=workspace,
        name="Subscription Pool",
        pool_type=PoolType.SUBSCRIPTION,
        provider="anthropic",
        rate_limits={"requests_per_minute": 100, "tokens_per_minute": 200000},
        uncertainty_pct=20,
        budget_limit_usd=Decimal("50.00"),
    )


@pytest.fixture
def agent(workspace, api_billing_pool):
    return Agent.objects.create(
        workspace=workspace,
        name="Relay Agent",
        agent_type="codex",
        relay_url="https://relay.example.com",
        relay_secret="secret",
        acpx_agent_name="codex",
        pool=api_billing_pool,
        status=AgentStatus.ONLINE,
    )


@pytest.mark.django_db
def test_dispatcher_stream_records_session_usage_and_tasks(cyrus_project, agent):
    response = MagicMock()
    response.status_code = 200
    response.raise_for_status.return_value = None
    response.iter_lines.return_value = [
        json.dumps({"type": "session_started", "session_id": "acpx-session-1", "model": "gpt-5"}),
        "{not-json",
        json.dumps(
            {
                "type": "done",
                "usage": {"input_tokens": 120, "output_tokens": 30, "total_tokens": 150},
                "model_name": "gpt-5",
            }
        ),
        json.dumps({"type": "relay_exit", "code": 0}),
    ]

    dispatcher = ACPXDispatcher(
        agent=agent,
        pool=agent.pool,
        project=cyrus_project["project"],
        work_item=cyrus_project["issue"],
    )

    with patch("plane.app.agents.dispatcher.requests.post", return_value=response), patch(
        "plane.app.agents.dispatcher.summarize_session.delay"
    ) as summarize_delay, patch("plane.app.agents.dispatcher.trace_session_to_langfuse.delay") as trace_delay, patch(
        "plane.app.agents.dispatcher.meter_session.delay"
    ) as meter_delay:
        session = dispatcher.dispatch("Ship the feature.")

    session.refresh_from_db()
    usage_record = PoolUsageRecord.objects.get(pool=agent.pool, session_id="acpx-session-1")
    cyrus_project["issue"].refresh_from_db()

    assert session.status == SessionStatus.COMPLETED
    assert session.acpx_session_id == "acpx-session-1"
    assert session.input_tokens == 120
    assert session.output_tokens == 30
    assert session.total_tokens == 150
    assert session.estimated_cost_usd == Decimal("0.000180")
    assert usage_record.estimated_cost_usd == Decimal("0.000180")
    assert cyrus_project["issue"].state_id == cyrus_project["started"].id
    summarize_delay.assert_called_once_with(session.id)
    trace_delay.assert_called_once_with(session.id)
    meter_delay.assert_called_once_with(session.id)


@pytest.mark.django_db
def test_dispatcher_marks_agent_offline_when_relay_unreachable(cyrus_project, agent):
    dispatcher = ACPXDispatcher(
        agent=agent,
        pool=agent.pool,
        project=cyrus_project["project"],
        work_item=cyrus_project["issue"],
    )

    with patch("plane.app.agents.dispatcher.requests.post", side_effect=requests.ConnectionError("relay offline")), patch(
        "plane.app.agents.dispatcher.summarize_session.delay"
    ), patch("plane.app.agents.dispatcher.trace_session_to_langfuse.delay"), patch(
        "plane.app.agents.dispatcher.meter_session.delay"
    ):
        session = dispatcher.dispatch("Still try dispatch.")

    session.refresh_from_db()
    agent.refresh_from_db()

    assert session.status == SessionStatus.FAILED
    assert agent.status == AgentStatus.OFFLINE


@pytest.mark.django_db
def test_compute_tracker_budget_state_applies_subscription_uncertainty(subscription_pool, workspace):
    agent = Agent.objects.create(
        workspace=workspace,
        name="Subscription Agent",
        agent_type="claude_code",
        relay_url="https://relay.example.com",
        relay_secret="secret",
        acpx_agent_name="claude",
        pool=subscription_pool,
    )
    PoolUsageRecord.objects.create(
        pool=subscription_pool,
        agent=agent,
        session_id="session-1",
        input_tokens=500,
        output_tokens=250,
        total_tokens=750,
        estimated_cost_usd=Decimal("0"),
        duration_seconds=12.5,
        was_rate_limited=True,
    )

    state = ComputeTracker(pool=subscription_pool).get_pool_budget_state()

    assert state["total_tokens"] == 750
    assert state["rate_limit_hits"] == 1
    assert state["safe_rate_limits"]["requests_per_minute"] == 80
    assert state["safe_rate_limits"]["tokens_per_minute"] == 160000
    assert state["budget_remaining_usd"] == Decimal("50.00")


@pytest.mark.django_db
def test_pool_rate_model_learns_safe_throughput(subscription_pool, workspace):
    agent = Agent.objects.create(
        workspace=workspace,
        name="Rate Limited Agent",
        agent_type="codex",
        relay_url="https://relay.example.com",
        relay_secret="secret",
        acpx_agent_name="codex",
        pool=subscription_pool,
    )
    session = CyrusSession.objects.create(agent=agent, project=None, work_item=None, goal=None, pool=subscription_pool)
    RateLimitEvent.objects.create(
        pool=subscription_pool,
        agent=agent,
        session=session,
        request_count=60,
        token_count=120000,
        retry_after_seconds=7,
    )

    throughput = PoolRateModel(subscription_pool).get_effective_throughput()

    assert throughput["learned"]["requests"] == 60
    assert throughput["learned"]["tokens"] == 120000
    assert throughput["safe"]["requests"] == 54
    assert throughput["safe"]["tokens"] == 108000
    assert throughput["event_count"] == 1


@pytest.mark.django_db
def test_check_agent_health_updates_statuses(workspace, api_billing_pool):
    WorkspaceMember.objects.get_or_create(workspace=workspace, member=workspace.owner, defaults={"role": 20})
    healthy_agent = Agent.objects.create(
        workspace=workspace,
        name="Healthy Agent",
        agent_type="codex",
        relay_url="https://healthy.example.com",
        relay_secret="secret",
        acpx_agent_name="codex",
        pool=api_billing_pool,
        status=AgentStatus.ONLINE,
    )
    timeout_agent = Agent.objects.create(
        workspace=workspace,
        name="Timeout Agent",
        agent_type="codex",
        relay_url="https://timeout.example.com",
        relay_secret="secret",
        acpx_agent_name="codex",
        pool=api_billing_pool,
        status=AgentStatus.DEGRADED,
    )

    def fake_get(url, headers, timeout):
        if "healthy" in url:
            response = MagicMock()
            response.status_code = 200
            return response
        raise requests.Timeout("timed out")

    with patch("plane.app.agents.tasks.requests.get", side_effect=fake_get):
        result = check_agent_health()

    healthy_agent.refresh_from_db()
    timeout_agent.refresh_from_db()

    assert result["online"] == 1
    assert result["offline"] == 1
    assert healthy_agent.status == AgentStatus.ONLINE
    assert timeout_agent.status == AgentStatus.OFFLINE
    assert healthy_agent.last_heartbeat is not None
    assert timeout_agent.last_heartbeat is not None
