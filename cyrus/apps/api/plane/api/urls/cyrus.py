# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from plane.api.views import (
    AgentViewSet,
    ApprovalViewSet,
    ComputeAllocationViewSet,
    ComputePoolViewSet,
    CyrusSessionViewSet,
    GoalKPIViewSet,
    GoalViewSet,
    ModelTierConfigViewSet,
    PoolUsageRecordViewSet,
    ScheduleRowViewSet,
    ScheduleViewSet,
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
]
