from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests
from celery import shared_task
from django.utils import timezone

from plane.db.models import Agent, AgentStatus

logger = logging.getLogger(__name__)


def _check_single_agent_health(agent: Agent) -> tuple[Agent, AgentStatus]:
    """Check health of a single agent (for parallel execution)."""
    try:
        response = requests.get(
            f"{agent.relay_url.rstrip('/')}/health",
            headers={"Authorization": f"Bearer {agent.relay_secret}"},
            timeout=10,
        )
        status = AgentStatus.ONLINE if response.status_code == 200 else AgentStatus.DEGRADED
        logger.debug(
            "Agent health check success",
            extra={"agent_id": str(agent.id), "agent_name": agent.name, "status": status, "status_code": response.status_code}
        )
        return agent, status
    except (requests.ConnectionError, requests.Timeout) as exc:
        logger.warning(
            "Agent health check offline",
            extra={"agent_id": str(agent.id), "agent_name": agent.name, "error": str(exc)}
        )
        return agent, AgentStatus.OFFLINE
    except requests.RequestException as exc:
        logger.warning(
            "Agent health check degraded",
            extra={"agent_id": str(agent.id), "agent_name": agent.name, "error": str(exc)}
        )
        return agent, AgentStatus.DEGRADED


@shared_task
def check_agent_health() -> dict[str, Any]:
    """
    Ping relay health endpoints and refresh each agent's current availability.

    Enhanced with:
    - Concurrent health checks using ThreadPoolExecutor
    - Batch database updates using bulk_update
    - Structured logging
    """
    counts = {"online": 0, "degraded": 0, "offline": 0, "total": 0}

    agents = list(Agent.objects.filter(
        status__in=[AgentStatus.ONLINE, AgentStatus.DEGRADED],
        deleted_at__isnull=True
    ))

    if not agents:
        logger.info("No agents to check")
        return counts

    counts["total"] = len(agents)
    logger.info(f"Starting health check for {len(agents)} agents")

    # Check all agents concurrently
    now = timezone.now()
    agents_to_update: list[Agent] = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_agent = {executor.submit(_check_single_agent_health, agent): agent for agent in agents}

        for future in as_completed(future_to_agent):
            try:
                agent, new_status = future.result()
                agent.status = new_status
                agent.last_heartbeat = now
                agents_to_update.append(agent)
                counts[new_status] += 1
            except Exception as exc:
                original_agent = future_to_agent[future]
                logger.exception(
                    "Unexpected error checking agent health",
                    extra={"agent_id": str(original_agent.id), "agent_name": original_agent.name, "error": str(exc)}
                )

    # Batch update all agents at once
    if agents_to_update:
        Agent.objects.bulk_update(agents_to_update, ["status", "last_heartbeat", "updated_at"])
        logger.info(
            "Agent health check completed",
            extra={"counts": counts, "updated_count": len(agents_to_update)}
        )

    return counts
