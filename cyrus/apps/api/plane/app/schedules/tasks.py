"""
Celery Tasks for Phase 4 Scheduling Engine

These tasks handle:
- Periodic scheduling ticks to evaluate dispatch plans
- Individual dispatch execution
- Conflict detection across schedule rows
- Automatic cycle management based on project cycle_duration
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import pytz
from celery import shared_task
from django.db.models import Q, Sum
from django.utils import timezone

from plane.app.agents.dispatcher import ACPXDispatcher
from plane.app.orchestrator.engine import Orchestrator
from plane.app.schedules.engine import SchedulingEngine
from plane.db.models import ComputeAllocation, Cycle, Project, Schedule, ScheduleRow, Workspace

logger = logging.getLogger(__name__)


@shared_task
def scheduling_tick() -> dict[str, Any]:
    """
    Periodic scheduling tick that evaluates all workspaces and dispatches work.

    This task should be run every 5 minutes via Celery Beat. It:
    1. Iterates over all active workspaces
    2. Runs the SchedulingEngine for each workspace
    3. Dispatches work items based on the computed dispatch plan

    Returns:
        Dictionary with statistics about the tick execution:
            - workspaces_evaluated: Number of workspaces processed
            - total_plans: Total dispatch plans generated
            - dispatches_triggered: Number of execute_dispatch tasks launched
            - errors: Number of errors encountered
    """
    stats = {
        "workspaces_evaluated": 0,
        "total_plans": 0,
        "dispatches_triggered": 0,
        "errors": 0,
    }

    workspaces = Workspace.objects.filter(deleted_at__isnull=True)

    for workspace in workspaces:
        try:
            stats["workspaces_evaluated"] += 1

            # Run the scheduling engine
            engine = SchedulingEngine(workspace_id=str(workspace.id))
            dispatch_plans = engine.compute_dispatch_plan()

            stats["total_plans"] += len(dispatch_plans)

            # Trigger dispatch tasks for each plan
            for plan in dispatch_plans:
                intensity = plan.get("intensity", "normal")
                if intensity != "skip":
                    allocation_id = plan["allocation_id"]
                    execute_dispatch.delay(allocation_id, intensity)
                    stats["dispatches_triggered"] += 1

        except Exception as exc:
            logger.exception(f"Error processing workspace {workspace.id} in scheduling tick")
            stats["errors"] += 1
            continue

    logger.info(f"Scheduling tick completed: {stats}")
    return stats


@shared_task
def execute_dispatch(allocation_id: str, intensity: str) -> dict[str, Any]:
    """
    Execute a dispatch for a specific ComputeAllocation.

    This task:
    1. Fetches the ComputeAllocation with all related objects
    2. Uses the Orchestrator to select work and compose a prompt
    3. Dispatches the work via ACPXDispatcher
    4. Triggers post-dispatch analysis

    Args:
        allocation_id: UUID string of the ComputeAllocation to dispatch
        intensity: Dispatch intensity level ("conservative", "normal", "aggressive")

    Returns:
        Dictionary with dispatch results:
            - allocation_id: The allocation ID
            - session_id: Created session ID (if successful)
            - status: "success", "failed", or "skipped"
            - error: Error message (if failed)
    """
    try:
        # Fetch the allocation with related objects
        alloc = ComputeAllocation.objects.select_related(
            'agent', 'pool', 'project', 'goal'
        ).get(id=allocation_id, deleted_at__isnull=True)

    except ComputeAllocation.DoesNotExist:
        logger.error(f"ComputeAllocation {allocation_id} not found or deleted")
        return {
            "allocation_id": allocation_id,
            "status": "failed",
            "error": "Allocation not found",
        }

    try:
        # Check if project exists
        if not alloc.project:
            logger.warning(f"Allocation {allocation_id} has no project, skipping")
            return {
                "allocation_id": allocation_id,
                "status": "skipped",
                "error": "No project associated",
            }

        # Orchestrator interfacing: select work item
        orchestrator = Orchestrator()
        work_item = orchestrator.select_work_item(alloc.project)

        if not work_item:
            logger.info(f"No work items available for project {alloc.project.id}, skipping dispatch")
            return {
                "allocation_id": allocation_id,
                "status": "skipped",
                "error": "No work items available",
            }

        # Compose dispatch prompt
        prompt = orchestrator.compose_dispatch_prompt(work_item, intensity=intensity)

        # Dispatch via ACPX
        dispatcher = ACPXDispatcher(
            agent=alloc.agent,
            pool=alloc.pool,
            project=alloc.project,
            work_item=work_item,
            goal=alloc.goal,
        )

        session = dispatcher.dispatch(prompt)

        # Trigger post-dispatch analysis (stub for now)
        post_dispatch_analysis.delay(str(alloc.project.id), str(work_item.id))

        logger.info(
            f"Dispatch successful for allocation {allocation_id}, "
            f"session {session.id}, work_item {work_item.id}"
        )

        return {
            "allocation_id": allocation_id,
            "session_id": str(session.id),
            "work_item_id": str(work_item.id),
            "status": "success",
        }

    except Exception as exc:
        logger.exception(f"Error executing dispatch for allocation {allocation_id}")
        return {
            "allocation_id": allocation_id,
            "status": "failed",
            "error": str(exc),
        }


@shared_task
def detect_conflicts(workspace_id: str) -> list[dict[str, Any]]:
    """
    Detect scheduling conflicts for a workspace.

    This task evaluates all ScheduleRow entries for overlapping time windows
    that target the same ComputePool. If the sum of utilization_pct for
    overlapping rows exceeds 100, it's flagged as a conflict.

    Args:
        workspace_id: The workspace ID to check

    Returns:
        List of conflict dictionaries, each containing:
            - pool_id: The conflicting pool ID
            - pool_name: The pool name
            - schedule_ids: List of schedule IDs involved
            - rows: List of row details (day, start_time, end_time, utilization_pct)
            - total_utilization: Sum of utilization percentages
            - time_window: Description of the conflict window
    """
    conflicts = []

    try:
        # Get all schedules for this workspace
        schedules = Schedule.objects.filter(
            workspace_id=workspace_id,
            deleted_at__isnull=True
        ).prefetch_related('rows', 'allocations__pool')

        # Build a mapping of pools to schedule rows
        pool_to_rows: dict[str, list[tuple[Schedule, ScheduleRow]]] = {}

        for schedule in schedules:
            for alloc in schedule.allocations.filter(deleted_at__isnull=True):
                pool_id = str(alloc.pool_id)
                if pool_id not in pool_to_rows:
                    pool_to_rows[pool_id] = []

                # Add all rows from this schedule for this pool
                for row in schedule.rows.filter(deleted_at__isnull=True):
                    pool_to_rows[pool_id].append((schedule, row))

        # Check each pool for conflicts
        for pool_id, schedule_rows in pool_to_rows.items():
            # Group by day and check for time overlaps
            conflicts_for_pool = _find_overlapping_rows(schedule_rows)

            for conflict in conflicts_for_pool:
                if conflict["total_utilization"] > 100:
                    conflict["pool_id"] = pool_id
                    conflicts.append(conflict)
                    logger.warning(
                        f"Scheduling conflict detected for pool {pool_id}: "
                        f"{conflict['total_utilization']}% utilization in {conflict['time_window']}"
                    )

    except Exception as exc:
        logger.exception(f"Error detecting conflicts for workspace {workspace_id}")

    return conflicts


def _find_overlapping_rows(schedule_rows: list[tuple[Schedule, ScheduleRow]]) -> list[dict[str, Any]]:
    """
    Helper function to find overlapping time windows in schedule rows.

    Args:
        schedule_rows: List of (Schedule, ScheduleRow) tuples

    Returns:
        List of conflict dictionaries
    """
    conflicts = []

    # Group by day
    day_groups: dict[str, list[tuple[Schedule, ScheduleRow]]] = {}

    for schedule, row in schedule_rows:
        days = row.days if isinstance(row.days, list) else []
        for day in days:
            if day not in day_groups:
                day_groups[day] = []
            day_groups[day].append((schedule, row))

    # Check each day for overlaps
    for day, rows in day_groups.items():
        # Compare each row with every other row
        for i, (sched1, row1) in enumerate(rows):
            for sched2, row2 in rows[i + 1:]:
                # Check if time windows overlap
                if _times_overlap(row1.start_time, row1.end_time, row2.start_time, row2.end_time):
                    total_util = row1.utilization_pct + row2.utilization_pct
                    conflicts.append({
                        "schedule_ids": [str(sched1.id), str(sched2.id)],
                        "rows": [
                            {
                                "schedule_name": sched1.name,
                                "day": day,
                                "start_time": str(row1.start_time),
                                "end_time": str(row1.end_time),
                                "utilization_pct": row1.utilization_pct,
                            },
                            {
                                "schedule_name": sched2.name,
                                "day": day,
                                "start_time": str(row2.start_time),
                                "end_time": str(row2.end_time),
                                "utilization_pct": row2.utilization_pct,
                            },
                        ],
                        "total_utilization": total_util,
                        "time_window": f"{day} {row1.start_time}-{row1.end_time}",
                    })

    return conflicts


def _times_overlap(start1, end1, start2, end2) -> bool:
    """Check if two time ranges overlap."""
    return start1 < end2 and start2 < end1


@shared_task
def manage_cycles() -> dict[str, Any]:
    """
    Automatically create Plane Cycles based on project cycle_duration settings.

    This task:
    1. Queries all active projects
    2. Creates new Cycle models based on cycle_duration ("5h", "24h", "7d")
    3. Ensures cycles are created in the correct timezone

    Returns:
        Dictionary with statistics:
            - projects_evaluated: Number of projects checked
            - cycles_created: Number of new cycles created
            - errors: Number of errors encountered
    """
    stats = {
        "projects_evaluated": 0,
        "cycles_created": 0,
        "errors": 0,
    }

    projects = Project.objects.filter(deleted_at__isnull=True)

    for project in projects:
        try:
            stats["projects_evaluated"] += 1

            # Get the workspace timezone (fallback to UTC)
            workspace = project.workspace
            tz_name = getattr(workspace, 'timezone', 'UTC')
            try:
                project_tz = pytz.timezone(tz_name)
            except pytz.UnknownTimeZoneError:
                project_tz = pytz.UTC

            now = timezone.now().astimezone(project_tz)

            # Determine cycle duration
            cycle_duration = project.cycle_duration or "5h"

            # Check if we need to create a new cycle
            should_create, start_date, end_date = _should_create_cycle(
                project, cycle_duration, now, project_tz
            )

            if should_create:
                # Create the cycle
                cycle = Cycle.objects.create(
                    project=project,
                    name=f"{project.name} - {start_date.strftime('%Y-%m-%d %H:%M')}",
                    description=f"Auto-generated {cycle_duration} cycle",
                    start_date=start_date,
                    end_date=end_date,
                    created_by=project.created_by,
                    updated_by=project.updated_by,
                )
                stats["cycles_created"] += 1
                logger.info(f"Created cycle {cycle.id} for project {project.id}")

        except Exception as exc:
            logger.exception(f"Error managing cycles for project {project.id}")
            stats["errors"] += 1
            continue

    logger.info(f"Cycle management completed: {stats}")
    return stats


def _should_create_cycle(project: Project, cycle_duration: str, now: datetime, tz) -> tuple[bool, datetime, datetime]:
    """
    Determine if a new cycle should be created and calculate its dates.

    Args:
        project: The project to check
        cycle_duration: Duration string ("5h", "24h", "7d")
        now: Current datetime in project timezone
        tz: Project timezone

    Returns:
        Tuple of (should_create, start_date, end_date)
    """
    # Get the latest cycle for this project
    latest_cycle = Cycle.objects.filter(
        project=project,
        deleted_at__isnull=True
    ).order_by('-end_date').first()

    # Parse cycle duration
    duration_map = {
        "5h": timedelta(hours=5),
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
    }

    duration = duration_map.get(cycle_duration, timedelta(hours=5))

    # If no cycles exist, create the first one
    if not latest_cycle:
        start_date = now
        end_date = now + duration
        return True, start_date, end_date

    # If the latest cycle has ended, create a new one
    if latest_cycle.end_date and latest_cycle.end_date <= now:
        start_date = latest_cycle.end_date
        end_date = start_date + duration
        return True, start_date, end_date

    # Otherwise, don't create a new cycle yet
    return False, now, now


@shared_task
def post_dispatch_analysis(project_id: str, work_item_id: str) -> dict[str, Any]:
    """
    Stub task for post-dispatch analysis.

    In a full implementation, this would:
    - Analyze the session outcome
    - Update project metrics
    - Trigger follow-up work if needed
    - Update goal KPIs

    Args:
        project_id: The project ID
        work_item_id: The work item (Issue) ID

    Returns:
        Dictionary with analysis results (currently stubbed)
    """
    logger.info(f"Post-dispatch analysis triggered for project {project_id}, work_item {work_item_id}")

    # TODO: Implement actual analysis logic in Phase 5
    return {
        "project_id": project_id,
        "work_item_id": work_item_id,
        "status": "stubbed",
        "message": "Post-dispatch analysis not yet implemented",
    }
