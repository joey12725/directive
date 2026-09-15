"""
Tests for WorkItemLifecycle enforcement gates.

These tests verify that state transitions auto-populate required fields
and report violations when data is missing — ensuring future dispatch
paths can't silently produce incomplete stories.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch, PropertyMock
from uuid import uuid4

import pytest


# ---------------------------------------------------------------------------
# Helpers to build lightweight fakes without touching Django ORM
# ---------------------------------------------------------------------------

class FakeState:
    def __init__(self, *, group="backlog", name="Backlog", pk=None):
        self.id = pk or uuid4()
        self.group = group
        self.name = name
        self.sequence = 1


class FakeProject:
    def __init__(self):
        self.id = uuid4()
        self.identifier = "TEST"
        self.workspace = FakeWorkspace()
        self.workspace_id = self.workspace.id
        self.goal = None


class FakeWorkspace:
    def __init__(self):
        self.id = uuid4()
        self.slug = "test-ws"
        self.owner = FakeUser()


class FakeUser:
    def __init__(self):
        self.id = uuid4()
        self.display_name = "Test User"


class FakeIssue:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", uuid4())
        self.name = kwargs.get("name", "Test Story")
        self.description_html = kwargs.get("description_html", "")
        self.description_stripped = kwargs.get("description_stripped", "")
        self.start_date = kwargs.get("start_date", None)
        self.completed_at = kwargs.get("completed_at", None)
        self.created_at = kwargs.get("created_at", datetime(2026, 1, 1))
        self.state = kwargs.get("state", FakeState())
        self.state_id = self.state.id if self.state else None
        self.project = kwargs.get("project", FakeProject())
        self.workspace = self.project.workspace
        self.workspace_id = self.workspace.id
        self._saved_fields = []

    def save(self, update_fields=None):
        self._saved_fields = update_fields or []


class FakeSession:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", uuid4())
        self.summary = kwargs.get("summary", "")
        self.event_log = kwargs.get("event_log", [])
        self.work_item = kwargs.get("work_item", None)
        self.work_item_id = self.work_item.id if self.work_item else None
        self.project = kwargs.get("project", None)
        self.agent = kwargs.get("agent", None)
        self.agent_id = self.agent.id if self.agent else None
        self.project_id = self.project.id if self.project else None


class FakeAgent:
    def __init__(self):
        self.id = uuid4()
        self.name = "test-agent"


# ---------------------------------------------------------------------------
# Tests for WorkItemLifecycle.start()
# ---------------------------------------------------------------------------

class TestLifecycleStart:
    """Tests that lifecycle.start() enforces invariants at the start transition."""

    @patch("plane.app.orchestrator.lifecycle.IssueAssignee")
    @patch("plane.app.orchestrator.lifecycle.State")
    def test_auto_populates_start_date(self, mock_state_cls, mock_assignee_cls):
        """start_date must be set when a story begins — lifecycle fills it in."""
        from plane.app.orchestrator.lifecycle import WorkItemLifecycle

        mock_state_cls.objects.filter.return_value.order_by.return_value.first.return_value = None
        mock_assignee_cls.objects.filter.return_value.exists.return_value = True

        issue = FakeIssue(start_date=None)
        lifecycle = WorkItemLifecycle()
        report = lifecycle.start(issue, actor=FakeUser())

        assert issue.start_date is not None, "start_date should be auto-populated"
        assert "start_date" in report.auto_fixed

    @patch("plane.app.orchestrator.lifecycle.IssueAssignee")
    @patch("plane.app.orchestrator.lifecycle.State")
    def test_auto_populates_assignee_when_none_exist(self, mock_state_cls, mock_assignee_cls):
        """If no assignees exist, lifecycle assigns the actor."""
        from plane.app.orchestrator.lifecycle import WorkItemLifecycle

        mock_state_cls.objects.filter.return_value.order_by.return_value.first.return_value = None
        mock_assignee_cls.objects.filter.return_value.exists.return_value = False
        mock_assignee_cls.objects.get_or_create.return_value = (MagicMock(), True)

        actor = FakeUser()
        issue = FakeIssue()
        lifecycle = WorkItemLifecycle()
        report = lifecycle.start(issue, actor=actor)

        assert "assignee" in report.auto_fixed
        mock_assignee_cls.objects.get_or_create.assert_called_once()

    @patch("plane.app.orchestrator.lifecycle.IssueAssignee")
    @patch("plane.app.orchestrator.lifecycle.State")
    def test_does_not_overwrite_existing_start_date(self, mock_state_cls, mock_assignee_cls):
        """If start_date is already set, lifecycle leaves it alone."""
        from plane.app.orchestrator.lifecycle import WorkItemLifecycle

        mock_state_cls.objects.filter.return_value.order_by.return_value.first.return_value = None
        mock_assignee_cls.objects.filter.return_value.exists.return_value = True

        existing_date = date(2026, 3, 1)
        issue = FakeIssue(start_date=existing_date)
        lifecycle = WorkItemLifecycle()
        report = lifecycle.start(issue)

        assert issue.start_date == existing_date, "Existing start_date should not be overwritten"
        assert "start_date" not in report.auto_fixed

    @patch("plane.app.orchestrator.lifecycle.IssueAssignee")
    @patch("plane.app.orchestrator.lifecycle.State")
    def test_warns_on_missing_description(self, mock_state_cls, mock_assignee_cls):
        """Starting a story with no description should produce a warning."""
        from plane.app.orchestrator.lifecycle import WorkItemLifecycle

        mock_state_cls.objects.filter.return_value.order_by.return_value.first.return_value = None
        mock_assignee_cls.objects.filter.return_value.exists.return_value = True

        issue = FakeIssue(description_html="", description_stripped="")
        lifecycle = WorkItemLifecycle()
        report = lifecycle.start(issue)

        desc_violations = [v for v in report.violations if v.field == "description"]
        assert len(desc_violations) == 1
        assert desc_violations[0].severity == "warning"

    @patch("plane.app.orchestrator.lifecycle.IssueAssignee")
    @patch("plane.app.orchestrator.lifecycle.State")
    def test_transitions_state_to_in_progress(self, mock_state_cls, mock_assignee_cls):
        """Lifecycle should move the issue to the STARTED state group."""
        from plane.app.orchestrator.lifecycle import WorkItemLifecycle

        in_progress_state = FakeState(group="started", name="In Progress")
        mock_state_cls.objects.filter.return_value.order_by.return_value.first.return_value = in_progress_state
        mock_assignee_cls.objects.filter.return_value.exists.return_value = True

        issue = FakeIssue()
        lifecycle = WorkItemLifecycle()
        report = lifecycle.start(issue)

        assert issue.state == in_progress_state
        assert "state" in report.auto_fixed


# ---------------------------------------------------------------------------
# Tests for WorkItemLifecycle.complete()
# ---------------------------------------------------------------------------

class TestLifecycleComplete:
    """Tests that lifecycle.complete() enforces invariants at the done transition."""

    @patch("plane.app.orchestrator.lifecycle.IssueComment")
    @patch("plane.app.orchestrator.lifecycle.IssueAssignee")
    @patch("plane.app.orchestrator.lifecycle.State")
    def test_auto_populates_completed_at(self, mock_state, mock_assignee, mock_comment):
        """completed_at must be set when a story finishes."""
        from plane.app.orchestrator.lifecycle import WorkItemLifecycle

        mock_state.objects.filter.return_value.order_by.return_value.first.return_value = FakeState(group="completed")
        mock_assignee.objects.filter.return_value.exists.return_value = True
        mock_comment.objects.filter.return_value.exists.return_value = True

        issue = FakeIssue(completed_at=None)
        lifecycle = WorkItemLifecycle()
        report = lifecycle.complete(issue)

        assert issue.completed_at is not None
        assert "completed_at" in report.auto_fixed

    @patch("plane.app.orchestrator.lifecycle.IssueComment")
    @patch("plane.app.orchestrator.lifecycle.IssueAssignee")
    @patch("plane.app.orchestrator.lifecycle.State")
    def test_backfills_start_date_on_completion(self, mock_state, mock_assignee, mock_comment):
        """If start_date was never set, completion backfills it from created_at."""
        from plane.app.orchestrator.lifecycle import WorkItemLifecycle

        mock_state.objects.filter.return_value.order_by.return_value.first.return_value = FakeState(group="completed")
        mock_assignee.objects.filter.return_value.exists.return_value = True
        mock_comment.objects.filter.return_value.exists.return_value = True

        created = datetime(2026, 2, 15)
        issue = FakeIssue(start_date=None, created_at=created)
        lifecycle = WorkItemLifecycle()
        report = lifecycle.complete(issue)

        assert issue.start_date == created.date()
        assert "start_date" in report.auto_fixed

    @patch("plane.app.orchestrator.lifecycle._upsert_comment")
    @patch("plane.app.orchestrator.lifecycle.IssueComment")
    @patch("plane.app.orchestrator.lifecycle.IssueAssignee")
    @patch("plane.app.orchestrator.lifecycle.State")
    def test_posts_summary_comment_when_missing(self, mock_state, mock_assignee, mock_comment, mock_upsert):
        """If no comments exist and a summary is provided, lifecycle posts it."""
        from plane.app.orchestrator.lifecycle import WorkItemLifecycle

        mock_state.objects.filter.return_value.order_by.return_value.first.return_value = FakeState(group="completed")
        mock_assignee.objects.filter.return_value.exists.return_value = True
        mock_comment.objects.filter.return_value.exists.return_value = False

        issue = FakeIssue()
        lifecycle = WorkItemLifecycle()
        report = lifecycle.complete(issue, summary="Built the login page with OAuth support")

        assert "session_comment" in report.auto_fixed
        mock_upsert.assert_called_once()

    @patch("plane.app.orchestrator.lifecycle.IssueComment")
    @patch("plane.app.orchestrator.lifecycle.IssueAssignee")
    @patch("plane.app.orchestrator.lifecycle.State")
    def test_warns_on_missing_assignee_at_completion(self, mock_state, mock_assignee, mock_comment):
        """Completing a story with no assignee should produce a warning."""
        from plane.app.orchestrator.lifecycle import WorkItemLifecycle

        mock_state.objects.filter.return_value.order_by.return_value.first.return_value = FakeState(group="completed")
        mock_assignee.objects.filter.return_value.exists.return_value = False
        mock_comment.objects.filter.return_value.exists.return_value = True

        issue = FakeIssue(description_html="<p>real description</p>", description_stripped="real description")
        lifecycle = WorkItemLifecycle()
        report = lifecycle.complete(issue)

        assignee_violations = [v for v in report.violations if v.field == "assignee"]
        assert len(assignee_violations) == 1

    @patch("plane.app.orchestrator.lifecycle.IssueComment")
    @patch("plane.app.orchestrator.lifecycle.IssueAssignee")
    @patch("plane.app.orchestrator.lifecycle.State")
    def test_warns_on_missing_session_summary(self, mock_state, mock_assignee, mock_comment):
        """Completing a story with no comments should produce a warning."""
        from plane.app.orchestrator.lifecycle import WorkItemLifecycle

        mock_state.objects.filter.return_value.order_by.return_value.first.return_value = FakeState(group="completed")
        mock_assignee.objects.filter.return_value.exists.return_value = True
        mock_comment.objects.filter.return_value.exists.return_value = False

        issue = FakeIssue(description_html="<p>desc</p>", description_stripped="desc")
        lifecycle = WorkItemLifecycle()
        report = lifecycle.complete(issue)

        comment_violations = [v for v in report.violations if v.field == "comments"]
        assert len(comment_violations) == 1

    @patch("plane.app.orchestrator.lifecycle.IssueComment")
    @patch("plane.app.orchestrator.lifecycle.IssueAssignee")
    @patch("plane.app.orchestrator.lifecycle.State")
    def test_uses_session_summary_fallback(self, mock_state, mock_assignee, mock_comment):
        """If no explicit summary but session has one, lifecycle uses it."""
        from plane.app.orchestrator.lifecycle import WorkItemLifecycle

        mock_state.objects.filter.return_value.order_by.return_value.first.return_value = FakeState(group="completed")
        mock_assignee.objects.filter.return_value.exists.return_value = True
        mock_comment.objects.filter.return_value.exists.return_value = False

        issue = FakeIssue()
        session = FakeSession(summary="Implemented auth flow", work_item=issue, project=issue.project)

        with patch("plane.app.orchestrator.lifecycle._upsert_comment") as mock_upsert:
            lifecycle = WorkItemLifecycle()
            report = lifecycle.complete(issue, session=session)

            assert "session_comment" in report.auto_fixed
            mock_upsert.assert_called_once()


# ---------------------------------------------------------------------------
# Tests for audit_work_item()
# ---------------------------------------------------------------------------

class TestAuditWorkItem:
    """Tests for the non-mutating audit function."""

    @patch("plane.app.orchestrator.lifecycle.IssueComment")
    @patch("plane.app.orchestrator.lifecycle.IssueAssignee")
    def test_detects_all_missing_fields_on_completed_item(self, mock_assignee, mock_comment):
        """A completed item with no description, assignee, comments, or dates should report all violations."""
        from plane.app.orchestrator.lifecycle import audit_work_item

        mock_assignee.objects.filter.return_value.exists.return_value = False
        mock_comment.objects.filter.return_value.exists.return_value = False

        completed_state = FakeState(group="completed", name="Done")
        issue = FakeIssue(
            state=completed_state,
            start_date=None,
            completed_at=None,
            description_html="",
            description_stripped="",
        )

        report = audit_work_item(issue)

        violation_fields = {v.field for v in report.violations}
        assert "description" in violation_fields
        assert "assignee" in violation_fields
        assert "start_date" in violation_fields
        assert "comments" in violation_fields
        assert "completed_at" in violation_fields

    @patch("plane.app.orchestrator.lifecycle.IssueComment")
    @patch("plane.app.orchestrator.lifecycle.IssueAssignee")
    def test_clean_item_passes_audit(self, mock_assignee, mock_comment):
        """A fully populated completed item should pass audit with no violations."""
        from plane.app.orchestrator.lifecycle import audit_work_item

        mock_assignee.objects.filter.return_value.exists.return_value = True
        mock_comment.objects.filter.return_value.exists.return_value = True

        completed_state = FakeState(group="completed", name="Done")
        issue = FakeIssue(
            state=completed_state,
            start_date=date(2026, 3, 1),
            completed_at=datetime(2026, 3, 15),
            description_html="<p>Real description</p>",
            description_stripped="Real description",
        )

        report = audit_work_item(issue)

        assert len(report.violations) == 0, f"Expected no violations, got: {[v.message for v in report.violations]}"

    @patch("plane.app.orchestrator.lifecycle.IssueComment")
    @patch("plane.app.orchestrator.lifecycle.IssueAssignee")
    def test_backlog_item_only_checks_description_and_assignee(self, mock_assignee, mock_comment):
        """A backlog item shouldn't be flagged for missing start_date or comments."""
        from plane.app.orchestrator.lifecycle import audit_work_item

        mock_assignee.objects.filter.return_value.exists.return_value = True
        mock_comment.objects.filter.return_value.exists.return_value = False

        backlog_state = FakeState(group="backlog", name="Backlog")
        issue = FakeIssue(
            state=backlog_state,
            start_date=None,
            description_html="<p>Desc</p>",
            description_stripped="Desc",
        )

        report = audit_work_item(issue)
        violation_fields = {v.field for v in report.violations}

        assert "start_date" not in violation_fields, "Backlog items shouldn't require start_date"
        assert "comments" not in violation_fields, "Backlog items shouldn't require comments"
