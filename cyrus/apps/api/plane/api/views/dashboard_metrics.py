from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from plane.api.middleware.api_authentication import APIKeyAuthentication
from plane.app.permissions import WorkspaceEntityPermission
from plane.app.dashboard_metrics.services import AgentMetricProvider
from plane.db.models import Workspace


class _WorkspaceMetricsBase(APIView):
    """Shared auth/perm/workspace resolution for all dashboard views."""

    authentication_classes = [APIKeyAuthentication]
    permission_classes = [WorkspaceEntityPermission]

    @property
    def workspace_slug(self):
        return self.kwargs.get("slug")

    def _provider(self, slug):
        workspace = get_object_or_404(Workspace, slug=slug)
        return AgentMetricProvider(workspace_id=workspace.id)

    def _days(self, request):
        days = int(request.query_params.get("days", 7))
        return max(1, min(days, 90))


class DashboardMetricsView(_WorkspaceMetricsBase):
    """Combined overview: tokens, cost, sessions, alerts."""

    def get(self, request, slug):
        provider = self._provider(slug)
        return Response(provider.get_all(days=self._days(request)), status=status.HTTP_200_OK)


class AgentHealthView(_WorkspaceMetricsBase):
    """Per-agent status, heartbeat, session counts, cost."""

    def get(self, request, slug):
        provider = self._provider(slug)
        return Response(provider.get_agent_health(), status=status.HTTP_200_OK)


class PoolBudgetsView(_WorkspaceMetricsBase):
    """Per-pool budget state: limit, spent, remaining, burn rate, runway."""

    def get(self, request, slug):
        provider = self._provider(slug)
        return Response(provider.get_pool_budgets(), status=status.HTTP_200_OK)


class SchedulingDecisionsView(_WorkspaceMetricsBase):
    """Dispatch/skip/block breakdown, reason frequency, intensity distribution."""

    def get(self, request, slug):
        provider = self._provider(slug)
        return Response(
            provider.get_scheduling_decisions(days=self._days(request)),
            status=status.HTTP_200_OK,
        )


class RateLimitEventsView(_WorkspaceMetricsBase):
    """Rate limit event timeline by pool."""

    def get(self, request, slug):
        provider = self._provider(slug)
        return Response(
            provider.get_rate_limit_events(days=self._days(request)),
            status=status.HTTP_200_OK,
        )


class GoalProgressView(_WorkspaceMetricsBase):
    """Goal status distribution, deadline proximity, KPI overview."""

    def get(self, request, slug):
        provider = self._provider(slug)
        return Response(provider.get_goal_progress(), status=status.HTTP_200_OK)


class AllocationHealthView(_WorkspaceMetricsBase):
    """Allocation failure rates, circuit breakers, dispatch frequency."""

    def get(self, request, slug):
        provider = self._provider(slug)
        return Response(provider.get_allocation_health(), status=status.HTTP_200_OK)
