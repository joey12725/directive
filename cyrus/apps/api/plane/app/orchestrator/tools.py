from __future__ import annotations

import json
import logging
import os
from html import escape
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

import requests
from bs4 import BeautifulSoup
from django.db.models import Case, Count, IntegerField, Q, Sum, Value, When
from django.utils import timezone

from plane.app.agents.dispatcher import ACPXDispatcher
from plane.app.metering.tracker import ComputeTracker
from plane.db.models import (
    Agent,
    Approval,
    ComputePool,
    CyrusSession,
    Cycle,
    CycleIssue,
    Goal,
    GoalKPI,
    Issue,
    IssueAssignee,
    IssueBlocker,
    IssueComment,
    IssueLabel,
    IssueLink,
    IssueRelation,
    Label,
    Module,
    ModuleIssue,
    Notification,
    Page,
    PoolUsageRecord,
    Project,
    State,
    User,
    Workspace,
)
from plane.db.models.cyrus import ApprovalStatus, SessionStatus
from plane.db.models.issue import IssueRelationChoices
from plane.db.models.module import ModuleStatus
from plane.db.models.state import StateGroup
logger = logging.getLogger(__name__)


class CyrusToolError(Exception):
    pass


@dataclass(slots=True)
class Context:
    workspace: Workspace | None = None
    project: Project | None = None
    goal: Goal | None = None
    agent: Agent | None = None
    user: User | None = None


def _parse_datetime(value: str | None) -> Any:
    if not value:
        return None
    parsed = timezone.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.utc)
    return parsed


def _markdown_to_html(text: str | None) -> str:
    text = (text or "").strip()
    if not text:
        return "<p></p>"
    paragraphs = [f"<p>{escape(block).replace(chr(10), '<br/>')}</p>" for block in text.split("\n\n") if block.strip()]
    return "".join(paragraphs) or "<p></p>"


def _html_to_markdown(html: str | None) -> str:
    if not html:
        return ""
    return BeautifulSoup(html, "html.parser").get_text("\n").strip()


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _resolve_context(args: dict[str, Any]) -> Context:
    workspace = None
    project = None
    goal = None
    agent = None
    user = None

    if workspace_id := args.get("workspace_id"):
        workspace = Workspace.objects.filter(id=workspace_id, deleted_at__isnull=True).first()
    elif workspace_slug := args.get("workspace_slug"):
        workspace = Workspace.objects.filter(slug=workspace_slug, deleted_at__isnull=True).first()

    if project_id := args.get("project_id"):
        project = Project.objects.select_related("workspace", "goal").filter(
            id=project_id,
            deleted_at__isnull=True,
        ).first()
        if project and workspace is None:
            workspace = project.workspace
    elif project_identifier := args.get("project_identifier"):
        if workspace is None:
            raise CyrusToolError("project_identifier requires workspace context")
        project = Project.objects.select_related("workspace", "goal").filter(
            workspace=workspace,
            identifier=project_identifier.upper(),
            deleted_at__isnull=True,
        ).first()

    if goal_id := args.get("goal_id"):
        goal = Goal.objects.filter(id=goal_id, deleted_at__isnull=True).first()
        if goal and workspace is None:
            workspace = goal.workspace
    elif project and project.goal_id:
        goal = project.goal

    if agent_id := args.get("agent_id"):
        agent = Agent.objects.select_related("pool", "workspace").filter(id=agent_id, deleted_at__isnull=True).first()
    elif args.get("is_cyrus_agent") and workspace is not None:
        agent = Agent.objects.select_related("pool", "workspace").filter(
            workspace=workspace,
            is_cyrus_agent=True,
            deleted_at__isnull=True,
        ).order_by("-last_heartbeat", "created_at").first()

    if user_id := args.get("user_id"):
        user = User.objects.filter(id=user_id).first()
    elif workspace is not None:
        user = workspace.owner

    return Context(workspace=workspace, project=project, goal=goal, agent=agent, user=user)


def _require_workspace(ctx: Context) -> Workspace:
    if ctx.workspace is None:
        raise CyrusToolError("workspace_id or workspace_slug is required")
    return ctx.workspace


def _require_project(ctx: Context) -> Project:
    if ctx.project is None:
        raise CyrusToolError("project_id or project_identifier is required")
    return ctx.project


def _require_issue(issue_id: str) -> Issue:
    issue = Issue.objects.select_related("project", "workspace", "state").filter(
        id=issue_id,
        deleted_at__isnull=True,
    ).first()
    if issue is None:
        raise CyrusToolError(f"Issue {issue_id} was not found")
    return issue


def _ensure_agent(ctx: Context) -> Agent:
    if ctx.agent is not None:
        return ctx.agent
    workspace = _require_workspace(ctx)
    agent = Agent.objects.select_related("pool", "workspace").filter(
        workspace=workspace,
        is_cyrus_agent=True,
        deleted_at__isnull=True,
    ).order_by("-last_heartbeat", "created_at").first()
    if agent is None:
        raise CyrusToolError(f"No Cyrus agent is registered for workspace {workspace.slug}")
    ctx.agent = agent
    return agent


def _pick_dispatch_issue(ctx: Context, args: dict[str, Any]) -> Issue:
    if issue_id := args.get("work_item_id"):
        return _require_issue(issue_id)
    project = ctx.project
    if project is None:
        workspace = _require_workspace(ctx)
        project = Project.objects.filter(workspace=workspace, deleted_at__isnull=True).order_by("created_at").first()
    if project is None:
        raise CyrusToolError("No project is available for dispatch")
    issue = Issue.objects.filter(
        project=project,
        deleted_at__isnull=True,
        archived_at__isnull=True,
    ).exclude(
        state__group__in=[StateGroup.COMPLETED.value, StateGroup.CANCELLED.value]
    ).order_by("created_at").first()
    if issue is None:
        state = State.objects.filter(project=project, group=StateGroup.BACKLOG.value).order_by("sequence").first()
        state = state or State.objects.filter(project=project).order_by("sequence").first()
        if state is None:
            raise CyrusToolError(f"Project {project.id} has no workflow states")
        issue = Issue.objects.create(
            project=project,
            workspace=project.workspace,
            state=state,
            name="[Cyrus] Operational control session",
            description_html=_markdown_to_html("Operational issue used by the Cyrus Agent for autonomous PM loops."),
        )
    ctx.project = project
    return issue


def _pick_state(project: Project, *, state_id: str | None = None, group: str | None = None, name: str | None = None) -> State:
    queryset = State.all_state_objects.filter(project=project, deleted_at__isnull=True)
    if state_id:
        state = queryset.filter(id=state_id).first()
        if state:
            return state
    if name:
        state = queryset.filter(name__iexact=name).order_by("sequence").first()
        if state:
            return state
    if group:
        state = queryset.filter(group=group).order_by("sequence").first()
        if state:
            return state
    raise CyrusToolError(f"Unable to resolve a state for project {project.identifier}")


def _serialize_issue(issue: Issue) -> dict[str, Any]:
    return {
        "id": str(issue.id),
        "sequence_id": issue.sequence_id,
        "identifier": f"{issue.project.identifier}-{issue.sequence_id}",
        "name": issue.name,
        "priority": issue.priority,
        "state": issue.state.name if issue.state_id else None,
        "state_group": issue.state.group if issue.state_id else None,
        "start_date": issue.start_date.isoformat() if issue.start_date else None,
        "target_date": issue.target_date.isoformat() if issue.target_date else None,
        "description": _html_to_markdown(issue.description_html),
    }


def _upsert_comment(issue: Issue, body: str, actor: User | None) -> IssueComment:
    return IssueComment.objects.create(
        issue=issue,
        project=issue.project,
        workspace=issue.workspace,
        actor=actor,
        comment_html=_markdown_to_html(body),
        comment_json={},
    )


def _notify_user(*, workspace: Workspace, receiver: User, title: str, message: str, entity_name: str, entity_identifier: Any = None, project: Project | None = None, triggered_by: User | None = None, data: dict[str, Any] | None = None) -> Notification:
    return Notification.objects.create(
        workspace=workspace,
        project=project,
        receiver=receiver,
        triggered_by=triggered_by,
        title=title,
        message={"text": message},
        message_html=_markdown_to_html(message),
        sender="cyrus:orchestrator",
        entity_name=entity_name,
        entity_identifier=entity_identifier,
        data=data or {},
    )


def _send_apprise_notification(title: str, body: str) -> dict[str, Any]:
    webhook = os.environ.get("CYRUS_APPRISE_WEBHOOK") or os.environ.get("APPRISE_WEBHOOK_URL")
    if not webhook:
        return {"sent": False, "reason": "webhook_not_configured"}
    try:
        response = requests.post(webhook, json={"title": title, "body": body, "format": "markdown"}, timeout=15)
        response.raise_for_status()
        return {"sent": True, "status_code": response.status_code}
    except requests.RequestException as exc:
        logger.warning("Apprise notification failed", extra={"error": str(exc)})
        return {"sent": False, "reason": str(exc)}


def _relay_post(agent: Agent, endpoint_candidates: list[str], payload: dict[str, Any], *, timeout: int = 60) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {agent.relay_secret}"}
    errors: list[str] = []
    for endpoint in endpoint_candidates:
        url = f"{agent.relay_url.rstrip('/')}/{endpoint.lstrip('/')}"
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if response.status_code == 404:
                errors.append(f"{endpoint}:404")
                continue
            response.raise_for_status()
            if "application/json" in response.headers.get("Content-Type", ""):
                return {"endpoint": endpoint, "payload": response.json()}
            return {"endpoint": endpoint, "payload": {"text": response.text}}
        except requests.Timeout:
            raise CyrusToolError(f"Relay request to {endpoint} timed out after {timeout}s")
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 429:
                retry_after = exc.response.headers.get("Retry-After", "0")
                raise CyrusToolError(f"Relay rate limited the request; retry_after={retry_after}")
            errors.append(f"{endpoint}:{exc}")
        except requests.RequestException as exc:
            errors.append(f"{endpoint}:{exc}")
    raise CyrusToolError("Relay interaction failed: " + "; ".join(errors))


def get_registered_agents(args: dict[str, Any]) -> dict[str, Any]:
    ctx = _resolve_context(args)
    workspace = _require_workspace(ctx)
    agents = Agent.objects.filter(workspace=workspace, deleted_at__isnull=True).select_related("pool")
    active_sessions = CyrusSession.objects.filter(status=SessionStatus.RUNNING).values("agent_id").annotate(total=Count("id"))
    running_by_agent = {row["agent_id"]: row["total"] for row in active_sessions}
    data = [
        {
            "id": str(agent.id),
            "name": agent.name,
            "status": agent.status,
            "is_cyrus_agent": agent.is_cyrus_agent,
            "pool": {"id": str(agent.pool_id), "name": agent.pool.name, "provider": agent.pool.provider},
            "last_heartbeat": agent.last_heartbeat.isoformat() if agent.last_heartbeat else None,
            "active_assignments": running_by_agent.get(agent.id, 0),
        }
        for agent in agents
    ]
    pools = [
        {"id": str(pool.id), "name": pool.name, "provider": pool.provider, "budget": ComputeTracker(pool=pool).get_pool_budget_state()}
        for pool in ComputePool.objects.filter(workspace=workspace, deleted_at__isnull=True)
    ]
    return {"workspace": workspace.slug, "agents": data, "pools": pools}


def get_system_settings(args: dict[str, Any]) -> dict[str, Any]:
    ctx = _resolve_context(args)
    return _ensure_agent(ctx).config.get("system_settings", {})


def update_system_settings(args: dict[str, Any]) -> dict[str, Any]:
    ctx = _resolve_context(args)
    agent = _ensure_agent(ctx)
    patch = args.get("settings") or {}
    if not isinstance(patch, dict):
        raise CyrusToolError("settings must be an object")
    config = dict(agent.config or {})
    settings_blob = dict(config.get("system_settings") or {})
    settings_blob.update(patch)
    config["system_settings"] = settings_blob
    agent.config = config
    agent.save(update_fields=["config", "updated_at"])
    return settings_blob


def configure_project_workflow(args: dict[str, Any]) -> dict[str, Any]:
    ctx = _resolve_context(args)
    project = _require_project(ctx)
    created_states: list[str] = []
    updated_states: list[str] = []
    for state_data in args.get("states", []):
        state, created = State.all_state_objects.update_or_create(
            project=project,
            name=state_data["name"],
            defaults={
                "workspace": project.workspace,
                "description": state_data.get("description", ""),
                "color": state_data.get("color", "#60646C"),
                "group": state_data.get("group", StateGroup.BACKLOG.value),
                "default": state_data.get("default", False),
                "sequence": state_data.get("sequence", 65535),
                "is_triage": state_data.get("group") == StateGroup.TRIAGE.value,
            },
        )
        (created_states if created else updated_states).append(state.name)
    labels = []
    for label_data in args.get("labels", []):
        label, _ = Label.objects.update_or_create(
            workspace=project.workspace,
            project=project,
            name=label_data["name"],
            defaults={"description": label_data.get("description", ""), "color": label_data.get("color", "#4E8CFF")},
        )
        labels.append(label.name)
    return {"project": project.identifier, "created_states": created_states, "updated_states": updated_states, "labels": labels}


def get_markdown_view(args: dict[str, Any]) -> dict[str, Any]:
    ctx = _resolve_context(args)
    project = _require_project(ctx)
    layout = str(args.get("layout", "list")).lower()
    issues = Issue.issue_objects.filter(project=project).select_related("state").prefetch_related("labels", "assignees").order_by("state__sequence", "sort_order", "created_at")
    rows = []
    for issue in issues:
        rows.append(
            {
                "id": f"{project.identifier}-{issue.sequence_id}",
                "name": issue.name,
                "state": issue.state.name if issue.state_id else "Unscheduled",
                "priority": issue.priority,
                "target": issue.target_date.isoformat() if issue.target_date else "",
                "assignees": ", ".join(issue.assignees.values_list("display_name", flat=True)) or "-",
                "labels": ", ".join(issue.labels.values_list("name", flat=True)) or "-",
            }
        )
    if layout == "board":
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(row["state"], []).append(row)
        lines = []
        for state_name, items in grouped.items():
            lines.append(f"## {state_name}")
            lines.extend([f"- {item['id']}: {item['name']} ({item['priority']})" for item in items])
            lines.append("")
        return {"layout": layout, "markdown": "\n".join(lines).strip()}
    header = "| Key | Title | State | Priority | Target | Assignees | Labels |"
    divider = "| --- | --- | --- | --- | --- | --- | --- |"
    lines = [header, divider]
    for row in rows:
        lines.append(f"| {row['id']} | {row['name']} | {row['state']} | {row['priority']} | {row['target']} | {row['assignees']} | {row['labels']} |")
    return {"layout": layout, "markdown": "\n".join(lines)}


def search_workspace(args: dict[str, Any]) -> dict[str, Any]:
    query = (args.get("query") or "").strip()
    if not query:
        raise CyrusToolError("query is required")
    ctx = _resolve_context(args)
    workspace = _require_workspace(ctx)
    terms = [term for term in query.split() if term]
    score_cases = [When(name__icontains=term, then=Value(3)) for term in terms] + [When(description_stripped__icontains=term, then=Value(2)) for term in terms]
    issue_results = Issue.issue_objects.filter(workspace=workspace).annotate(score=Sum(Case(*score_cases, default=Value(0), output_field=IntegerField()))).filter(Q(name__icontains=query) | Q(description_stripped__icontains=query)).select_related("project", "state").order_by("-score", "-updated_at")[: args.get("limit", 10)]
    page_results = Page.objects.filter(workspace=workspace, archived_at__isnull=True).filter(Q(name__icontains=query) | Q(description_stripped__icontains=query)).order_by("-updated_at")[: args.get("limit", 10)]
    return {
        "issues": [{"id": str(issue.id), "key": f"{issue.project.identifier}-{issue.sequence_id}", "name": issue.name, "state": issue.state.name if issue.state_id else None, "score": issue.score or 0} for issue in issue_results],
        "wiki_pages": [{"id": str(page.id), "name": page.name} for page in page_results],
    }


def check_story_duplicates(args: dict[str, Any]) -> dict[str, Any]:
    ctx = _resolve_context(args)
    project = _require_project(ctx)
    title = (args.get("title") or "").strip()
    description = (args.get("description") or "").strip()
    if not title:
        raise CyrusToolError("title is required")
    queryset = Issue.issue_objects.filter(project=project).annotate(duplicate_score=Case(When(name__iexact=title, then=Value(100)), When(name__icontains=title, then=Value(75)), When(description_stripped__icontains=title, then=Value(40)), When(description_stripped__icontains=description[:120], then=Value(25)), default=Value(0), output_field=IntegerField())).filter(duplicate_score__gt=0).order_by("-duplicate_score", "-updated_at")[:10]
    return {"duplicates": [{**_serialize_issue(issue), "duplicate_score": issue.duplicate_score} for issue in queryset]}


def manage_goals_and_projects(args: dict[str, Any]) -> dict[str, Any]:
    ctx = _resolve_context(args)
    workspace = _require_workspace(ctx)
    results: dict[str, Any] = {"workspace": workspace.slug}
    if goal_payload := args.get("goal"):
        goal, _ = Goal.objects.update_or_create(workspace=workspace, name=goal_payload["name"], defaults={"description": goal_payload.get("description", ""), "status": goal_payload.get("status", "active"), "deadline": _parse_datetime(goal_payload.get("deadline"))})
        results["goal"] = {"id": str(goal.id), "name": goal.name, "status": goal.status}
    if project_payload := args.get("project"):
        identifier = project_payload["identifier"].upper()
        goal_id = project_payload.get("goal_id") or (results.get("goal") or {}).get("id")
        project, _ = Project.objects.update_or_create(workspace=workspace, identifier=identifier, defaults={"name": project_payload["name"], "description": project_payload.get("description", ""), "network": project_payload.get("network", 0), "project_lead": ctx.user, "default_assignee": ctx.user, "workspace_path": project_payload.get("workspace_path", ""), "goal_id": goal_id, "cycle_duration": project_payload.get("cycle_duration", Project.CycleDuration.FIVE_HOURS)})
        results["project"] = {"id": str(project.id), "identifier": project.identifier, "name": project.name}
    return results


def manage_cycles_and_modules(args: dict[str, Any]) -> dict[str, Any]:
    ctx = _resolve_context(args)
    project = _require_project(ctx)
    results: dict[str, Any] = {"project": project.identifier}
    if cycle_payload := args.get("cycle"):
        cycle, _ = Cycle.objects.update_or_create(project=project, workspace=project.workspace, name=cycle_payload["name"], defaults={"description": cycle_payload.get("description", ""), "owned_by": ctx.user or project.created_by, "start_date": _parse_datetime(cycle_payload.get("start_date")), "end_date": _parse_datetime(cycle_payload.get("end_date")), "timezone": cycle_payload.get("timezone", project.timezone)})
        for issue_id in cycle_payload.get("issue_ids", []):
            CycleIssue.objects.get_or_create(project=project, workspace=project.workspace, cycle=cycle, issue=_require_issue(issue_id))
        results["cycle"] = {"id": str(cycle.id), "name": cycle.name}
    if module_payload := args.get("module"):
        module, _ = Module.objects.update_or_create(project=project, workspace=project.workspace, name=module_payload["name"], defaults={"description": module_payload.get("description", ""), "status": module_payload.get("status", ModuleStatus.PLANNED), "lead": ctx.user or project.project_lead})
        for issue_id in module_payload.get("issue_ids", []):
            ModuleIssue.objects.get_or_create(project=project, workspace=project.workspace, module=module, issue=_require_issue(issue_id))
        results["module"] = {"id": str(module.id), "name": module.name}
    return results


def define_kpi_schema(args: dict[str, Any]) -> dict[str, Any]:
    ctx = _resolve_context(args)
    if ctx.goal is None:
        raise CyrusToolError("goal_id is required")
    created = []
    for metric in args.get("metrics", []):
        kpi, _ = GoalKPI.objects.update_or_create(goal=ctx.goal, name=metric["name"], defaults={"unit": metric.get("unit", "")})
        created.append({"id": str(kpi.id), "name": kpi.name, "unit": kpi.unit})
    return {"goal": ctx.goal.name, "metrics": created}


def log_kpi_datapoint(args: dict[str, Any]) -> dict[str, Any]:
    kpi = GoalKPI.objects.filter(id=args.get("kpi_id")).first()
    if kpi is None:
        raise CyrusToolError("kpi_id is required")
    value = Decimal(str(args.get("value")))
    history = list(kpi.history or [])
    history.append({"value": str(value), "timestamp": timezone.now().isoformat(), "source": args.get("source", "cyrus_tool")})
    kpi.current_value = value
    kpi.last_collected = timezone.now()
    kpi.history = history[-500:]
    kpi.save(update_fields=["current_value", "last_collected", "history", "updated_at"])
    return {"kpi_id": str(kpi.id), "current_value": str(kpi.current_value)}


def get_activity_data_for_summary(args: dict[str, Any]) -> dict[str, Any]:
    ctx = _resolve_context(args)
    workspace = _require_workspace(ctx)
    since = _parse_datetime(args.get("since")) or timezone.now() - timedelta(days=int(args.get("days", 7)))
    until = _parse_datetime(args.get("until")) or timezone.now()
    completed = Issue.issue_objects.filter(workspace=workspace, completed_at__gte=since, completed_at__lte=until).select_related("project", "state")[:200]
    sessions = CyrusSession.objects.filter(agent__workspace=workspace, started_at__gte=since, started_at__lte=until).select_related("agent", "project", "work_item", "pool")[:200]
    usage = PoolUsageRecord.objects.filter(pool__workspace=workspace, timestamp__gte=since, timestamp__lte=until)[:200]
    lines = [f"# Activity Summary Input\n", f"Window: {since.isoformat()} -> {until.isoformat()}\n", "## Completed Stories"]
    for issue in completed:
        lines.append(f"- {issue.project.identifier}-{issue.sequence_id}: {issue.name} [{issue.state.name if issue.state_id else 'n/a'}]")
    lines.append("\n## Sessions")
    for session in sessions:
        lines.append(f"- session={session.id} agent={session.agent.name} project={getattr(session.project, 'identifier', 'n/a')} work_item={getattr(session.work_item, 'name', 'n/a')} status={session.status} tokens={session.total_tokens} cost={session.estimated_cost_usd}")
    lines.append("\n## Metering Records")
    for record in usage:
        lines.append(f"- pool={record.pool.name} session={record.session_id} tokens={record.total_tokens} cost={record.estimated_cost_usd} rate_limited={record.was_rate_limited}")
    return {"markdown": "\n".join(lines)}


def create_work_item(args: dict[str, Any]) -> dict[str, Any]:
    ctx = _resolve_context(args)
    project = _require_project(ctx)
    state = _pick_state(project, state_id=args.get("state_id"), group=args.get("state_group") or StateGroup.BACKLOG.value)
    issue = Issue.objects.create(project=project, workspace=project.workspace, state=state, name=args["title"], priority=args.get("priority", "medium"), start_date=args.get("start_date"), target_date=args.get("target_date"), description_html=_markdown_to_html(args.get("description")), description_json={})
    for label_name in args.get("labels", []):
        label, _ = Label.objects.get_or_create(workspace=project.workspace, project=project, name=label_name, defaults={"color": "#4E8CFF"})
        IssueLabel.objects.get_or_create(issue=issue, label=label, project=project, workspace=project.workspace)
    return _serialize_issue(issue)


def update_work_item(args: dict[str, Any]) -> dict[str, Any]:
    issue = _require_issue(args["issue_id"])
    if "title" in args:
        issue.name = args["title"]
    if "description" in args:
        issue.description_html = _markdown_to_html(args["description"])
        issue.description_json = {}
    if "priority" in args:
        issue.priority = args["priority"]
    if "start_date" in args:
        issue.start_date = args["start_date"]
    if "target_date" in args:
        issue.target_date = args["target_date"]
    if any(key in args for key in ("state_id", "state_name", "state_group")):
        issue.state = _pick_state(issue.project, state_id=args.get("state_id"), name=args.get("state_name"), group=args.get("state_group"))
    issue.save()
    if "labels" in args:
        IssueLabel.objects.filter(issue=issue).delete()
        for label_name in args.get("labels", []):
            label, _ = Label.objects.get_or_create(workspace=issue.workspace, project=issue.project, name=label_name, defaults={"color": "#4E8CFF"})
            IssueLabel.objects.get_or_create(issue=issue, label=label, project=issue.project, workspace=issue.workspace)
    if "assignee_ids" in args:
        IssueAssignee.objects.filter(issue=issue).delete()
        for assignee_id in args.get("assignee_ids", []):
            IssueAssignee.objects.get_or_create(issue=issue, assignee_id=assignee_id, project=issue.project, workspace=issue.workspace)
    for blocked_id in args.get("blocks", []):
        IssueBlocker.objects.get_or_create(block=_require_issue(blocked_id), blocked_by=issue, project=issue.project, workspace=issue.workspace)
    for related_id in args.get("relates_to", []):
        IssueRelation.objects.get_or_create(issue=issue, related_issue=_require_issue(related_id), relation_type=IssueRelationChoices.RELATES_TO, project=issue.project, workspace=issue.workspace)
    return _serialize_issue(issue)


def check_capacity_and_budget(args: dict[str, Any]) -> dict[str, Any]:
    ctx = _resolve_context(args)
    workspace = _require_workspace(ctx)
    running_sessions = CyrusSession.objects.filter(agent__workspace=workspace, status=SessionStatus.RUNNING).count()
    pools = [{"pool": pool.name, "state": ComputeTracker(pool=pool).get_pool_budget_state()} for pool in ComputePool.objects.filter(workspace=workspace, deleted_at__isnull=True)]
    return {"running_sessions": running_sessions, "pools": pools}


def _eval_prompt(work_item: Issue) -> str:
    """
    Build a focused self-audit prompt.

    The worker receives this after its implementation pass.  It must NOT make
    further changes — only inspect what already exists and report honestly.
    """
    workspace = work_item.project.workspace_path or "(workspace)"
    requirements = (work_item.description_stripped or "No description.").strip()
    return (
        f"EVALUATION ONLY — do NOT modify any files or write new code.\n\n"
        f"You have just finished a work pass for this story:\n"
        f"  Title: {work_item.name}\n\n"
        f"Story requirements:\n{requirements}\n\n"
        f"Workspace: {workspace}\n\n"
        f"Check the workspace now and verify every requirement above is satisfied.\n"
        f"Reply with EXACTLY one of these two formats and nothing else:\n\n"
        f"  DONE: <one-sentence summary of what was delivered>\n\n"
        f"  INCOMPLETE: <bullet list — one gap per line, be specific>\n\n"
        f"Do not narrate. Do not apologise. Do not fix anything. Just evaluate."
    )


def _continuation_prompt(work_item: Issue, gaps: str, pass_num: int) -> str:
    """Build a targeted follow-up prompt that hands the gap list back to the worker."""
    workspace = work_item.project.workspace_path or "(workspace)"
    requirements = (work_item.description_stripped or "").strip()
    return (
        f"This is pass {pass_num} for story: {work_item.name}\n\n"
        f"The previous pass was incomplete. Gaps identified by evaluation:\n"
        f"{gaps}\n\n"
        f"Fix every gap listed above so the story fully satisfies its requirements.\n\n"
        f"Full requirements for reference:\n{requirements}\n\n"
        f"Workspace: {workspace}\n\n"
        f"When done, all required files must exist and every requirement must be met."
    )


def _mark_work_item_done(
    work_item: Issue,
    *,
    session: CyrusSession | None = None,
    summary: str | None = None,
    actor: User | None = None,
) -> None:
    from plane.app.orchestrator.lifecycle import WorkItemLifecycle

    actor = actor or (work_item.workspace.owner if work_item.workspace_id else None)
    report = WorkItemLifecycle().complete(
        work_item,
        session=session,
        summary=summary,
        actor=actor,
    )
    if report.violations:
        logger.warning(
            "Work item %s completed with violations: %s",
            work_item.id,
            "; ".join(v.message for v in report.violations),
        )


def start_story_session(args: dict[str, Any]) -> dict[str, Any]:
    """
    Dispatch a worker agent to execute a story, then run an evaluation loop.

    After each implementation pass the same agent receives a lightweight
    self-audit prompt.  It must reply DONE or INCOMPLETE (with gaps).

    • DONE       → mark the work item completed and return.
    • INCOMPLETE → feed the gap list back as a continuation prompt and retry.

    After max_passes retries without a DONE verdict the work item is left open
    and a spike is filed so Cyrus can route the gap work manually.
    """
    ctx = _resolve_context(args)
    agent = _ensure_agent(ctx)
    work_item = _pick_dispatch_issue(ctx, args)
    max_passes: int = max(1, int(args.get("max_passes", 3)))
    workspace = work_item.project.workspace_path or ""

    last_session = None
    prompt = args["prompt"]

    for pass_num in range(1, max_passes + 1):
        last_session = ACPXDispatcher(
            agent=agent,
            pool=agent.pool,
            project=work_item.project,
            work_item=work_item,
            goal=work_item.project.goal,
        ).dispatch(prompt)

        if last_session.status != SessionStatus.COMPLETED:
            # Hard failure (timeout, rate-limit, error) — stop immediately.
            break

        # ── Evaluation pass ───────────────────────────────────────────────
        eval_session = ACPXDispatcher(
            agent=agent,
            pool=agent.pool,
            project=work_item.project,
            work_item=work_item,
            goal=work_item.project.goal,
        ).dispatch(_eval_prompt(work_item))

        # Extract the agent's verdict from the evaluation session's output.
        chunks = [
            e.get("text", "")
            for e in (eval_session.event_log or [])
            if e.get("type") == "agent_message_chunk"
        ]
        verdict_text = "\n".join(chunks).strip()

        if verdict_text.upper().startswith("DONE"):
            done_summary = verdict_text.removeprefix("DONE:").strip() or verdict_text
            _mark_work_item_done(
                work_item,
                session=last_session,
                summary=done_summary,
            )
            return {
                "session_id": str(last_session.id),
                "eval_session_id": str(eval_session.id),
                "status": last_session.status,
                "work_item_id": str(work_item.id),
                "work_item_done": True,
                "passes": pass_num,
                "verdict": verdict_text[:300],
            }

        # INCOMPLETE — extract gap details and prepare next pass.
        gaps = verdict_text.removeprefix("INCOMPLETE:").strip() or verdict_text

        if pass_num < max_passes:
            prompt = _continuation_prompt(work_item, gaps, pass_num + 1)
        else:
            # Exhausted retries — file a spike so a human or Cyrus can triage.
            spike_title = f"[Spike] Unresolved gaps in: {work_item.name}"
            spike_desc = (
                f"The story worker did not satisfy all requirements after "
                f"{max_passes} passes.\n\n"
                f"Last evaluation gaps:\n{gaps}"
            )
            try:
                spike_state = _pick_state(
                    work_item.project, group=StateGroup.BACKLOG.value
                )
                Issue.objects.create(
                    project=work_item.project,
                    workspace=work_item.workspace,
                    state=spike_state,
                    name=spike_title,
                    description_html=_markdown_to_html(spike_desc),
                    description_json={},
                    priority="high",
                )
            except Exception:
                pass  # Non-fatal — the story result is still returned below.

    return {
        "session_id": str(last_session.id) if last_session else None,
        "status": last_session.status if last_session else "never_started",
        "work_item_id": str(work_item.id),
        "work_item_done": False,
        "passes": pass_num if last_session else 0,
        "verdict": "INCOMPLETE after max passes — spike filed",
    }


def force_start_story(args: dict[str, Any]) -> dict[str, Any]:
    result = start_story_session(args)
    result["forced"] = True
    return result


def interact_with_session(args: dict[str, Any]) -> dict[str, Any]:
    session = CyrusSession.objects.select_related("agent").filter(id=args["session_id"]).first()
    if session is None:
        raise CyrusToolError("session not found")
    response = _relay_post(session.agent, ["message", "sessions/message", "session/message", "interact"], {"session_id": session.acpx_session_id or str(session.id), "message": args["message"]}, timeout=int(args.get("timeout", 60)))
    event_log = list(session.event_log or [])
    event_log.append({"type": "human_interaction", "message": args["message"], "response": response["payload"], "timestamp": timezone.now().isoformat()})
    session.event_log = event_log
    session.save(update_fields=["event_log", "updated_at"])
    return response


def ask_agent_question(args: dict[str, Any]) -> dict[str, Any]:
    ctx = _resolve_context(args)
    agent = _ensure_agent(ctx)
    work_item = _pick_dispatch_issue(ctx, args)
    session = ACPXDispatcher(agent=agent, pool=agent.pool, project=work_item.project, work_item=work_item, goal=work_item.project.goal).dispatch(args["question"], one_shot=True)
    return {"session_id": str(session.id), "status": session.status, "answer": session.outcome}


def cancel_session(args: dict[str, Any]) -> dict[str, Any]:
    session = CyrusSession.objects.select_related("agent").filter(id=args["session_id"]).first()
    if session is None:
        raise CyrusToolError("session not found")
    response = _relay_post(session.agent, ["cancel", "sessions/cancel", "session/cancel"], {"session_id": session.acpx_session_id or str(session.id), "reason": args.get("reason", "cancelled_by_cyrus")})
    session.status = SessionStatus.CANCELLED
    session.ended_at = timezone.now()
    session.save(update_fields=["status", "ended_at", "updated_at"])
    return {"session_id": str(session.id), "status": session.status, "relay": response}


def escalate_to_human_blocker(args: dict[str, Any]) -> dict[str, Any]:
    issue = _require_issue(args["issue_id"])
    blocker = Issue.objects.create(project=issue.project, workspace=issue.workspace, state=_pick_state(issue.project, group=StateGroup.BACKLOG.value), name=args.get("title") or f"[Blocker] Human unblock needed for {issue.name}", priority="urgent", description_html=_markdown_to_html(args.get("description") or "Human escalation required."), description_json={})
    IssueBlocker.objects.get_or_create(block=issue, blocked_by=blocker, project=issue.project, workspace=issue.workspace)
    notification = _notify_user(workspace=issue.workspace, project=issue.project, receiver=issue.workspace.owner, title="Cyrus escalation", message=f"{blocker.name}\n\nOriginal story: {issue.name}", entity_name="issue", entity_identifier=blocker.id, data={"original_issue_id": str(issue.id), "blocker_issue_id": str(blocker.id)})
    apprise = _send_apprise_notification("Cyrus blocker escalation", f"{blocker.name}\n\nOriginal issue: {issue.name}")
    return {"blocker_issue": _serialize_issue(blocker), "notification_id": str(notification.id), "apprise": apprise}


def create_agent_spike(args: dict[str, Any]) -> dict[str, Any]:
    payload = {**args, "title": args.get("title") or f"[Spike] {args['research_question']}", "description": args.get("description") or f"Time-boxed research spike.\n\nQuestion: {args['research_question']}", "labels": list({*(args.get("labels") or []), "spike"}), "priority": args.get("priority", "medium")}
    return create_work_item(payload)


def request_human_approval(args: dict[str, Any]) -> dict[str, Any]:
    ctx = _resolve_context(args)
    workspace = _require_workspace(ctx)
    approval = Approval.objects.create(goal=ctx.goal, project=ctx.project, agent=_ensure_agent(ctx), threshold_matched=args["question"], status=ApprovalStatus.PENDING)
    notification = _notify_user(workspace=workspace, project=ctx.project, receiver=workspace.owner, triggered_by=workspace.owner, title="Cyrus approval requested", message=args["question"], entity_name="approval", data={"approval_id": str(approval.id), "yes_label": args.get("yes_label", "Approve"), "no_label": args.get("no_label", "Reject")})
    return {"approval_id": str(approval.id), "notification_id": str(notification.id), "status": approval.status}


def register_artifact(args: dict[str, Any]) -> dict[str, Any]:
    issue = _require_issue(args["issue_id"])
    target = args["target"]
    metadata = {"artifact_type": args.get("artifact_type", "deliverable"), "registered_by": "cyrus_tool"}
    if target.startswith("http://") or target.startswith("https://"):
        link = IssueLink.objects.create(issue=issue, project=issue.project, workspace=issue.workspace, title=args.get("title", "Artifact"), url=target, metadata=metadata)
        return {"artifact_kind": "url", "link_id": str(link.id)}
    comment = _upsert_comment(issue, f"Artifact registered: `{Path(target)}`", issue.workspace.owner)
    return {"artifact_kind": "file", "comment_id": str(comment.id), "metadata": {**metadata, "path": target}}


def record_session_outcome(args: dict[str, Any]) -> dict[str, Any]:
    session = CyrusSession.objects.select_related("work_item", "project").filter(id=args["session_id"]).first()
    if session is None:
        raise CyrusToolError("session not found")
    if "cost_usd" in args:
        session.estimated_cost_usd = Decimal(str(args["cost_usd"]))
    if "summary" in args:
        session.summary = args["summary"]
    if "status" in args:
        session.status = args["status"]
    if session.ended_at is None:
        session.ended_at = timezone.now()
    session.save()

    result: dict[str, Any] = {
        "session_id": str(session.id),
        "status": session.status,
        "cost_usd": str(session.estimated_cost_usd),
    }

    if session.work_item_id and args.get("mark_done", True):
        actor = session.project.workspace.owner if session.project else None
        _mark_work_item_done(
            session.work_item,
            session=session,
            summary=args.get("summary"),
            actor=actor,
        )
        result["lifecycle_complete"] = True

    return result


def flag_alignment_drift(args: dict[str, Any]) -> dict[str, Any]:
    ctx = _resolve_context(args)
    workspace = _require_workspace(ctx)
    project = ctx.project or Project.objects.filter(workspace=workspace, deleted_at__isnull=True).order_by("created_at").first()
    if project is None:
        raise CyrusToolError("No project found to attach the drift warning")
    issue = Issue.objects.create(project=project, workspace=workspace, state=_pick_state(project, group=StateGroup.BACKLOG.value), name=args.get("title") or "[Alignment Drift] Human review required", priority="high", description_html=_markdown_to_html(args.get("description") or "Cyrus detected work that appears misaligned with the active goal."), description_json={})
    notification = _notify_user(workspace=workspace, project=project, receiver=workspace.owner, title="Alignment drift detected", message=issue.name, entity_name="issue", entity_identifier=issue.id, data={"goal_id": str(ctx.goal.id) if ctx.goal else None, "issue_id": str(issue.id)})
    return {"warning_issue": _serialize_issue(issue), "notification_id": str(notification.id)}


TOOL_REGISTRY: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {"get_registered_agents": get_registered_agents, "get_system_settings": get_system_settings, "update_system_settings": update_system_settings, "configure_project_workflow": configure_project_workflow, "get_markdown_view": get_markdown_view, "search_workspace": search_workspace, "check_story_duplicates": check_story_duplicates, "manage_goals_and_projects": manage_goals_and_projects, "manage_cycles_and_modules": manage_cycles_and_modules, "define_kpi_schema": define_kpi_schema, "log_kpi_datapoint": log_kpi_datapoint, "get_activity_data_for_summary": get_activity_data_for_summary, "create_work_item": create_work_item, "update_work_item": update_work_item, "check_capacity_and_budget": check_capacity_and_budget, "start_story_session": start_story_session, "force_start_story": force_start_story, "interact_with_session": interact_with_session, "ask_agent_question": ask_agent_question, "cancel_session": cancel_session, "escalate_to_human_blocker": escalate_to_human_blocker, "create_agent_spike": create_agent_spike, "request_human_approval": request_human_approval, "register_artifact": register_artifact, "record_session_outcome": record_session_outcome, "flag_alignment_drift": flag_alignment_drift}


def execute_tool(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    if tool_name not in TOOL_REGISTRY:
        raise CyrusToolError(f"Unknown Cyrus tool: {tool_name}")
    result = TOOL_REGISTRY[tool_name](args)
    return json.loads(json.dumps(result, default=_json_default))
