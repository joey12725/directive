# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from plane.app.views.cyrus import (
    AppAgentHealthView,
    AppAgentListView,
    AppDashboardMetricsView,
    AppGoalDetailView,
    AppGoalKPIDetailView,
    AppGoalKPIListCreateView,
    AppGoalListView,
    AppGoalProgressView,
    AppPoolBudgetsView,
    AppPoolListView,
    AppSessionDetailView,
    AppSessionListView,
)

urlpatterns = [
    # Dashboard metrics
    path("workspaces/<str:slug>/cyrus/dashboard/metrics/", AppDashboardMetricsView.as_view(), name="app-cyrus-dashboard-metrics"),
    path("workspaces/<str:slug>/cyrus/dashboard/agent-health/", AppAgentHealthView.as_view(), name="app-cyrus-agent-health"),
    path("workspaces/<str:slug>/cyrus/dashboard/pool-budgets/", AppPoolBudgetsView.as_view(), name="app-cyrus-pool-budgets"),
    path("workspaces/<str:slug>/cyrus/dashboard/goals/", AppGoalProgressView.as_view(), name="app-cyrus-goals-progress"),
    # Goal CRUD
    path("workspaces/<str:slug>/cyrus/goals/", AppGoalListView.as_view(), name="app-cyrus-goals"),
    path("workspaces/<str:slug>/cyrus/goals/<uuid:goal_id>/", AppGoalDetailView.as_view(), name="app-cyrus-goal-detail"),
    path("workspaces/<str:slug>/cyrus/goals/<uuid:goal_id>/kpis/", AppGoalKPIListCreateView.as_view(), name="app-cyrus-goal-kpis"),
    path("workspaces/<str:slug>/cyrus/goals/<uuid:goal_id>/kpis/<uuid:kpi_id>/", AppGoalKPIDetailView.as_view(), name="app-cyrus-goal-kpi-detail"),
    # Other CRUD
    path("workspaces/<str:slug>/cyrus/agents/", AppAgentListView.as_view(), name="app-cyrus-agents"),
    path("workspaces/<str:slug>/cyrus/pools/", AppPoolListView.as_view(), name="app-cyrus-pools"),
    path("workspaces/<str:slug>/cyrus/sessions/", AppSessionListView.as_view(), name="app-cyrus-sessions"),
    path("workspaces/<str:slug>/cyrus/sessions/<uuid:session_id>/", AppSessionDetailView.as_view(), name="app-cyrus-session-detail"),
]
