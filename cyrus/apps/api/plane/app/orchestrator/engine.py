"""
Orchestrator Stub - Phase 4

This is a temporary stub implementation of the Orchestrator class to prevent ImportError
while Phase 4 (Scheduling Engine) is being used. The full Orchestrator implementation
will be completed in Phase 5 (The Cyrus Agent).

The Orchestrator is responsible for:
- Selecting the next work item from a project's backlog
- Composing dispatch prompts based on work context and intensity
- Managing the intelligent routing of work to agents
"""

from __future__ import annotations

import logging
from typing import Any

from plane.db.models import Issue, Project, State
from plane.db.models.state import StateGroup

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Stub Orchestrator for work item selection and prompt composition.

    This class provides minimal functionality to allow Phase 4 to operate
    without the full Cyrus Agent implementation from Phase 5.
    """

    def select_work_item(self, project: Project) -> Issue | None:
        """
        Select the next work item (Issue) from a project's backlog.

        This stub implementation returns the first open Issue in the project.
        If no issues exist, it creates a dummy one to prevent errors.

        Args:
            project: The Project to select work from

        Returns:
            An Issue object, or None if the project is invalid
        """
        if not project:
            logger.warning("select_work_item called with None project")
            return None

        # Find the first open issue (not in COMPLETED or CANCELLED state groups)
        open_issue = Issue.objects.filter(
            project=project,
            deleted_at__isnull=True,
            archived_at__isnull=True,
        ).exclude(
            state__group__in=[StateGroup.COMPLETED.value, StateGroup.CANCELLED.value]
        ).order_by('created_at').first()

        if open_issue:
            logger.info(f"Selected work item {open_issue.id} from project {project.id}")
            return open_issue

        # If no open issues exist, create a dummy one
        logger.warning(f"No open issues found for project {project.id}, creating dummy issue")
        return self._create_dummy_issue(project)

    def compose_dispatch_prompt(self, work_item: Issue, intensity: str = "normal") -> str:
        """
        Compose a dispatch prompt for the agent based on the work item and intensity.

        This stub implementation returns a basic prompt string. The full implementation
        in Phase 5 will include:
        - Context gathering from related issues, PRs, and documentation
        - Intensity-specific instruction tuning
        - Goal alignment and KPI tracking instructions
        - Tool usage guidelines

        Args:
            work_item: The Issue to work on
            intensity: Dispatch intensity ("conservative", "normal", "aggressive")

        Returns:
            A prompt string for the agent
        """
        if not work_item:
            return "No work item provided. Please check the project backlog."

        # Build a basic prompt
        intensity_instructions = {
            "conservative": "Work carefully and conservatively. Minimize token usage and avoid risky operations.",
            "normal": "Work at a normal pace with standard best practices.",
            "aggressive": "Work efficiently and prioritize throughput. This is high-priority work.",
        }

        instruction = intensity_instructions.get(intensity, intensity_instructions["normal"])

        prompt = f"""
{instruction}

Work Item: {work_item.name}
Project: {work_item.project.name if work_item.project else "Unknown"}

Description:
{work_item.description or "No description provided."}

Please analyze this work item and begin implementation. Follow the project's coding standards
and create tests where appropriate.

Note: This is a stub prompt from the Phase 4 Orchestrator. Phase 5 will provide enhanced
context and goal-specific instructions.
""".strip()

        logger.info(
            f"Composed dispatch prompt for work item {work_item.id} "
            f"with intensity '{intensity}' ({len(prompt)} chars)"
        )

        return prompt

    def _create_dummy_issue(self, project: Project) -> Issue:
        """
        Create a dummy issue for projects with no open work items.

        This prevents the scheduling engine from failing when a project has no issues.
        In a production system, this would instead signal that the project is complete
        or needs user input.

        Args:
            project: The project to create the issue in

        Returns:
            A newly created dummy Issue
        """
        # Find or create a "To Do" state for this project
        todo_state = State.objects.filter(
            project=project,
            group=StateGroup.BACKLOG.value,
            deleted_at__isnull=True
        ).order_by('sequence').first()

        if not todo_state:
            # Fallback: use any state
            todo_state = State.objects.filter(
                project=project,
                deleted_at__isnull=True
            ).order_by('sequence').first()

        if not todo_state:
            logger.error(f"No states found for project {project.id}, cannot create dummy issue")
            raise ValueError(f"Project {project.id} has no states configured")

        # Create the dummy issue
        dummy_issue = Issue.objects.create(
            project=project,
            name="[Auto-Generated] Placeholder Work Item",
            description=(
                "This is a placeholder issue created by the Cyrus Orchestrator stub. "
                "The project had no open work items, so this was created to prevent scheduling errors. "
                "Please create real issues for this project or disable its compute allocation."
            ),
            state=todo_state,
            created_by=project.created_by,
            updated_by=project.updated_by,
        )

        logger.info(f"Created dummy issue {dummy_issue.id} for project {project.id}")
        return dummy_issue
