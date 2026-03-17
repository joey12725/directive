from __future__ import annotations

from celery import shared_task


@shared_task
def summarize_session(session_id):
    """Placeholder for async session summarization."""

    return str(session_id)


@shared_task
def trace_session_to_langfuse(session_id):
    """Placeholder for async Langfuse tracing."""

    return str(session_id)


@shared_task
def meter_session(session_id):
    """Placeholder for async session metering."""

    return str(session_id)
