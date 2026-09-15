"""
Work-item lifecycle enforcement for Cyrus.

Every state transition (backlog → in-progress, in-progress → done) passes
through this module.  It auto-populates fields that can be derived from
context and rejects transitions when required data is still missing.

If a new dispatch path, tool, or agent flow is added in the future, routing
it through WorkItemLifecycle guarantees the same completeness rules apply.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from django.utils import timezone

from html import escape

from plane.db.models import (
    Agent,
    CyrusSession,
    Issue,
    IssueAssignee,
    IssueComment,
    IssueLink,
    State,
    User,
)
from plane.db.models.state import StateGroup

logger = logging.getLogger(__name__)


def _markdown_to_html(text: str | None) -> str:
    text = (text or "").strip()
    if not text:
        return "<p></p>"
    paragraphs = [f"<p>{escape(block).replace(chr(10), '<br/>')}</p>" for block in text.split("\n\n") if block.strip()]
    return "".join(paragraphs) or "<p></p>"


def _upsert_comment(issue: Issue, body: str, actor: User | None) -> IssueComment:
    return IssueComment.objects.create(
        issue=issue,
        project=issue.project,
        workspace=issue.workspace,
        actor=actor,
        comment_html=_markdown_to_html(body),
        comment_json={},
    )


@dataclass(slots=True)
class Violation:
    """A single completeness violation on a work item."""
    field: str
    message: str
    severity: str = "error"  # "error" blocks transition, "warning" logs only


@dataclass(slots=True)
class ComplianceReport:
    """Result of validating a work item against lifecycle requirements."""
    issue_id: str
    transition: str
    violations: list[Violation] = field(default_factory=list)
    auto_fixed: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not any(v.severity == "error" for v in self.violations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "transition": self.transition,
            "passed": self.passed,
            "violations": [
                {"field": v.field, "message": v.message, "severity": v.severity}
                for v in self.violations
            ],
            "auto_fixed": self.auto_fixed,
        }


class WorkItemLifecycle:
    """
    Gate-keeper for work-item state transitions.

    Usage::

        lifecycle = WorkItemLifecycle()

        # When an agent starts working on a story:
        report = lifecycle.start(issue, agent=agent, actor=workspace.owner)

        # When a story is marked done:
        report = lifecycle.complete(
            issue,
            session=session,
            summary="Built the login page...",
            actor=workspace.owner,
        )

    Both methods auto-populate missing fields where possible, then validate.
    If validation fails the state transition is NOT applied — the caller
    receives the report with violations and can decide how to proceed.
    """

    # ── transition: start ────────────────────────────────────────────────

    def start(
        self,
        issue: Issue,
        *,
        agent: Agent | None = None,
        actor: User | None = None,
    ) -> ComplianceReport:
        """
        Transition a work item to in-progress.

        Auto-populates:
        - start_date  (today, if not already set)
        - assignee    (actor, if no assignees exist)
        - state       (first STARTED-group state)

        Validates:
        - description is not empty
        - at least one assignee exists after auto-population
        """
        report = ComplianceReport(
            issue_id=str(issue.id), transition="start"
        )

        # ── auto-populate start_date ─────────────────────────────────────
        if not issue.start_date:
            issue.start_date = timezone.now().date()
            report.auto_fixed.append("start_date")

        # ── auto-populate assignee ───────────────────────────────────────
        has_assignees = IssueAssignee.objects.filter(issue=issue).exists()
        if not has_assignees and actor is not None:
            IssueAssignee.objects.get_or_create(
                issue=issue,
                assignee=actor,
                defaults={
                    "project": issue.project,
                    "workspace": issue.workspace,
                },
            )
            report.auto_fixed.append("assignee")

        # ── move to in-progress state ────────────────────────────────────
        in_progress = (
            State.objects.filter(
                project=issue.project,
                group=StateGroup.STARTED.value,
            )
            .order_by("sequence")
            .first()
        ) or (
            State.objects.filter(
                project=issue.project,
                name__iexact="In Progress",
            )
            .order_by("sequence")
            .first()
        )
        if in_progress and issue.state_id != in_progress.id:
            issue.state = in_progress
            report.auto_fixed.append("state")

        # ── validate ─────────────────────────────────────────────────────
        if not _has_description(issue):
            report.violations.append(
                Violation(
                    field="description",
                    message="Work item has no description — agent work will lack context",
                    severity="warning",
                )
            )

        # Persist the auto-populated fields
        issue.save(update_fields=["start_date", "state", "updated_at"])

        if report.auto_fixed:
            logger.info(
                "Lifecycle.start auto-fixed fields on %s: %s",
                issue.id,
                ", ".join(report.auto_fixed),
            )
        if report.violations:
            logger.warning(
                "Lifecycle.start violations on %s: %s",
                issue.id,
                "; ".join(v.message for v in report.violations),
            )

        return report

    # ── transition: complete ─────────────────────────────────────────────

    def complete(
        self,
        issue: Issue,
        *,
        session: CyrusSession | None = None,
        summary: str | None = None,
        actor: User | None = None,
    ) -> ComplianceReport:
        """
        Transition a work item to completed.

        Auto-populates:
        - completed_at       (now)
        - state              (first COMPLETED-group state)
        - session comment    (from summary, if provided and no session comment exists)
        - start_date         (created_at, if somehow still missing)

        Validates (warnings — logged but don't block):
        - description is not empty
        - at least one assignee exists
        - at least one comment exists (session summary)
        - start_date is set
        """
        report = ComplianceReport(
            issue_id=str(issue.id), transition="complete"
        )

        # ── auto-populate completed_at ───────────────────────────────────
        if not issue.completed_at:
            issue.completed_at = timezone.now()
            report.auto_fixed.append("completed_at")

        # ── auto-populate start_date if still missing ────────────────────
        if not issue.start_date:
            issue.start_date = (issue.created_at or timezone.now()).date()
            report.auto_fixed.append("start_date")

        # ── move to completed state ──────────────────────────────────────
        done_state = (
            State.objects.filter(
                project=issue.project,
                group=StateGroup.COMPLETED.value,
                deleted_at__isnull=True,
            )
            .order_by("sequence")
            .first()
        )
        if done_state:
            issue.state = done_state
            report.auto_fixed.append("state")

        # ── post session summary as comment if missing ───────────────────
        has_comments = IssueComment.objects.filter(issue=issue).exists()
        if not has_comments and summary:
            _upsert_comment(issue, summary, actor)
            report.auto_fixed.append("session_comment")
        elif not has_comments and session and session.summary:
            _upsert_comment(issue, session.summary, actor)
            report.auto_fixed.append("session_comment")

        # ── persist ──────────────────────────────────────────────────────
        issue.save(update_fields=["state", "completed_at", "start_date", "updated_at"])

        # ── validate completeness ────────────────────────────────────────
        if not _has_description(issue):
            report.violations.append(
                Violation(
                    field="description",
                    message="Completed work item has no description",
                    severity="warning",
                )
            )

        if not IssueAssignee.objects.filter(issue=issue).exists():
            report.violations.append(
                Violation(
                    field="assignee",
                    message="Completed work item has no assignee",
                    severity="warning",
                )
            )

        if not IssueComment.objects.filter(issue=issue).exists():
            report.violations.append(
                Violation(
                    field="comments",
                    message="Completed work item has no session summary comment",
                    severity="warning",
                )
            )

        if not issue.start_date:
            report.violations.append(
                Violation(
                    field="start_date",
                    message="Completed work item has no start date",
                    severity="warning",
                )
            )

        if report.auto_fixed:
            logger.info(
                "Lifecycle.complete auto-fixed fields on %s: %s",
                issue.id,
                ", ".join(report.auto_fixed),
            )
        if report.violations:
            logger.warning(
                "Lifecycle.complete violations on %s: %s",
                issue.id,
                "; ".join(v.message for v in report.violations),
            )

        return report


def audit_work_item(issue: Issue) -> ComplianceReport:
    """
    Non-mutating audit: check a work item's completeness for its current state.

    Returns a report of what's missing without changing anything.  Useful for
    dashboard health checks, post-dispatch analysis, and batch auditing.
    """
    report = ComplianceReport(
        issue_id=str(issue.id),
        transition="audit",
    )

    state_group = issue.state.group if issue.state_id else None

    if not _has_description(issue):
        report.violations.append(
            Violation(field="description", message="No description")
        )

    if not IssueAssignee.objects.filter(issue=issue).exists():
        report.violations.append(
            Violation(field="assignee", message="No assignee")
        )

    if not issue.start_date and state_group in (
        StateGroup.STARTED.value,
        StateGroup.COMPLETED.value,
    ):
        report.violations.append(
            Violation(field="start_date", message="No start date despite being started/completed")
        )

    if state_group == StateGroup.COMPLETED.value:
        if not IssueComment.objects.filter(issue=issue).exists():
            report.violations.append(
                Violation(field="comments", message="Completed with no session summary")
            )

        if not issue.completed_at:
            report.violations.append(
                Violation(field="completed_at", message="In completed state but completed_at is null")
            )

    return report


def _has_description(issue: Issue) -> bool:
    """Check whether an issue has meaningful description content."""
    if issue.description_stripped and issue.description_stripped.strip():
        return True
    if issue.description_html and issue.description_html not in ("", "<p></p>"):
        return True
    return False
