# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from .base import BaseModel


class GoalStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    PAUSED = "paused", "Paused"
    ARCHIVED = "archived", "Archived"


class Goal(BaseModel):
    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="goals")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=GoalStatus.choices, default=GoalStatus.ACTIVE)
    deadline = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "cyrus_goals"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "name"],
                condition=models.Q(deleted_at__isnull=True),
                name="cyrus_goal_unique_name_per_workspace",
            )
        ]
        indexes = [
            models.Index(fields=["workspace", "status"], name="cyrus_goal_ws_status_idx"),
            models.Index(fields=["deadline"], name="cyrus_goal_deadline_idx"),
        ]


class GoalKPI(BaseModel):
    goal = models.ForeignKey(Goal, on_delete=models.CASCADE, related_name="kpis")
    name = models.CharField(max_length=255)
    unit = models.CharField(max_length=50, blank=True)
    current_value = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    last_collected = models.DateTimeField(null=True, blank=True)
    history = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "cyrus_goal_kpis"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["goal", "last_collected"], name="cyrus_kpi_goal_collected_idx"),
        ]


class AgentType(models.TextChoices):
    OPENCLAW = "openclaw", "OpenClaw"
    CLAUDE_CODE = "claude_code", "Claude Code"
    CODEX = "codex", "Codex"
    GEMINI = "gemini", "Gemini"
    OPENCODE = "opencode", "OpenCode"
    ACP_NATIVE = "acp_native", "ACP Native"
    CUSTOM = "custom", "Custom"


class AgentStatus(models.TextChoices):
    ONLINE = "online", "Online"
    OFFLINE = "offline", "Offline"
    DEGRADED = "degraded", "Degraded"
    ERRORED = "errored", "Errored"


class PoolType(models.TextChoices):
    SUBSCRIPTION = "subscription", "Subscription"
    API_BILLING = "api_billing", "API Billing"


class PoolProvider(models.TextChoices):
    ANTHROPIC = "anthropic", "Anthropic"
    OPENAI = "openai", "OpenAI"
    GOOGLE = "google", "Google"
    OPENROUTER = "openrouter", "OpenRouter"
    CUSTOM = "custom", "Custom"


class ThrottleBehavior(models.TextChoices):
    QUEUE = "queue", "Queue"
    RETRY = "429_retry", "429 Retry"
    DEGRADED = "degraded", "Degraded"


class BudgetPeriod(models.TextChoices):
    DAILY = "daily", "Daily"
    WEEKLY = "weekly", "Weekly"
    MONTHLY = "monthly", "Monthly"


class ComputePool(BaseModel):
    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="compute_pools")
    name = models.CharField(max_length=255)
    pool_type = models.CharField(max_length=30, choices=PoolType.choices)
    provider = models.CharField(max_length=30, choices=PoolProvider.choices)
    tier = models.CharField(max_length=100, blank=True)
    rate_limits = models.JSONField(default=dict, blank=True)
    uncertainty_pct = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    throttle_behavior = models.CharField(max_length=20, choices=ThrottleBehavior.choices, blank=True)
    cost_per_input_token_usd = models.DecimalField(
        max_digits=10, decimal_places=6, null=True, blank=True,
        validators=[MinValueValidator(0)]
    )
    cost_per_output_token_usd = models.DecimalField(
        max_digits=10, decimal_places=6, null=True, blank=True,
        validators=[MinValueValidator(0)]
    )
    budget_limit_usd = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)]
    )
    budget_period = models.CharField(max_length=20, choices=BudgetPeriod.choices, default=BudgetPeriod.MONTHLY)

    class Meta:
        db_table = "cyrus_compute_pools"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "name"],
                condition=models.Q(deleted_at__isnull=True),
                name="cyrus_compute_pool_unique_name_per_workspace",
            ),
            models.CheckConstraint(
                check=models.Q(cost_per_input_token_usd__gte=0) | models.Q(cost_per_input_token_usd__isnull=True),
                name="cyrus_pool_input_cost_non_negative",
            ),
            models.CheckConstraint(
                check=models.Q(cost_per_output_token_usd__gte=0) | models.Q(cost_per_output_token_usd__isnull=True),
                name="cyrus_pool_output_cost_non_negative",
            ),
            models.CheckConstraint(
                check=models.Q(budget_limit_usd__gte=0) | models.Q(budget_limit_usd__isnull=True),
                name="cyrus_pool_budget_limit_non_negative",
            ),
        ]
        indexes = [
            models.Index(fields=["workspace", "pool_type"], name="cyrus_pool_workspace_type_idx"),
            models.Index(fields=["provider"], name="cyrus_pool_provider_idx"),
        ]


class Agent(BaseModel):
    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="agents")
    name = models.CharField(max_length=255)
    agent_type = models.CharField(max_length=30, choices=AgentType.choices)
    is_cyrus_agent = models.BooleanField(default=False)
    relay_url = models.URLField()
    relay_secret = models.CharField(max_length=255, blank=True)
    acpx_agent_name = models.CharField(max_length=255, blank=True)
    pool = models.ForeignKey(ComputePool, on_delete=models.PROTECT, related_name="agents")
    status = models.CharField(max_length=20, choices=AgentStatus.choices, default=AgentStatus.OFFLINE)
    last_heartbeat = models.DateTimeField(null=True, blank=True)
    config = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "cyrus_agents"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "name"],
                condition=models.Q(deleted_at__isnull=True),
                name="cyrus_agent_unique_name_per_workspace",
            )
        ]
        indexes = [
            models.Index(fields=["workspace", "status"], name="cyrus_agent_ws_status_idx"),
            models.Index(fields=["pool", "status"], name="cyrus_agent_pool_status_idx"),
            models.Index(fields=["last_heartbeat"], name="cyrus_agent_heartbeat_idx"),
        ]


class PoolUsageRecord(BaseModel):
    pool = models.ForeignKey(ComputePool, on_delete=models.CASCADE, related_name="usage_records")
    agent = models.ForeignKey(Agent, on_delete=models.PROTECT, related_name="usage_records")
    goal = models.ForeignKey(Goal, on_delete=models.SET_NULL, null=True, blank=True, related_name="usage_records")
    project = models.ForeignKey(
        "db.Project", on_delete=models.SET_NULL, null=True, blank=True, related_name="pool_usage_records"
    )
    work_item = models.ForeignKey(
        "db.Issue", on_delete=models.SET_NULL, null=True, blank=True, related_name="pool_usage_records"
    )
    session_id = models.CharField(max_length=255)
    timestamp = models.DateTimeField(auto_now_add=True)
    input_tokens = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    output_tokens = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    total_tokens = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    estimated_cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=0, validators=[MinValueValidator(0)])
    duration_seconds = models.FloatField(default=0, validators=[MinValueValidator(0)])
    model_name = models.CharField(max_length=100, blank=True)
    was_rate_limited = models.BooleanField(default=False)
    rate_limit_wait_seconds = models.FloatField(default=0, validators=[MinValueValidator(0)])

    class Meta:
        db_table = "cyrus_pool_usage_records"
        ordering = ("-timestamp", "-created_at")
        indexes = [
            models.Index(fields=["pool", "timestamp"], name="cyrus_usage_pool_ts_idx"),
            models.Index(fields=["agent", "timestamp"], name="cyrus_usage_agent_ts_idx"),
            models.Index(fields=["session_id"], name="cyrus_usage_session_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(input_tokens__gte=0),
                name="cyrus_usage_input_tokens_non_negative",
            ),
            models.CheckConstraint(
                check=models.Q(output_tokens__gte=0),
                name="cyrus_usage_output_tokens_non_negative",
            ),
            models.CheckConstraint(
                check=models.Q(total_tokens__gte=0),
                name="cyrus_usage_total_tokens_non_negative",
            ),
            models.CheckConstraint(
                check=models.Q(estimated_cost_usd__gte=0),
                name="cyrus_usage_cost_non_negative",
            ),
        ]


class RateLimitEvent(BaseModel):
    pool = models.ForeignKey(ComputePool, on_delete=models.CASCADE, related_name="rate_limit_events")
    agent = models.ForeignKey(Agent, on_delete=models.PROTECT, related_name="rate_limit_events")
    session = models.ForeignKey(
        "db.CyrusSession", on_delete=models.SET_NULL, null=True, blank=True, related_name="rate_limit_events"
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    status_code = models.PositiveIntegerField(default=429)
    retry_after_seconds = models.FloatField(default=0, validators=[MinValueValidator(0)])
    request_count = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    token_count = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "cyrus_rate_limit_events"
        ordering = ("-timestamp", "-created_at")
        indexes = [
            models.Index(fields=["pool", "timestamp"], name="cyrus_ratelimit_pool_ts_idx"),
            models.Index(fields=["agent", "timestamp"], name="cyrus_ratelimit_agent_ts_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(retry_after_seconds__gte=0),
                name="cyrus_rate_limit_retry_non_negative",
            ),
        ]


class Schedule(BaseModel):
    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="schedules")
    name = models.CharField(max_length=255)
    timezone = models.CharField(max_length=50, default="America/Chicago")

    class Meta:
        db_table = "cyrus_schedules"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "name"],
                condition=models.Q(deleted_at__isnull=True),
                name="cyrus_schedule_unique_name_per_workspace",
            )
        ]
        indexes = [
            models.Index(fields=["workspace"], name="cyrus_schedule_workspace_idx"),
        ]


class ScheduleRow(BaseModel):
    schedule = models.ForeignKey(Schedule, on_delete=models.CASCADE, related_name="rows")
    start_time = models.TimeField()
    end_time = models.TimeField()
    days = models.JSONField(default=list, blank=True)
    utilization_pct = models.IntegerField(default=50, validators=[MinValueValidator(0), MaxValueValidator(100)])
    priority_modifier = models.IntegerField(default=0, validators=[MinValueValidator(-5), MaxValueValidator(5)])

    class Meta:
        db_table = "cyrus_schedule_rows"
        ordering = ("created_at",)
        indexes = [
            models.Index(fields=["schedule"], name="cyrus_schedrow_schedule_idx"),
        ]


class ComputeAllocation(BaseModel):
    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="compute_allocations")
    goal = models.ForeignKey(Goal, on_delete=models.SET_NULL, null=True, blank=True, related_name="allocations")
    project = models.ForeignKey(
        "db.Project", on_delete=models.SET_NULL, null=True, blank=True, related_name="compute_allocations"
    )
    agent = models.ForeignKey(Agent, on_delete=models.PROTECT, related_name="allocations")
    pool = models.ForeignKey(ComputePool, on_delete=models.PROTECT, related_name="allocations")
    schedule = models.ForeignKey(Schedule, on_delete=models.PROTECT, related_name="allocations")
    priority = models.IntegerField(default=5, validators=[MinValueValidator(1), MaxValueValidator(10)])
    last_dispatched_at = models.DateTimeField(null=True, blank=True)
    cooldown_minutes = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    consecutive_failures = models.IntegerField(default=0, validators=[MinValueValidator(0)])

    class Meta:
        db_table = "cyrus_compute_allocations"
        ordering = ("priority", "-created_at")
        constraints = [
            models.CheckConstraint(
                check=models.Q(consecutive_failures__gte=0),
                name="cyrus_allocation_failures_non_negative",
            ),
        ]
        indexes = [
            models.Index(fields=["workspace", "schedule"], name="cyrus_alloc_ws_sched_idx"),
            models.Index(fields=["pool", "priority"], name="cyrus_alloc_pool_priority_idx"),
            models.Index(fields=["last_dispatched_at"], name="cyrus_alloc_dispatched_idx"),
        ]


class SessionStatus(models.TextChoices):
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"
    RATE_LIMITED = "rate_limited", "Rate Limited"


class CyrusSession(BaseModel):
    agent = models.ForeignKey(Agent, on_delete=models.PROTECT, related_name="sessions")
    goal = models.ForeignKey(Goal, on_delete=models.SET_NULL, null=True, blank=True, related_name="sessions")
    project = models.ForeignKey("db.Project", on_delete=models.SET_NULL, null=True, blank=True, related_name="sessions")
    work_item = models.ForeignKey("db.Issue", on_delete=models.SET_NULL, null=True, blank=True, related_name="sessions")
    pool = models.ForeignKey(ComputePool, on_delete=models.PROTECT, related_name="sessions")
    acpx_session_id = models.CharField(max_length=255, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=SessionStatus.choices, default=SessionStatus.RUNNING)
    event_log = models.JSONField(default=list, blank=True)
    summary = models.TextField(blank=True)
    outcome = models.JSONField(default=dict, blank=True)
    total_tokens = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    input_tokens = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    output_tokens = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    estimated_cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=0, validators=[MinValueValidator(0)])
    duration_seconds = models.FloatField(default=0, validators=[MinValueValidator(0)])
    model_name = models.CharField(max_length=100, blank=True)
    was_rate_limited = models.BooleanField(default=False)
    rate_limit_wait_seconds = models.FloatField(default=0, validators=[MinValueValidator(0)])
    langfuse_trace_id = models.CharField(max_length=255, blank=True)
    langfuse_trace_url = models.URLField(blank=True)

    class Meta:
        db_table = "cyrus_sessions"
        ordering = ("-started_at", "-created_at")
        indexes = [
            models.Index(fields=["agent", "status"], name="cyrus_sess_agent_status_idx"),
            models.Index(fields=["pool", "started_at"], name="cyrus_sess_pool_started_idx"),
            models.Index(fields=["status", "started_at"], name="cyrus_sess_status_started_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(total_tokens__gte=0),
                name="cyrus_session_total_tokens_non_negative",
            ),
            models.CheckConstraint(
                check=models.Q(input_tokens__gte=0),
                name="cyrus_session_input_tokens_non_negative",
            ),
            models.CheckConstraint(
                check=models.Q(output_tokens__gte=0),
                name="cyrus_session_output_tokens_non_negative",
            ),
            models.CheckConstraint(
                check=models.Q(estimated_cost_usd__gte=0),
                name="cyrus_session_cost_non_negative",
            ),
        ]


class ApprovalStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class Approval(BaseModel):
    goal = models.ForeignKey(Goal, on_delete=models.SET_NULL, null=True, blank=True, related_name="approvals")
    project = models.ForeignKey(
        "db.Project", on_delete=models.SET_NULL, null=True, blank=True, related_name="approvals"
    )
    agent = models.ForeignKey(Agent, on_delete=models.PROTECT, related_name="approvals")
    threshold_matched = models.TextField()
    status = models.CharField(max_length=20, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING)
    requested_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "cyrus_approvals"
        ordering = ("-requested_at", "-created_at")
        indexes = [
            models.Index(fields=["status", "requested_at"], name="cyrus_appr_status_req_idx"),
            models.Index(fields=["agent", "status"], name="cyrus_appr_agent_status_idx"),
        ]


class ModelTier(models.TextChoices):
    HIGH = "high", "High"
    MEDIUM = "medium", "Medium"
    LOW = "low", "Low"


class ModelTierConfig(BaseModel):
    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="model_tier_configs")
    tier = models.CharField(max_length=20, choices=ModelTier.choices)
    provider = models.CharField(max_length=100)
    model_name = models.CharField(max_length=100)

    class Meta:
        db_table = "cyrus_model_tier_configs"
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "tier"],
                condition=models.Q(deleted_at__isnull=True),
                name="cyrus_model_tier_unique_workspace_tier",
            )
        ]


class SchedulingDecision(BaseModel):
    """Audit log for scheduling engine decisions"""
    allocation = models.ForeignKey(ComputeAllocation, on_delete=models.CASCADE, related_name="scheduling_decisions")
    decision = models.CharField(max_length=20)  # "dispatched", "skipped", "blocked"
    reasons = models.JSONField(default=list, blank=True)
    pool_utilization = models.FloatField(default=0, validators=[MinValueValidator(0)])
    budget_remaining_usd = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)]
    )
    intensity = models.CharField(max_length=20, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "cyrus_scheduling_decisions"
        ordering = ("-timestamp",)
        indexes = [
            models.Index(fields=["allocation", "timestamp"], name="cyrus_scheddec_alloc_ts_idx"),
            models.Index(fields=["decision", "timestamp"], name="cyrus_scheddec_dec_ts_idx"),
        ]


class ScheduleTemplate(BaseModel):
    """Pre-defined schedule patterns for quick setup"""
    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="schedule_templates")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    pattern_type = models.CharField(max_length=50)  # "business_hours", "off_peak", "24_7", "custom"
    timezone = models.CharField(max_length=50, default="UTC")
    rows_config = models.JSONField(default=list, blank=True)  # List of row configurations
    is_system = models.BooleanField(default=False)  # System templates can't be modified

    class Meta:
        db_table = "cyrus_schedule_templates"
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "name"],
                condition=models.Q(deleted_at__isnull=True),
                name="cyrus_schedule_template_unique_name_per_workspace",
            )
        ]
        indexes = [
            models.Index(fields=["workspace", "pattern_type"], name="cyrus_schedtpl_ws_pattern_idx"),
            models.Index(fields=["is_system"], name="cyrus_schedtpl_system_idx"),
        ]
