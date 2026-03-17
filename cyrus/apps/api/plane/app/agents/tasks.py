from __future__ import annotations

from celery import shared_task
from django.utils import timezone
import requests

from plane.db.models import Agent, AgentStatus


@shared_task
def check_agent_health() -> dict[str, int]:
    """Ping relay health endpoints and refresh each agent's current availability."""

    counts = {"online": 0, "degraded": 0, "offline": 0}

    for agent in Agent.objects.filter(status__in=[AgentStatus.ONLINE, AgentStatus.DEGRADED]):
        try:
            response = requests.get(
                f"{agent.relay_url.rstrip('/')}/health",
                headers={"Authorization": f"Bearer {agent.relay_secret}"},
                timeout=10,
            )
            agent.status = AgentStatus.ONLINE if response.status_code == 200 else AgentStatus.DEGRADED
        except (requests.ConnectionError, requests.Timeout):
            agent.status = AgentStatus.OFFLINE
        except requests.RequestException:
            agent.status = AgentStatus.DEGRADED

        agent.last_heartbeat = timezone.now()
        agent.save(update_fields=["status", "last_heartbeat", "updated_at"])
        counts[agent.status] += 1

    return counts
