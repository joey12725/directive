#!/usr/bin/env python
"""Set up Cyrus heartbeat periodic tasks in django-celery-beat."""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plane.settings.production')
django.setup()

from django_celery_beat.models import PeriodicTask, CrontabSchedule
from plane.db.models import Workspace

def get_or_create_crontab(minute='*', hour='*', day_of_week='*', day_of_month='*', month_of_year='*'):
    """Get or create a crontab schedule."""
    schedule, created = CrontabSchedule.objects.get_or_create(
        minute=minute,
        hour=hour,
        day_of_week=day_of_week,
        day_of_month=day_of_month,
        month_of_year=month_of_year,
    )
    return schedule

def setup_tasks():
    """Set up all Cyrus heartbeat tasks."""

    # Get workspace ID from env or use first workspace
    workspace_id = os.environ.get('CYRUS_DEFAULT_WORKSPACE_ID')
    if not workspace_id:
        ws = Workspace.objects.filter(deleted_at__isnull=True).first()
        if ws:
            workspace_id = str(ws.id)
            print(f"Using first available workspace: {ws.name} ({workspace_id})")
        else:
            print("WARNING: No workspace found. Tasks will be created but may fail at runtime.")
            workspace_id = ""
    else:
        print(f"Using CYRUS_DEFAULT_WORKSPACE_ID: {workspace_id}")

    tasks_config = [
        {
            'name': 'cyrus-visionary-ideation-loop',
            'task': 'plane.app.orchestrator.loop_tasks.visionary_ideation_loop',
            'schedule': get_or_create_crontab(minute='*/30'),  # Every 30 minutes
            'description': 'Cyrus PM generates new stories from open goals'
        },
        {
            'name': 'cyrus-backlog-grooming-loop',
            'task': 'plane.app.orchestrator.loop_tasks.backlog_grooming_loop',
            'schedule': get_or_create_crontab(minute='10', hour='*/2'),  # Every 2 hours at :10
            'description': 'Cyrus PM grooms and enriches pending stories'
        },
        {
            'name': 'cyrus-janitor-triage-loop',
            'task': 'plane.app.orchestrator.loop_tasks.janitor_triage_loop',
            'schedule': get_or_create_crontab(minute='25', hour='*/4'),  # Every 4 hours at :25
            'description': 'Cyrus PM closes stale sessions and normalizes intake'
        },
        {
            'name': 'cyrus-alignment-audit-loop',
            'task': 'plane.app.orchestrator.loop_tasks.audit_alignment_loop',
            'schedule': get_or_create_crontab(minute='0', hour='8'),  # Daily at 08:00 UTC
            'description': 'Cyrus PM audits delivery against goal intent'
        },
        {
            'name': 'cyrus-archivist-wiki-loop',
            'task': 'plane.app.wiki_sync.tasks.archivist_wiki_loop',
            'schedule': get_or_create_crontab(minute='45', hour='*/6'),  # Every 6 hours at :45
            'description': 'Cyrus PM syncs local wiki to Plane workspace'
        },
    ]

    created_count = 0
    updated_count = 0

    for config in tasks_config:
        task, created = PeriodicTask.objects.get_or_create(
            name=config['name'],
            defaults={
                'task': config['task'],
                'crontab': config['schedule'],
                'args': f'["{workspace_id}"]',
                'description': config['description'],
                'enabled': True,
            }
        )

        if not created:
            task.task = config['task']
            task.crontab = config['schedule']
            task.args = f'["{workspace_id}"]'
            task.description = config['description']
            task.enabled = True
            task.save()
            updated_count += 1
            print(f"✓ Updated: {config['name']}")
        else:
            created_count += 1
            print(f"✓ Created: {config['name']}")

    print(f"\n{created_count} tasks created, {updated_count} tasks updated")
    print("\nTo disable a task:")
    print("  docker exec cyrus-api-1 python manage.py shell")
    print("  >>> from django_celery_beat.models import PeriodicTask")
    print("  >>> PeriodicTask.objects.filter(name='cyrus-...').update(enabled=False)")

    return 0

if __name__ == '__main__':
    sys.exit(setup_tasks())
