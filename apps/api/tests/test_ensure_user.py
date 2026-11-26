"""ensure_user race-safety + idempotency (user-test finding: approvals/inbox 500).

The dev database crashed with ``UNIQUE constraint failed: org_unit.code`` on
``GET /api/v1/approvals/inbox`` — concurrent requests both passed the
select-then-insert check before either committed. ``ensure_user`` is now
race-safe: on the ``IntegrityError`` it re-selects the concurrently created
row instead of failing the request.
"""

from __future__ import annotations

from sqlalchemy import select

from eil.core.security import Principal
from eil.modules.identity.demo_users import DEMO_USERS_BY_ROLE
from eil.modules.identity.models import OrgUnit
from eil.modules.identity.rbac import _get_or_create_org_unit, ensure_user


def _principal(subject: str) -> Principal:
    demo = next(iter(DEMO_USERS_BY_ROLE.values()))
    return Principal(
        subject=subject,
        name="Race User",
        email=f"{subject}@eil.test",
        roles=["executive"],
        org_unit_id=demo.org_unit_id,
    )


async def test_ensure_user_idempotent(app) -> None:
    principal = _principal("user-race-test")
    async with app.state.session_factory() as session:
        user1 = await ensure_user(session, principal)
    async with app.state.session_factory() as session:
        user2 = await ensure_user(session, principal)
    assert user1.id == user2.id
    async with app.state.session_factory() as session:
        org_unit = (
            await session.execute(select(OrgUnit).where(OrgUnit.code == principal.org_unit_id))
        ).scalar_one()
        assert user1.org_unit_id == org_unit.id


async def test_get_or_create_org_unit_returns_existing(app) -> None:
    async with app.state.session_factory() as session:
        code = "race-org-unit"
        first = await _get_or_create_org_unit(session, code, "First")
        second = await _get_or_create_org_unit(session, code, "Second")
        assert first.id == second.id
        assert second.name == "First"
