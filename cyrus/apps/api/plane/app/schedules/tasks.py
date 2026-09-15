"""
Celery Tasks for Phase 4 Scheduling Engine - Enhanced

These tasks handle:
- Periodic scheduling ticks to evaluate dispatch plans
- Individual dispatch execution with retry and circuit breaker
- Advanced conflict detection with resolution suggestions
- Automatic cycle management based on project cycle_duration

Enhanced with:
- Exponential backoff retry
- Allocation tracking (last_dispatched_at, consecutive_failures)
- Circuit breaker integration
- Detailed metrics and logging
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
        Dictionary with statistics about the tick execution
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


@shared_task(
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=3,
    retry_jitter=True,
)
def execute_dispatch(allocation_id: str, intensity: str) -> dict[str, Any]:
    """
    Execute a dispatch for a specific ComputeAllocation.

    Enhanced with:
    - Exponential backoff retry for connection errors
    - Rate limit backoff using Celery countdown (non-blocking)
    - Allocation tracking (last_dispatched_at, consecutive_failures)
    - Circuit breaker integration
    - Comprehensive error handling

    Args:
        allocation_id: UUID string of the ComputeAllocation to dispatch
        intensity: Dispatch intensity level ("conservative", "normal", "aggressive")

    Returns:
        Dictionary with dispatch results
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

    # Check for recent rate limit events on this pool
    from plane.db.models import RateLimitEvent
    recent_rate_limit = RateLimitEvent.objects.filter(
        pool=alloc.pool,
        timestamp__gte=timezone.now() - timedelta(hours=6)  # Check last 6 hours
    ).order_by('-timestamp').first()

    if recent_rate_limit and recent_rate_limit.retry_after_seconds > 0:
        # Calculate time remaining until retry is allowed
        time_since_event = (timezone.now() - recent_rate_limit.timestamp).total_seconds()
        time_remaining = recent_rate_limit.retry_after_seconds - time_since_event

        if time_remaining > 0:
            # Reschedule this task using Celery countdown (non-blocking)
            logger.info(
                f"Rate limit active for pool {alloc.pool.name}, rescheduling dispatch in {time_remaining:.0f}s"
            )
            # Use apply_async with countdown to reschedule
            execute_dispatch.apply_async(
                args=[allocation_id, intensity],
                countdown=min(time_remaining, 21600)  # Cap at 6 hours
            )
            return {
                "allocation_id": allocation_id,
                "status": "rate_limited_rescheduled",
                "retry_after_seconds": time_remaining,
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

        # Update allocation tracking
        alloc.last_dispatched_at = timezone.now()
        alloc.consecutive_failures = 0  # Reset on success
        alloc.save(update_fields=['last_dispatched_at', 'consecutive_failures', 'updated_at'])

        # Trigger post-dispatch analysis
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

    except (ConnectionError, TimeoutError) as exc:
        # These will be retried automatically by Celery
        logger.warning(f"Retryable error for allocation {allocation_id}: {exc}")
        _increment_allocation_failures(alloc)
        raise  # Celery will handle retry

    except Exception as exc:
        logger.exception(f"Error executing dispatch for allocation {allocation_id}")
        _increment_allocation_failures(alloc)

        # Check if the session was rate limited and reschedule
        if hasattr(exc, 'response') and getattr(exc.response, 'status_code', None) == 429:
            # Extract retry_after from response headers if available
            retry_after = 0
            if hasattr(exc, 'response') and exc.response is not None:
                retry_after_header = exc.response.headers.get('Retry-After')
                if retry_after_header:
                    try:
                        retry_after = float(retry_after_header)
                    except (ValueError, TypeError):
                        retry_after = 3600  # Default to 1 hour

            if retry_after > 0:
                logger.info(
                    f"Rate limit (429) for allocation {allocation_id}, rescheduling in {retry_after:.0f}s"
                )
                execute_dispatch.apply_async(
                    args=[allocation_id, intensity],
                    countdown=min(retry_after, 21600)  # Cap at 6 hours
                )
                return {
                    "allocation_id": allocation_id,
                    "status": "rate_limited_rescheduled",
                    "retry_after_seconds": retry_after,
                }

        return {
            "allocation_id": allocation_id,
            "status": "failed",
            "error": str(exc),
        }


def _increment_allocation_failures(alloc: ComputeAllocation) -> None:
    """Increment consecutive failure counter for circuit breaker."""
    try:
        alloc.consecutive_failures += 1
        alloc.save(update_fields=['consecutive_failures', 'updated_at'])
        logger.warning(
            f"Allocation {alloc.id} consecutive failures: {alloc.consecutive_failures}"
        )
    except Exception as exc:
        logger.error(f"Failed to update allocation failure count: {exc}")


@shared_task
def detect_conflicts(workspace_id: str) -> dict[str, Any]:
    """
    Detect scheduling conflicts for a workspace with resolution suggestions.

    Enhanced with:
    - Detailed conflict categorization
    - Resolution strategy suggestions
    - Severity scoring

    Args:
        workspace_id: The workspace ID to check

    Returns:
        Dictionary with conflicts and resolution suggestions
    """
    conflicts = []
    resolution_suggestions = []

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
                pool_name = alloc.pool.name

                if pool_id not in pool_to_rows:
                    pool_to_rows[pool_id] = []

                # Add all rows from this schedule for this pool
                for row in schedule.rows.filter(deleted_at__isnull=True):
                    pool_to_rows[pool_id].append((schedule, row, pool_name))

        # Check each pool for conflicts
        for pool_id, schedule_rows in pool_to_rows.items():
            pool_name = schedule_rows[0][2] if schedule_rows else "Unknown"
            conflicts_for_pool = _find_overlapping_rows_with_suggestions(schedule_rows, pool_id, pool_name)

            for conflict in conflicts_for_pool:
                if conflict["total_utilization"] > 100:
                    conflicts.append(conflict)
                    resolution_suggestions.extend(conflict.get("suggestions", []))

                    severity = _calculate_conflict_severity(conflict["total_utilization"])
                    logger.warning(
                        f"Scheduling conflict detected (severity: {severity}) for pool {pool_name}: "
                        f"{conflict['total_utilization']}% utilization in {conflict['time_window']}"
                    )

    except Exception as exc:
        logger.exception(f"Error detecting conflicts for workspace {workspace_id}")

    return {
        "conflicts": conflicts,
        "resolution_suggestions": resolution_suggestions,
        "total_conflicts": len(conflicts),
    }


def _find_overlapping_rows_with_suggestions(
    schedule_rows: list[tuple[Schedule, ScheduleRow, str]],
    pool_id: str,
    pool_name: str
) -> list[dict[str, Any]]:
    """
    Helper function to find overlapping time windows with resolution suggestions.
    """
    conflicts = []

    # Group by day
    day_groups: dict[str, list[tuple[Schedule, ScheduleRow]]] = {}

    for schedule, row, _ in schedule_rows:
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
                    over_utilization = total_util - 100

                    # Generate resolution suggestions
                    suggestions = _generate_conflict_resolutions(
                        row1, row2, over_utilization, pool_name
                    )

                    conflicts.append({
                        "pool_id": pool_id,
                        "pool_name": pool_name,
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
                        "over_utilization": over_utilization,
                        "time_window": f"{day} {row1.start_time}-{row1.end_time}",
                        "suggestions": suggestions,
                    })

    return conflicts


def _generate_conflict_resolutions(
    row1: ScheduleRow,
    row2: ScheduleRow,
    over_utilization: int,
    pool_name: str
) -> list[dict[str, str]]:
    """Generate resolution suggestions for scheduling conflicts."""
    suggestions = []

    # Suggestion 1: Reduce utilization percentages
    reduction_each = (over_utilization + 1) // 2
    new_util_1 = row1.utilization_pct - reduction_each
    new_util_2 = row2.utilization_pct - reduction_each

    if new_util_1 > 0 and new_util_2 > 0:
        suggestions.append({
            "strategy": "reduce_utilization",
            "description": f"Reduce row 1 utilization to {new_util_1}% and row 2 to {new_util_2}%",
            "impact": "Both schedules run concurrently with reduced capacity",
        })

    # Suggestion 2: Shift time windows
    suggestions.append({
        "strategy": "shift_times",
        "description": f"Shift one schedule's time window to avoid overlap",
        "impact": "Schedules run at different times, full capacity for each",
    })

    # Suggestion 3: Use different pool
    suggestions.append({
        "strategy": "different_pool",
        "description": f"Move one schedule to a different compute pool",
        "impact": "Distributes load across multiple pools",
    })

    # Suggestion 4: Merge schedules
    suggestions.append({
        "strategy": "merge_schedules",
        "description": f"Combine both schedules into one with reduced total utilization",
        "impact": "Simplifies management, coordinates resource usage",
    })

    return suggestions


def _calculate_conflict_severity(total_utilization: float) -> str:
    """Calculate severity of conflict based on over-utilization."""
    if total_utilization > 200:
        return "critical"
    elif total_utilization > 150:
        return "high"
    elif total_utilization > 120:
        return "medium"
    else:
        return "low"


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
        Dictionary with statistics
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


def _should_create_cycle(
    project: Project,
    cycle_duration: str,
    now: datetime,
    tz
) -> tuple[bool, datetime, datetime]:
    """Determine if a new cycle should be created and calculate its dates."""
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
    Post-dispatch analysis: audit work-item completeness and log violations.

    Runs after every dispatch to catch metadata gaps early rather than
    discovering them after a story is marked done.
    """
    from plane.app.orchestrator.lifecycle import audit_work_item
    from plane.db.models import Issue

    logger.info(f"Post-dispatch analysis triggered for project {project_id}, work_item {work_item_id}")

    try:
        issue = Issue.objects.select_related("state", "project", "workspace").filter(
            id=work_item_id, deleted_at__isnull=True
        ).first()
        if issue is None:
            return {"project_id": project_id, "work_item_id": work_item_id, "status": "not_found"}

        report = audit_work_item(issue)

        if report.violations:
            logger.warning(
                "Post-dispatch audit found %d violations on %s: %s",
                len(report.violations),
                work_item_id,
                "; ".join(v.message for v in report.violations),
            )

        return {
            "project_id": project_id,
            "work_item_id": work_item_id,
            "status": "audited",
            "violations": [
                {"field": v.field, "message": v.message, "severity": v.severity}
                for v in report.violations
            ],
        }
    except Exception as exc:
        logger.exception(f"Post-dispatch analysis failed for {work_item_id}")
        return {
            "project_id": project_id,
            "work_item_id": work_item_id,
            "status": "error",
            "error": str(exc),
        }
