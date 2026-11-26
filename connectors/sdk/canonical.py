"""Connector SDK — the package concrete connectors and simulators build on.

Public surface: canonical record models (plan §7.3, T3.2), the ``Connector``
protocol (T3.1), the declarative YAML field-mapping engine, the connector
registry (T3.4) and the write-back record types (T3.5/T3.7).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

# --- Canonical integration models (plan §7.3, T3.2) -------------------------


@dataclass(frozen=True)
class CanonicalProject:
    name: str
    description: str | None = None
    status: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CanonicalActivity:
    name: str
    duration_days: int | None = None
    description: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CanonicalMilestone:
    name: str
    due_date: date | None = None
    description: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CanonicalWorkOrder:
    work_order_number: str
    asset_id: str | None = None
    status: str | None = None
    priority: str | None = None
    due_date: date | None = None
    description: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CanonicalPerson:
    name: str
    email: str | None = None
    title: str | None = None
    department: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CanonicalCertification:
    name: str
    person: str | None = None
    issuer: str | None = None
    expiry_date: date | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CanonicalMeeting:
    title: str
    start_time: datetime | None = None
    end_time: datetime | None = None
    organizer: str | None = None
    attendees: list[str] = field(default_factory=list)
    url: str | None = None
    transcript_url: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CanonicalMessage:
    sender: str
    subject: str
    body: str
    received_at: datetime | None = None
    flags: list[str] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CanonicalDocument:
    title: str
    url: str
    path: str
    size_bytes: int | None = None
    description: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
