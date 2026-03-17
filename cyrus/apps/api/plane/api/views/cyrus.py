# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response

from plane.app.permissions import WorkspaceEntityPermission
from plane.api.serializers import (
    AgentSerializer,
    ApprovalSerializer,
    ComputeAllocationSerializer,
    ComputePoolSerializer,
    CyrusSessionSerializer,
    GoalKPISerializer,
    GoalSerializer,
    ModelTierConfigSerializer,
    PoolUsageRecordSerializer,
    ScheduleRowSerializer,
    ScheduleSerializer,
)
from plane.api.views.base import BaseViewSet
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


class CyrusWorkspaceViewSet(BaseViewSet):
    permission_classes = [WorkspaceEntityPermission]
    workspace_lookup = "workspace"
    workspace_field_name = "workspace"

    def get_workspace(self):
        return get_object_or_404(Workspace, slug=self.kwargs["slug"])

    def get_queryset(self):
        queryset = super().get_queryset()
        return self.filter_queryset(queryset.filter(**{f"{self.workspace_lookup}__slug": self.kwargs["slug"]}))

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["workspace"] = self.get_workspace()
        context["workspace_slug"] = self.kwargs["slug"]
        return context

    def list(self, request, slug):
        queryset = self.get_queryset().order_by("-created_at")
        return self.paginate(
            request=request,
            queryset=queryset,
            on_results=lambda results: self.get_serializer(results, many=True).data,
            default_per_page=20,
        )

    def retrieve(self, request, slug, pk):
        serializer = self.get_serializer(self.get_object())
        return Response(serializer.data, status=status.HTTP_200_OK)

    def create(self, request, slug):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        save_kwargs = {}
        if self.workspace_field_name:
            save_kwargs[self.workspace_field_name] = self.get_workspace()
        serializer.save(**save_kwargs)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, slug, pk):
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    def destroy(self, request, slug, pk):
        instance = self.get_object()
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class GoalViewSet(CyrusWorkspaceViewSet):
    serializer_class = GoalSerializer
    model = Goal


class GoalKPIViewSet(CyrusWorkspaceViewSet):
    serializer_class = GoalKPISerializer
    model = GoalKPI
    workspace_lookup = "goal__workspace"
    workspace_field_name = None


class ComputePoolViewSet(CyrusWorkspaceViewSet):
    serializer_class = ComputePoolSerializer
    model = ComputePool


class AgentViewSet(CyrusWorkspaceViewSet):
    serializer_class = AgentSerializer
    model = Agent


class PoolUsageRecordViewSet(CyrusWorkspaceViewSet):
    serializer_class = PoolUsageRecordSerializer
    model = PoolUsageRecord
    workspace_lookup = "pool__workspace"
    workspace_field_name = None


class ScheduleViewSet(CyrusWorkspaceViewSet):
    serializer_class = ScheduleSerializer
    model = Schedule


class ScheduleRowViewSet(CyrusWorkspaceViewSet):
    serializer_class = ScheduleRowSerializer
    model = ScheduleRow
    workspace_lookup = "schedule__workspace"
    workspace_field_name = None


class ComputeAllocationViewSet(CyrusWorkspaceViewSet):
    serializer_class = ComputeAllocationSerializer
    model = ComputeAllocation


class CyrusSessionViewSet(CyrusWorkspaceViewSet):
    serializer_class = CyrusSessionSerializer
    model = CyrusSession
    workspace_lookup = "pool__workspace"
    workspace_field_name = None


class ApprovalViewSet(CyrusWorkspaceViewSet):
    serializer_class = ApprovalSerializer
    model = Approval
    workspace_lookup = "agent__workspace"
    workspace_field_name = None


class ModelTierConfigViewSet(CyrusWorkspaceViewSet):
    serializer_class = ModelTierConfigSerializer
    model = ModelTierConfig
