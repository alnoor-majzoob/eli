"""Identity, organisation and role-permission models."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import JSON, Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from eil.core.db import Base
from eil.core.models import IdMixin, TimestampMixin


class OrgUnit(IdMixin, TimestampMixin, Base):
    __tablename__ = "org_unit"

    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    parent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("org_unit.id", ondelete="SET NULL"), nullable=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "app_user"

    subject: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    org_unit_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("org_unit.id", ondelete="SET NULL"), nullable=True
    )
    roles: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class RolePermission(Base):
    __tablename__ = "role_permission"

    role: Mapped[str] = mapped_column(String(50), primary_key=True)
    permission: Mapped[str] = mapped_column(String(100), primary_key=True)
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="own_org")

    __table_args__ = (UniqueConstraint("role", "permission", name="uq_role_permission"),)
