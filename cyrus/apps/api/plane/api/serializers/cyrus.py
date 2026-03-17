# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from rest_framework import serializers

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

from .base import BaseSerializer


class WorkspaceScopedSerializer(BaseSerializer):
    workspace_error_message = "Related records must belong to the current workspace."

    def get_workspace(self):
        workspace = self.context.get("workspace")
        if workspace is not None:
            return workspace

        slug = self.context.get("workspace_slug")
        if slug:
            workspace = Workspace.objects.filter(slug=slug).first()
            if workspace is not None:
                return workspace

        raise serializers.ValidationError({"workspace": "Workspace context is required."})

    def validate_workspace_relation(self, data, field_name, workspace=None, attr="workspace_id"):
        workspace = workspace or self.get_workspace()
        instance = data.get(field_name)
        if instance is not None and getattr(instance, attr, None) != workspace.id:
            raise serializers.ValidationError({field_name: self.workspace_error_message})


class GoalSerializer(WorkspaceScopedSerializer):
    class Meta:
        model = Goal
        fields = "__all__"
        read_only_fields = ["workspace", "created_by", "updated_by", "deleted_at"]


class GoalKPISerializer(WorkspaceScopedSerializer):
    class Meta:
        model = GoalKPI
        fields = "__all__"
        read_only_fields = ["created_by", "updated_by", "deleted_at"]

    def validate(self, data):
        data = super().validate(data)
        self.validate_workspace_relation(data, "goal", self.get_workspace(), "workspace_id")
        return data


class ComputePoolSerializer(WorkspaceScopedSerializer):
    class Meta:
        model = ComputePool
        fields = "__all__"
        read_only_fields = ["workspace", "created_by", "updated_by", "deleted_at"]


class AgentSerializer(WorkspaceScopedSerializer):
    class Meta:
        model = Agent
        fields = "__all__"
        read_only_fields = ["workspace", "created_by", "updated_by", "deleted_at"]

    def validate(self, data):
        data = super().validate(data)
        self.validate_workspace_relation(data, "pool", self.get_workspace())
        return data


class PoolUsageRecordSerializer(WorkspaceScopedSerializer):
    class Meta:
        model = PoolUsageRecord
        fields = "__all__"
        read_only_fields = ["created_by", "updated_by", "deleted_at", "timestamp"]

    def validate(self, data):
        data = super().validate(data)
        workspace = self.get_workspace()
        self.validate_workspace_relation(data, "pool", workspace)
        self.validate_workspace_relation(data, "agent", workspace)
        self.validate_workspace_relation(data, "goal", workspace)
        self.validate_workspace_relation(data, "project", workspace)

        work_item = data.get("work_item")
        if work_item is not None and work_item.workspace_id != workspace.id:
            raise serializers.ValidationError({"work_item": self.workspace_error_message})

        return data


class ScheduleSerializer(WorkspaceScopedSerializer):
    class Meta:
        model = Schedule
        fields = "__all__"
        read_only_fields = ["workspace", "created_by", "updated_by", "deleted_at"]


class ScheduleRowSerializer(WorkspaceScopedSerializer):
    class Meta:
        model = ScheduleRow
        fields = "__all__"
        read_only_fields = ["created_by", "updated_by", "deleted_at"]

    def validate(self, data):
        data = super().validate(data)
        self.validate_workspace_relation(data, "schedule", self.get_workspace(), "workspace_id")
        return data


class ComputeAllocationSerializer(WorkspaceScopedSerializer):
    class Meta:
        model = ComputeAllocation
        fields = "__all__"
        read_only_fields = ["workspace", "created_by", "updated_by", "deleted_at"]

    def validate(self, data):
        data = super().validate(data)
        workspace = self.get_workspace()
        self.validate_workspace_relation(data, "goal", workspace)
        self.validate_workspace_relation(data, "project", workspace)
        self.validate_workspace_relation(data, "agent", workspace)
        self.validate_workspace_relation(data, "pool", workspace)
        self.validate_workspace_relation(data, "schedule", workspace)
        return data


class CyrusSessionSerializer(WorkspaceScopedSerializer):
    class Meta:
        model = CyrusSession
        fields = "__all__"
        read_only_fields = ["created_by", "updated_by", "deleted_at", "started_at"]

    def validate(self, data):
        data = super().validate(data)
        workspace = self.get_workspace()
        self.validate_workspace_relation(data, "agent", workspace)
        self.validate_workspace_relation(data, "goal", workspace)
        self.validate_workspace_relation(data, "project", workspace)
        self.validate_workspace_relation(data, "pool", workspace)

        work_item = data.get("work_item")
        if work_item is not None and work_item.workspace_id != workspace.id:
            raise serializers.ValidationError({"work_item": self.workspace_error_message})

        return data


class ApprovalSerializer(WorkspaceScopedSerializer):
    class Meta:
        model = Approval
        fields = "__all__"
        read_only_fields = ["created_by", "updated_by", "deleted_at", "requested_at"]

    def validate(self, data):
        data = super().validate(data)
        workspace = self.get_workspace()
        self.validate_workspace_relation(data, "goal", workspace)
        self.validate_workspace_relation(data, "project", workspace)
        self.validate_workspace_relation(data, "agent", workspace)
        return data


class ModelTierConfigSerializer(WorkspaceScopedSerializer):
    class Meta:
        model = ModelTierConfig
        fields = "__all__"
        read_only_fields = ["workspace", "created_by", "updated_by", "deleted_at"]


def validate_project_goal(data, workspace_id):
    goal = data.get("goal")
    if goal is not None and goal.workspace_id != workspace_id:
        raise serializers.ValidationError("Goal should belong to the workspace")
    return data
