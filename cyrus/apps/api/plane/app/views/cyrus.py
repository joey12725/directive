"""
App-level (session-auth) Cyrus views.

These mirror the /api/v1/ external API views but use BaseSessionAuthentication
instead of APIKeyAuthentication, so the web frontend can call them with cookies.
"""

from django.db import models
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from plane.app.views.base import BaseAPIView
from plane.app.permissions import WorkspaceEntityPermission
from plane.app.dashboard_metrics.services import AgentMetricProvider
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
    Schedule,
    ScheduleRow,
    Workspace,
)


# ======================================================================
# Base mixin for workspace-scoped Cyrus views
# ======================================================================

class CyrusBaseView(BaseAPIView):
    permission_classes = [IsAuthenticated, WorkspaceEntityPermission]

    @property
    def workspace_slug(self):
        return self.kwargs.get("slug")

    def get_workspace(self):
        return get_object_or_404(Workspace, slug=self.kwargs["slug"])


# ======================================================================
# Dashboard metric views (session-auth versions)
# ======================================================================

class AppDashboardMetricsView(CyrusBaseView):
    def get(self, request, slug):
        workspace = self.get_workspace()
        days = max(1, min(int(request.query_params.get("days", 7)), 90))
        provider = AgentMetricProvider(workspace_id=workspace.id)
        return Response(provider.get_all(days=days), status=status.HTTP_200_OK)


class AppAgentHealthView(CyrusBaseView):
    def get(self, request, slug):
        workspace = self.get_workspace()
        provider = AgentMetricProvider(workspace_id=workspace.id)
        return Response(provider.get_agent_health(), status=status.HTTP_200_OK)


class AppPoolBudgetsView(CyrusBaseView):
    def get(self, request, slug):
        workspace = self.get_workspace()
        provider = AgentMetricProvider(workspace_id=workspace.id)
        return Response(provider.get_pool_budgets(), status=status.HTTP_200_OK)


class AppGoalProgressView(CyrusBaseView):
    def get(self, request, slug):
        workspace = self.get_workspace()
        provider = AgentMetricProvider(workspace_id=workspace.id)
        return Response(provider.get_goal_progress(), status=status.HTTP_200_OK)


# ======================================================================
# CRUD list views (session-auth)
# ======================================================================

def _paginated_list(queryset, serializer_fn):
    """Simple list helper — returns {results: [...]}."""
    items = queryset.order_by("-created_at")[:100]
    return Response({"results": [serializer_fn(obj) for obj in items]}, status=status.HTTP_200_OK)


def _kpi_to_dict(k):
    return {
        "id": str(k.id),
        "goal": str(k.goal_id),
        "name": k.name,
        "unit": k.unit,
        "current_value": float(k.current_value) if k.current_value is not None else None,
        "last_collected": k.last_collected.isoformat() if k.last_collected else None,
        "history": k.history or [],
        "created_at": k.created_at.isoformat(),
    }


def _goal_to_dict(g):
    return {
        "id": str(g.id),
        "name": g.name,
        "status": g.status,
        "deadline": g.deadline.isoformat() if g.deadline else None,
        "description": g.description,
        "created_at": g.created_at.isoformat(),
        "kpi_count": getattr(g, "_kpi_count", None),
    }


def _agent_to_dict(a):
    return {
        "id": str(a.id),
        "name": a.name,
        "agent_type": a.agent_type,
        "status": a.status,
        "relay_url": a.relay_url,
        "pool": str(a.pool_id),
        "pool_name": a.pool.name if a.pool else None,
        "last_heartbeat": a.last_heartbeat.isoformat() if a.last_heartbeat else None,
        "created_at": a.created_at.isoformat(),
    }


def _pool_to_dict(p):
    return {
        "id": str(p.id),
        "name": p.name,
        "provider": p.provider,
        "pool_type": p.pool_type,
        "budget_limit_usd": float(p.budget_limit_usd or 0),
        "budget_period": p.budget_period,
        "created_at": p.created_at.isoformat(),
    }


def _session_to_dict(s):
    return {
        "id": str(s.id),
        "acpx_session_id": s.acpx_session_id,
        "status": s.status,
        "agent": str(s.agent_id),
        "agent_name": s.agent.name if s.agent else None,
        "total_tokens": s.total_tokens,
        "estimated_cost_usd": float(s.estimated_cost_usd or 0),
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "duration_seconds": s.duration_seconds,
        "model_name": s.model_name,
    }


class AppGoalListView(CyrusBaseView):
    def get(self, request, slug):
        workspace = self.get_workspace()
        from django.db.models import Count
        qs = (
            Goal.objects.filter(workspace=workspace, deleted_at__isnull=True)
            .annotate(_kpi_count=Count("kpis", filter=models.Q(kpis__deleted_at__isnull=True)))
        )
        status_filter = request.query_params.get("status")
        if status_filter and status_filter in ("active", "paused", "archived"):
            qs = qs.filter(status=status_filter)
        return _paginated_list(qs, _goal_to_dict)

    def post(self, request, slug):
        workspace = self.get_workspace()
        data = request.data
        goal = Goal.objects.create(
            workspace=workspace,
            name=data.get("name", ""),
            description=data.get("description", ""),
            status=data.get("status", "active"),
            deadline=data.get("deadline"),
            created_by=request.user,
        )
        return Response(_goal_to_dict(goal), status=status.HTTP_201_CREATED)


class AppAgentListView(CyrusBaseView):
    def get(self, request, slug):
        workspace = self.get_workspace()
        qs = Agent.objects.filter(workspace=workspace, deleted_at__isnull=True).select_related("pool")
        return _paginated_list(qs, _agent_to_dict)


class AppPoolListView(CyrusBaseView):
    def get(self, request, slug):
        workspace = self.get_workspace()
        qs = ComputePool.objects.filter(workspace=workspace, deleted_at__isnull=True)
        return _paginated_list(qs, _pool_to_dict)


class AppSessionListView(CyrusBaseView):
    def get(self, request, slug):
        workspace = self.get_workspace()
        qs = CyrusSession.objects.filter(
            pool__workspace=workspace, deleted_at__isnull=True
        ).select_related("agent")
        return _paginated_list(qs, _session_to_dict)


class AppSessionDetailView(CyrusBaseView):
    def get(self, request, slug, session_id):
        workspace = self.get_workspace()
        session = get_object_or_404(
            CyrusSession.objects.select_related("agent", "pool", "goal"),
            id=session_id,
            pool__workspace=workspace,
            deleted_at__isnull=True,
        )
        data = {
            "id": str(session.id),
            "acpx_session_id": session.acpx_session_id,
            "status": session.status,
            "agent": str(session.agent_id),
            "agent_name": session.agent.name if session.agent else None,
            "goal": str(session.goal_id) if session.goal_id else None,
            "goal_name": session.goal.name if session.goal else None,
            "project": str(session.project_id) if session.project_id else None,
            "work_item": str(session.work_item_id) if session.work_item_id else None,
            "pool": str(session.pool_id),
            "pool_name": session.pool.name if session.pool else None,
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "ended_at": session.ended_at.isoformat() if session.ended_at else None,
            "event_log": session.event_log or [],
            "summary": session.summary,
            "outcome": session.outcome or {},
            "total_tokens": session.total_tokens,
            "input_tokens": session.input_tokens,
            "output_tokens": session.output_tokens,
            "estimated_cost_usd": str(session.estimated_cost_usd),
            "duration_seconds": session.duration_seconds,
            "model_name": session.model_name,
            "was_rate_limited": session.was_rate_limited,
            "rate_limit_wait_seconds": session.rate_limit_wait_seconds,
            "langfuse_trace_id": session.langfuse_trace_id,
            "langfuse_trace_url": session.langfuse_trace_url,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
        }
        return Response(data, status=status.HTTP_200_OK)


# ======================================================================
# Goal detail + CRUD
# ======================================================================

class AppGoalDetailView(CyrusBaseView):
    """GET / PATCH / DELETE a single goal with nested KPIs."""

    def _get_goal(self, slug, goal_id):
        workspace = self.get_workspace()
        return get_object_or_404(Goal, id=goal_id, workspace=workspace, deleted_at__isnull=True)

    def get(self, request, slug, goal_id):
        goal = self._get_goal(slug, goal_id)
        kpis = GoalKPI.objects.filter(goal=goal, deleted_at__isnull=True).order_by("name")
        sessions = CyrusSession.objects.filter(
            goal=goal, deleted_at__isnull=True
        ).select_related("agent").order_by("-started_at")[:10]
        allocations = ComputeAllocation.objects.filter(
            goal=goal, deleted_at__isnull=True
        ).select_related("agent", "pool").count()

        data = {
            **_goal_to_dict(goal),
            "kpis": [_kpi_to_dict(k) for k in kpis],
            "allocation_count": allocations,
            "recent_sessions": [_session_to_dict(s) for s in sessions],
            "session_count": CyrusSession.objects.filter(goal=goal, deleted_at__isnull=True).count(),
        }
        return Response(data, status=status.HTTP_200_OK)

    def patch(self, request, slug, goal_id):
        goal = self._get_goal(slug, goal_id)
        data = request.data
        for field in ("name", "description", "status", "deadline"):
            if field in data:
                setattr(goal, field, data[field])
        goal.updated_by = request.user
        goal.save()
        return Response(_goal_to_dict(goal), status=status.HTTP_200_OK)

    def delete(self, request, slug, goal_id):
        goal = self._get_goal(slug, goal_id)
        goal.deleted_at = timezone.now()
        goal.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ======================================================================
# KPI CRUD (nested under goal)
# ======================================================================

class AppGoalKPIListCreateView(CyrusBaseView):
    """GET list / POST create KPIs for a goal."""

    def get(self, request, slug, goal_id):
        workspace = self.get_workspace()
        goal = get_object_or_404(Goal, id=goal_id, workspace=workspace, deleted_at__isnull=True)
        kpis = GoalKPI.objects.filter(goal=goal, deleted_at__isnull=True).order_by("name")
        return Response({"results": [_kpi_to_dict(k) for k in kpis]}, status=status.HTTP_200_OK)

    def post(self, request, slug, goal_id):
        workspace = self.get_workspace()
        goal = get_object_or_404(Goal, id=goal_id, workspace=workspace, deleted_at__isnull=True)
        data = request.data
        kpi = GoalKPI.objects.create(
            goal=goal,
            name=data.get("name", ""),
            unit=data.get("unit", ""),
            current_value=data.get("current_value"),
            last_collected=timezone.now() if data.get("current_value") is not None else None,
            history=[],
            created_by=request.user,
        )
        return Response(_kpi_to_dict(kpi), status=status.HTTP_201_CREATED)


class AppGoalKPIDetailView(CyrusBaseView):
    """PATCH / DELETE a single KPI."""

    def _get_kpi(self, slug, goal_id, kpi_id):
        workspace = self.get_workspace()
        goal = get_object_or_404(Goal, id=goal_id, workspace=workspace, deleted_at__isnull=True)
        return get_object_or_404(GoalKPI, id=kpi_id, goal=goal, deleted_at__isnull=True)

    def patch(self, request, slug, goal_id, kpi_id):
        kpi = self._get_kpi(slug, goal_id, kpi_id)
        data = request.data
        for field in ("name", "unit"):
            if field in data:
                setattr(kpi, field, data[field])
        # If current_value is updated, log a data point to history
        if "current_value" in data and data["current_value"] is not None:
            new_val = float(data["current_value"])
            history = kpi.history if isinstance(kpi.history, list) else []
            history.append({
                "date": timezone.now().strftime("%Y-%m-%d"),
                "value": new_val,
            })
            kpi.history = history
            kpi.current_value = new_val
            kpi.last_collected = timezone.now()
        kpi.updated_by = request.user
        kpi.save()
        return Response(_kpi_to_dict(kpi), status=status.HTTP_200_OK)

    def delete(self, request, slug, goal_id, kpi_id):
        kpi = self._get_kpi(slug, goal_id, kpi_id)
        kpi.deleted_at = timezone.now()
        kpi.save()
        return Response(status=status.HTTP_204_NO_CONTENT)
