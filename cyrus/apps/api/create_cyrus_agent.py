#!/usr/bin/env python
"""Create or update the Cyrus PM agent in the database."""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plane.settings.production')
django.setup()

from plane.db.models import Workspace, Agent, ComputePool

def main():
    # Get the workspace
    ws = Workspace.objects.filter(deleted_at__isnull=True).first()
    if not ws:
        print("ERROR: No workspace found")
        return 1

    print(f"Workspace: {ws.name} ({ws.id})")

    # Get or create a pool for Cyrus (use the existing subscription pool)
    pool = ComputePool.objects.filter(workspace=ws, provider='anthropic').first()
    if not pool:
        print("ERROR: No anthropic pool found")
        return 1

    print(f"Pool: {pool.name} ({pool.id})")

    # Create or update Cyrus Agent
    cyrus_agent, created = Agent.objects.get_or_create(
        name="Cyrus PM",
        workspace=ws,
        defaults={
            'pool': pool,
            'agent_type': 'openclaw',
            'is_cyrus_agent': True,
            'relay_url': 'http://localhost:9999',  # Not used for OpenClaw
            'status': 'online',
            'config': {
                'model': 'claude-sonnet-4.5-20250929',
                'system_settings': {},
                'capabilities': {'pm': True, 'autonomous': True},
            }
        }
    )

    if not created:
        # Update the existing one
        cyrus_agent.is_cyrus_agent = True
        cyrus_agent.pool = pool
        cyrus_agent.config = cyrus_agent.config or {}
        cyrus_agent.config['model'] = 'claude-sonnet-4.5-20250929'
        cyrus_agent.save()
        print(f"✓ Updated Cyrus Agent: {cyrus_agent.name} ({cyrus_agent.id})")
    else:
        print(f"✓ Created Cyrus Agent: {cyrus_agent.name} ({cyrus_agent.id})")

    print(f"\nAgent ID: {cyrus_agent.id}")
    print(f"Is Cyrus Agent: {cyrus_agent.is_cyrus_agent}")
    print(f"Pool: {cyrus_agent.pool.name}")

    return 0

if __name__ == '__main__':
    sys.exit(main())
