"""In-process domain event bus (handlers registered per event type)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from eil.core.outbox import OutboxEvent

logger = structlog.get_logger(__name__)

EventHandler = Callable[["OutboxEvent"], Awaitable[None]]

_handlers: dict[str, list[EventHandler]] = defaultdict(list)


def register_handler(event_type: str, handler: EventHandler) -> None:
    """Register an async handler for a domain event type."""
    _handlers[event_type].append(handler)


def clear_handlers() -> None:
    """Remove all handlers (tests)."""
    _handlers.clear()


def registered_event_types() -> list[str]:
    return sorted(_handlers)


async def handle_event(event: OutboxEvent) -> None:
    """Dispatch one event to every registered handler."""
    handlers = _handlers.get(event.event_type, [])
    if not handlers:
        logger.debug("outbox_no_handler", event_type=event.event_type, event_id=str(event.id))
        return
    for handler in handlers:
        await handler(event)
