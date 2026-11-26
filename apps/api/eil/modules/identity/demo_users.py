"""Synthetic demo identities (rule R11: never real people)."""

from __future__ import annotations

from dataclasses import dataclass

from eil.core.security import Principal


@dataclass(frozen=True)
class DemoUser:
    role: str
    subject: str
    name: str
    email: str
    org_unit_id: str

    def to_principal(self) -> Principal:
        return Principal(
            subject=self.subject,
            name=self.name,
            email=self.email,
            roles=[self.role],
            org_unit_id=self.org_unit_id,
        )


DEMO_USERS: tuple[DemoUser, ...] = (
    DemoUser("executive", "demo-executive", "Fatma Al-Hinai", "fatma@example.invalid", "exec"),
    DemoUser(
        "portfolio_manager",
        "demo-portfolio",
        "Salim Al-Balushi",
        "salim@example.invalid",
        "pmo",
    ),
    DemoUser(
        "project_manager",
        "demo-project",
        "Aisha Al-Zadjali",
        "aisha@example.invalid",
        "projects",
    ),
    DemoUser("dept_head", "demo-dept-head", "Khalid Al-Riyami", "khalid@example.invalid", "ops"),
    DemoUser(
        "resource_manager",
        "demo-resource",
        "Mariam Al-Habsi",
        "mariam@example.invalid",
        "pmo",
    ),
    DemoUser(
        "team_member", "demo-team", "Yousuf Al-Farsi", "yousuf@example.invalid", "maintenance"
    ),
    DemoUser("pmo_analyst", "demo-pmo", "Noor Al-Saadi", "noor@example.invalid", "pmo"),
    DemoUser("ai_reviewer", "demo-ai", "Huda Al-Kindi", "huda@example.invalid", "engineering"),
    DemoUser(
        "integration_admin",
        "demo-integration",
        "Ahmed Al-Mamari",
        "ahmed@example.invalid",
        "it",
    ),
    DemoUser("auditor", "demo-auditor", "Layla Al-Amri", "layla@example.invalid", "audit"),
    DemoUser("admin", "demo-admin", "System Administrator", "admin@example.invalid", "it"),
)

DEMO_USERS_BY_ROLE: dict[str, DemoUser] = {user.role: user for user in DEMO_USERS}


def public_roles() -> list[dict[str, str]]:
    return [
        {
            "role": user.role,
            "name": user.name,
            "email": user.email,
            "org_unit_id": user.org_unit_id,
        }
        for user in DEMO_USERS
    ]
