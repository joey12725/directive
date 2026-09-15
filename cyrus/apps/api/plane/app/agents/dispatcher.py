from __future__ import annotations

import json
import logging
from typing import Any

import requests
from django.utils import timezone

from plane.app.metering.tracker import ComputeTracker
from plane.app.sessions.tasks import meter_session, summarize_session, trace_session_to_langfuse
from plane.app.orchestrator.lifecycle import WorkItemLifecycle
from plane.db.models import Agent, AgentStatus, ComputePool, CyrusSession, Goal, Issue, Project, SessionStatus, State
from plane.db.models.state import StateGroup

logger = logging.getLogger(__name__)

_lifecycle = WorkItemLifecycle()


class ACPXDispatcher:
    """Dispatch prompts to a remote Cyrus Relay and persist the resulting session stream."""

    DEFAULT_TIMEOUT_SECONDS = 600

    def __init__(
        self,
        *,
        agent: Agent,
        pool: ComputePool,
        project: Project,
        work_item: Issue,
        goal: Goal | None = None,
    ) -> None:
        self.agent = agent
        self.pool = pool
        self.project = project
        self.work_item = work_item
        self.goal = goal or project.goal
        self.tracker = ComputeTracker(pool=pool)

        # Configurable timeout: agent config > pool config > default
        self.timeout = self._get_timeout()

    def _get_timeout(self) -> int:
        """Get timeout from agent config, pool config, or default."""
        # Check agent config first
        if self.agent.config and isinstance(self.agent.config, dict):
            timeout = self.agent.config.get("timeout_seconds")
            if timeout is not None:
                try:
                    return int(timeout)
                except (ValueError, TypeError):
                    pass

        # Check pool config
        if hasattr(self.pool, 'config') and isinstance(self.pool.config, dict):
            timeout = self.pool.config.get("timeout_seconds")
            if timeout is not None:
                try:
                    return int(timeout)
                except (ValueError, TypeError):
                    pass

        return self.DEFAULT_TIMEOUT_SECONDS

    def _log_context(self) -> dict[str, Any]:
        """Build structured logging context."""
        return {
            "agent_id": str(self.agent.id),
            "agent_name": self.agent.name,
            "pool_id": str(self.pool.id),
            "pool_name": self.pool.name,
            "project_id": str(self.project.id),
            "project_name": self.project.name,
            "work_item_id": str(self.work_item.id) if self.work_item else None,
            "goal_id": str(self.goal.id) if self.goal else None,
        }

    def dispatch(self, prompt: str, session_name: str | None = None, one_shot: bool = False) -> CyrusSession:
        session = self._create_session()
        session_name = session_name or self._build_session_name(session)
        headers = {"Authorization": f"Bearer {self.agent.relay_secret}"}
        payload = {
            "agent": self.agent.acpx_agent_name,
            "prompt": prompt,
            "session_name": session_name,
            "cwd": self.project.workspace_path,
        }
        request_url = f"{self.agent.relay_url.rstrip('/')}{'/exec' if one_shot else '/dispatch'}"

        log_context = {
            **self._log_context(),
            "session_id": str(session.id),
            "session_name": session_name,
            "one_shot": one_shot,
            "timeout": self.timeout,
        }

        logger.info(
            "Starting dispatch",
            extra=log_context
        )

        self._mark_work_item_in_progress()

        try:
            if one_shot:
                self._dispatch_one_shot(session=session, request_url=request_url, headers=headers, payload=payload)
            else:
                self._dispatch_stream(session=session, request_url=request_url, headers=headers, payload=payload)
        except requests.ConnectionError as exc:
            logger.error(
                "Connection error during dispatch",
                extra={**log_context, "error": str(exc)}
            )
            session.status = SessionStatus.FAILED
            session.outcome = {"error": str(exc), "kind": "connection_error"}
            self.agent.status = AgentStatus.OFFLINE
            self.agent.save(update_fields=["status", "updated_at"])
        except requests.Timeout as exc:
            logger.error(
                "Timeout during dispatch",
                extra={**log_context, "error": str(exc), "timeout_seconds": self.timeout}
            )
            session.status = SessionStatus.FAILED
            session.outcome = {"error": str(exc), "kind": "timeout"}
            self.agent.status = AgentStatus.OFFLINE
            self.agent.save(update_fields=["status", "updated_at"])
        except requests.HTTPError as exc:
            response = exc.response
            status_code = response.status_code if response is not None else None
            logger.error(
                "HTTP error during dispatch",
                extra={**log_context, "error": str(exc), "status_code": status_code}
            )
            session.outcome = {"error": str(exc), "status_code": status_code, "kind": "http_error"}
            if status_code == 429:
                session.status = SessionStatus.RATE_LIMITED
                session.was_rate_limited = True
                self._record_rate_limit_event(session, {"type": "http_429", "status_code": 429})
                logger.warning(
                    "Rate limit hit during dispatch",
                    extra={**log_context, "status_code": status_code}
                )
            else:
                session.status = SessionStatus.FAILED
        except Exception as exc:
            logger.exception(
                "Unexpected relay dispatch failure",
                extra=log_context
            )
            session.status = SessionStatus.FAILED
            session.outcome = {"error": str(exc), "kind": "unexpected_error"}
        finally:
            self._finalize_session(session)
            logger.info(
                "Dispatch completed",
                extra={**log_context, "status": session.status, "duration_seconds": session.duration_seconds}
            )

        return session

    def _dispatch_stream(
        self,
        *,
        session: CyrusSession,
        request_url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> None:
        response = requests.post(request_url, headers=headers, json=payload, stream=True, timeout=self.timeout)
        response.raise_for_status()

        event_log: list[dict[str, Any]] = []
        relay_exit_code: int | None = None

        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line:
                continue

            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                logger.debug(
                    "Ignoring malformed relay chunk",
                    extra={**self._log_context(), "chunk": raw_line, "session_id": str(session.id)}
                )
                continue

            if not isinstance(event, dict):
                continue

            event_log.append(event)
            self._extract_session_metadata(session, event)

            event_type = event.get("type")
            if event_type == "relay_exit":
                relay_exit_code = self._coerce_int(event.get("code"))
                logger.debug(
                    "Relay exit",
                    extra={**self._log_context(), "session_id": str(session.id), "exit_code": relay_exit_code}
                )
            elif event_type == "relay_error":
                session.outcome = event
                logger.warning(
                    "Relay error event",
                    extra={**self._log_context(), "session_id": str(session.id), "error": event}
                )

            if self._is_rate_limit_event(event):
                retry_after = self._extract_retry_after_seconds(event)
                session.was_rate_limited = True
                session.rate_limit_wait_seconds = max(
                    session.rate_limit_wait_seconds,
                    retry_after,
                )
                self._record_rate_limit_event(session, event)
                logger.warning(
                    "Rate limit event in stream",
                    extra={
                        **self._log_context(),
                        "session_id": str(session.id),
                        "retry_after_seconds": retry_after
                    }
                )

        session.event_log = event_log

        if relay_exit_code == 0:
            session.status = SessionStatus.COMPLETED
        elif relay_exit_code is None and session.was_rate_limited:
            session.status = SessionStatus.RATE_LIMITED
        else:
            session.status = SessionStatus.FAILED

    def _dispatch_one_shot(
        self,
        *,
        session: CyrusSession,
        request_url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> None:
        response = requests.post(request_url, headers=headers, json=payload, timeout=self.timeout)
        response.raise_for_status()
        outcome = response.json()

        exit_code = self._coerce_int(outcome.get("code"))
        logger.debug(
            "One-shot execution completed",
            extra={**self._log_context(), "session_id": str(session.id), "exit_code": exit_code}
        )

        event = {"type": "exec_result", **outcome}
        session.event_log = [event]
        session.outcome = outcome
        session.status = SessionStatus.COMPLETED if exit_code == 0 else SessionStatus.FAILED
        self._extract_session_metadata(session, event)

    def _create_session(self) -> CyrusSession:
        return CyrusSession.objects.create(
            agent=self.agent,
            goal=self.goal,
            project=self.project,
            work_item=self.work_item,
            pool=self.pool,
            status=SessionStatus.RUNNING,
        )

    def _mark_work_item_in_progress(self) -> None:
        actor = self.project.workspace.owner if self.project and self.project.workspace_id else None
        report = _lifecycle.start(
            self.work_item,
            agent=self.agent,
            actor=actor,
        )
        if report.violations:
            logger.warning(
                "Work item %s started with violations: %s",
                self.work_item.id,
                "; ".join(v.message for v in report.violations),
            )

    def _finalize_session(self, session: CyrusSession) -> None:
        session.ended_at = timezone.now()
        started_at = session.started_at or session.created_at or session.ended_at
        session.duration_seconds = max((session.ended_at - started_at).total_seconds(), 0.0)

        # Use actual cost from provider if available (more accurate), else calculate from pool rates
        if hasattr(session, '_actual_cost_usd') and session._actual_cost_usd is not None:
            session.estimated_cost_usd = session._actual_cost_usd
        else:
            session.estimated_cost_usd = self.tracker.calculate_session_cost(session)

        session.save()

        self.tracker.record_session(session)
        summarize_session.delay(session.id)
        trace_session_to_langfuse.delay(session.id)
        meter_session.delay(session.id)

    def _build_session_name(self, session: CyrusSession) -> str:
        work_item_part = (
            f"{self.project.identifier}-{self.work_item.sequence_id}" if self.work_item and self.work_item.sequence_id else None
        )
        base = work_item_part or self.project.identifier or self.project.name.replace(" ", "-").lower()
        return f"{base}-{str(session.id)[:8]}"

    def _extract_session_metadata(self, session: CyrusSession, event: dict[str, Any]) -> None:
        session_identifier = (
            event.get("session_id")
            or event.get("acpx_session_id")
            or event.get("id")
            or self._nested_lookup(event, "session", "id")
            or self._nested_lookup(event, "session", "session_id")
        )
        if isinstance(session_identifier, str) and session_identifier:
            session.acpx_session_id = session_identifier

        if event.get("type") == "done" and isinstance(event.get("usage"), dict):
            usage = event["usage"]
            session.total_tokens = self._coerce_int(usage.get("total_tokens"))
            session.input_tokens = self._coerce_int(usage.get("input_tokens"))
            session.output_tokens = self._coerce_int(usage.get("output_tokens"))

            # Store cache tokens if model has the fields (TODO: add to CyrusSession model)
            if hasattr(session, 'cache_read_tokens'):
                session.cache_read_tokens = self._coerce_int(usage.get("cache_read_input_tokens"))
            if hasattr(session, 'cache_creation_tokens'):
                session.cache_creation_tokens = self._coerce_int(usage.get("cache_creation_input_tokens"))

            # Extract actual cost from provider (e.g., Claude Code's total_cost_usd)
            # This is more accurate than pool rate calculation because it accounts for:
            # - Cache token pricing (different rates)
            # - Multi-model usage (Haiku for tools, Sonnet for reasoning)
            # - Service tier adjustments
            if "total_cost_usd" in event:
                from decimal import Decimal
                try:
                    session._actual_cost_usd = Decimal(str(event["total_cost_usd"]))
                except (ValueError, TypeError):
                    pass  # Fall back to pool rate calculation

        model_name = event.get("model") or event.get("model_name") or self._nested_lookup(event, "usage", "model")
        if isinstance(model_name, str) and model_name:
            session.model_name = model_name

    def _record_rate_limit_event(self, session: CyrusSession, event: dict[str, Any]) -> None:
        from plane.db.models import RateLimitEvent

        RateLimitEvent.objects.create(
            pool=session.pool,
            agent=session.agent,
            session=session,
            status_code=self._coerce_int(event.get("status_code"), default=429),
            retry_after_seconds=self._extract_retry_after_seconds(event),
            request_count=self._coerce_int(
                event.get("request_count") or self._nested_lookup(event, "limits", "request_count"),
            ),
            token_count=self._coerce_int(
                event.get("token_count") or self._nested_lookup(event, "limits", "token_count"),
            ),
            metadata=event,
        )

    @staticmethod
    def _is_rate_limit_event(event: dict[str, Any]) -> bool:
        event_type = str(event.get("type", "")).lower()
        message = str(event.get("message", "")).lower()
        status_code = event.get("status_code")
        return status_code == 429 or "rate_limit" in event_type or "429" in message

    @staticmethod
    def _extract_retry_after_seconds(event: dict[str, Any]) -> float:
        retry_after = event.get("retry_after") or event.get("retry_after_seconds")
        if retry_after is None:
            retry_after = ACPXDispatcher._nested_lookup(event, "limits", "retry_after_seconds")
        try:
            return float(retry_after or 0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _nested_lookup(data: dict[str, Any], *path: str) -> Any:
        current: Any = data
        for key in path:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    @staticmethod
    def _coerce_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
