# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from plane.api.views import (
    AgentHealthView,
    AgentViewSet,
    AllocationHealthView,
    ApprovalViewSet,
    ComputeAllocationViewSet,
    ComputePoolViewSet,
    CyrusSessionViewSet,
    DashboardMetricsView,
    GoalKPIViewSet,
    GoalProgressView,
    GoalViewSet,
    ModelTierConfigViewSet,
    PoolBudgetsView,
    PoolUsageRecordViewSet,
    RateLimitEventsView,
    ScheduleRowViewSet,
    ScheduleViewSet,
    SchedulingDecisionsView,
)

router = DefaultRouter()
router.register(r"goals", GoalViewSet, basename="workspace-goals")
router.register(r"goal-kpis", GoalKPIViewSet, basename="workspace-goal-kpis")
router.register(r"compute-pools", ComputePoolViewSet, basename="workspace-compute-pools")
router.register(r"agents", AgentViewSet, basename="workspace-agents")
router.register(r"pool-usage-records", PoolUsageRecordViewSet, basename="workspace-pool-usage-records")
router.register(r"schedules", ScheduleViewSet, basename="workspace-schedules")
router.register(r"schedule-rows", ScheduleRowViewSet, basename="workspace-schedule-rows")
router.register(r"compute-allocations", ComputeAllocationViewSet, basename="workspace-compute-allocations")
router.register(r"sessions", CyrusSessionViewSet, basename="workspace-cyrus-sessions")
router.register(r"approvals", ApprovalViewSet, basename="workspace-approvals")
router.register(r"model-tier-configs", ModelTierConfigViewSet, basename="workspace-model-tier-configs")

urlpatterns = [
    path("workspaces/<str:slug>/", include(router.urls)),
    # Dashboard metrics endpoints
    path("workspaces/<str:slug>/dashboard/metrics/", DashboardMetricsView.as_view(), name="workspace-dashboard-metrics"),
    path("workspaces/<str:slug>/dashboard/agent-health/", AgentHealthView.as_view(), name="workspace-dashboard-agent-health"),
    path("workspaces/<str:slug>/dashboard/pool-budgets/", PoolBudgetsView.as_view(), name="workspace-dashboard-pool-budgets"),
    path("workspaces/<str:slug>/dashboard/scheduling/", SchedulingDecisionsView.as_view(), name="workspace-dashboard-scheduling"),
    path("workspaces/<str:slug>/dashboard/rate-limits/", RateLimitEventsView.as_view(), name="workspace-dashboard-rate-limits"),
    path("workspaces/<str:slug>/dashboard/goals/", GoalProgressView.as_view(), name="workspace-dashboard-goals"),
    path("workspaces/<str:slug>/dashboard/allocation-health/", AllocationHealthView.as_view(), name="workspace-dashboard-allocation-health"),
]
