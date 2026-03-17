# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest
from rest_framework import status

from plane.db.models import (
    Agent,
    Approval,
    ComputeAllocation,
    ComputePool,
    CyrusSession,
    Goal,
    GoalKPI,
    ModelTierConfig,
    PoolUsageRecord,
    Project,
    ProjectMember,
    Schedule,
    ScheduleRow,
    Workspace,
    WorkspaceMember,
)


@pytest.fixture
def project(db, workspace, create_user):
    project = Project.objects.create(
        name="Phase 1 Project",
        identifier="PH1",
        workspace=workspace,
        created_by=create_user,
    )
    ProjectMember.objects.create(project=project, member=create_user, role=20, is_active=True)
    return project


@pytest.fixture
def other_workspace(db, create_user):
    workspace = Workspace.objects.create(name="Other Workspace", owner=create_user, slug="other-workspace")
    WorkspaceMember.objects.create(workspace=workspace, member=create_user, role=20, is_active=True)
    return workspace


@pytest.mark.contract
class TestCyrusPhase1ProjectExtensions:
    @pytest.mark.django_db
    def test_create_project_with_phase1_fields(self, api_key_client, workspace):
        goal = Goal.objects.create(workspace=workspace, name="Launch Orchestration")

        response = api_key_client.post(
            f"/api/v1/workspaces/{workspace.slug}/projects/",
            {
                "name": "Cyrus Delivery",
                "identifier": "CYD",
                "workspace_path": "C:\\workspaces\\cyrus-delivery",
                "cycle_duration": "24h",
                "goal": str(goal.id),
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        created = Project.objects.get(id=response.data["id"])
        assert created.workspace_path == "C:\\workspaces\\cyrus-delivery"
        assert created.cycle_duration == "24h"
        assert created.goal_id == goal.id


@pytest.mark.contract
class TestCyrusPhase1Goals:
    @pytest.mark.django_db
    def test_goal_and_kpi_crud(self, api_key_client, workspace):
        goals_url = f"/api/v1/workspaces/{workspace.slug}/goals/"
        response = api_key_client.post(
            goals_url,
            {"name": "Reduce latency", "description": "Improve end-to-end dispatch time."},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        goal_id = response.data["id"]

        kpi_response = api_key_client.post(
            f"/api/v1/workspaces/{workspace.slug}/goal-kpis/",
            {"goal": goal_id, "name": "P95 dispatch latency", "unit": "seconds", "current_value": "12.5"},
            format="json",
        )
        assert kpi_response.status_code == status.HTTP_201_CREATED
        assert GoalKPI.objects.filter(goal_id=goal_id, name="P95 dispatch latency").exists()

        list_response = api_key_client.get(goals_url)
        assert list_response.status_code == status.HTTP_200_OK
        assert len(list_response.data["results"]) == 1

        patch_response = api_key_client.patch(
            f"/api/v1/workspaces/{workspace.slug}/goals/{goal_id}/",
            {"status": "paused"},
            format="json",
        )
        assert patch_response.status_code == status.HTTP_200_OK
        assert Goal.objects.get(id=goal_id).status == "paused"

        delete_response = api_key_client.delete(f"/api/v1/workspaces/{workspace.slug}/goals/{goal_id}/")
        assert delete_response.status_code == status.HTTP_204_NO_CONTENT
        assert not Goal.objects.filter(id=goal_id).exists()


@pytest.mark.contract
class TestCyrusPhase1Validation:
    @pytest.mark.django_db
    def test_agent_rejects_pool_from_another_workspace(self, api_key_client, workspace, other_workspace):
        foreign_pool = ComputePool.objects.create(
            workspace=other_workspace,
            name="Foreign Pool",
            pool_type="subscription",
            provider="openai",
        )

        response = api_key_client.post(
            f"/api/v1/workspaces/{workspace.slug}/agents/",
            {
                "name": "Main Codex",
                "agent_type": "codex",
                "relay_url": "https://relay.example.com",
                "pool": str(foreign_pool.id),
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "pool" in response.data


@pytest.mark.contract
class TestCyrusPhase1ResourceFlows:
    @pytest.mark.django_db
    def test_compute_and_session_resources_crud(self, api_key_client, workspace, project):
        goal = Goal.objects.create(workspace=workspace, name="Autonomous delivery")
        pool = ComputePool.objects.create(
            workspace=workspace,
            name="Primary Pool",
            pool_type="subscription",
            provider="openai",
        )
        agent = Agent.objects.create(
            workspace=workspace,
            name="Codex Gateway",
            agent_type="codex",
            relay_url="https://relay.example.com",
            pool=pool,
        )
        schedule = Schedule.objects.create(workspace=workspace, name="Weekday schedule")

        row_response = api_key_client.post(
            f"/api/v1/workspaces/{workspace.slug}/schedule-rows/",
            {
                "schedule": str(schedule.id),
                "start_time": "09:00:00",
                "end_time": "17:00:00",
                "days": ["mon", "tue", "wed"],
                "utilization_pct": 70,
            },
            format="json",
        )
        assert row_response.status_code == status.HTTP_201_CREATED
        assert ScheduleRow.objects.filter(schedule=schedule).count() == 1

        allocation_response = api_key_client.post(
            f"/api/v1/workspaces/{workspace.slug}/compute-allocations/",
            {
                "goal": str(goal.id),
                "project": str(project.id),
                "agent": str(agent.id),
                "pool": str(pool.id),
                "schedule": str(schedule.id),
                "priority": 3,
            },
            format="json",
        )
        assert allocation_response.status_code == status.HTTP_201_CREATED
        assert ComputeAllocation.objects.filter(workspace=workspace, agent=agent).exists()

        session_response = api_key_client.post(
            f"/api/v1/workspaces/{workspace.slug}/sessions/",
            {
                "goal": str(goal.id),
                "project": str(project.id),
                "agent": str(agent.id),
                "pool": str(pool.id),
                "status": "running",
                "acpx_session_id": "session-123",
            },
            format="json",
        )
        assert session_response.status_code == status.HTTP_201_CREATED
        assert CyrusSession.objects.filter(agent=agent, acpx_session_id="session-123").exists()

        usage_response = api_key_client.post(
            f"/api/v1/workspaces/{workspace.slug}/pool-usage-records/",
            {
                "goal": str(goal.id),
                "project": str(project.id),
                "agent": str(agent.id),
                "pool": str(pool.id),
                "session_id": "session-123",
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 150,
                "estimated_cost_usd": "0.123456",
            },
            format="json",
        )
        assert usage_response.status_code == status.HTTP_201_CREATED
        assert PoolUsageRecord.objects.filter(pool=pool, session_id="session-123").exists()

        approval_response = api_key_client.post(
            f"/api/v1/workspaces/{workspace.slug}/approvals/",
            {
                "goal": str(goal.id),
                "project": str(project.id),
                "agent": str(agent.id),
                "threshold_matched": "Deployment touches production credentials.",
            },
            format="json",
        )
        assert approval_response.status_code == status.HTTP_201_CREATED
        assert Approval.objects.filter(agent=agent, project=project).exists()

        tier_response = api_key_client.post(
            f"/api/v1/workspaces/{workspace.slug}/model-tier-configs/",
            {"tier": "high", "provider": "anthropic", "model_name": "claude-opus"},
            format="json",
        )
        assert tier_response.status_code == status.HTTP_201_CREATED
        assert ModelTierConfig.objects.filter(workspace=workspace, tier="high").exists()
