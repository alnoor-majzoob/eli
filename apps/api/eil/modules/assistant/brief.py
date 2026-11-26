"""Executive brief (plan Phase 8, T8.4).

Auto-generated executive brief (weekly/on-demand) grounded in fact sheets with
a numbers guard (R3): LLM narration is accepted only when every number in the
output appears in the fact sheet; a template fallback is used otherwise.
PDF export is not implemented yet (no PDF renderer in the stack).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from eil.ai.gateway import get_gateway
from eil.core.config import get_settings
from eil.core.models import utcnow
from eil.modules.identity.rbac import PermissionContext
from eil.modules.metrics import service as metrics_service
from eil.modules.risk.explain import _numbers_in_fact_sheet, _numbers_in_text


def _fact_sheet(summary: dict[str, Any]) -> dict[str, Any]:
    committed = summary["committed"]
    return {
        "committed_total": float(committed["total"]),
        "avg_confidence": committed["avg_confidence"] or 0.0,
        "red_commitments": sum(
            1 for row in committed["by_org_unit"] if (row["min_confidence"] or 0) < 0.5
        ),
        "top_priorities": [
            (row["title"], float(row["confidence"])) for row in summary["priorities"][:5]
        ],
        "capacity_overloads": len(summary["capacity_constraints"]),
        "red_weeks": sum(1 for row in summary["capacity_constraints"] if row["status"] == "red"),
        "at_risk": [(row["title"], float(row["confidence"])) for row in summary["at_risk"]],
        "objectives_at_risk": [
            (row["title"], float(row["confidence"]))
            for row in summary["strategic_outcomes"]["objectives"]
            if row["confidence"] < 0.8
        ],
        "interventions_open": len(summary["interventions"]),
    }


async def _narrate(fact_sheet: dict[str, Any]) -> str | None:
    settings = get_settings()
    if not settings.ai_enabled:
        return None
    messages = [
        {
            "role": "system",
            "content": (
                "You write a concise executive summary from a numeric fact sheet. "
                "Quote only numbers from the fact sheet."
            ),
        },
        {"role": "user", "content": repr(fact_sheet)},
    ]
    try:
        result = (
            await get_gateway()
            .client()
            .chat(messages, alias="strong", temperature=0.2, max_tokens=600)
        )
        text = result.content.strip()
    except Exception:
        return None
    numbers = _numbers_in_text(text)
    if numbers and not numbers.issubset(_numbers_in_fact_sheet(fact_sheet)):
        return None
    return text or None


def _render_html(summary: dict[str, Any], narrative: str | None) -> str:
    committed = summary["committed"]
    top_titles = ", ".join(row["title"] for row in summary["priorities"][:5]) or "none"
    bullets = [
        f"<li>Commitments: {committed['total']} (average confidence "
        f"{committed['avg_confidence']})</li>",
        f"<li>Top priorities: {top_titles}</li>",
        f"<li>Capacity: {len(summary['capacity_constraints'])} constrained weeks</li>",
        f"<li>At risk: {len(summary['at_risk'])} items</li>",
        f"<li>Interventions: {len(summary['interventions'])} open</li>",
    ]
    header = "<html><head><meta charset='utf-8'><title>Executive brief</title></head><body>"
    fallback = "Executive summary not generated (AI disabled or unavailable)."
    return "".join(
        [
            header,
            "<h1>Executive Brief</h1>",
            f"<p>As of {utcnow().date().isoformat()}</p>",
            f"<h2>Summary</h2><p>{narrative or fallback}</p>",
            f"<h2>Status</h2><ul>{''.join(bullets)}</ul>",
            "</body></html>",
        ]
    )


async def executive_brief(session: AsyncSession, ctx: PermissionContext) -> dict[str, Any]:
    """Executive brief (plan Phase 8, T8.4): fact sheet + numbers-guarded narrative."""
    summary = await metrics_service.executive_summary(session, ctx)
    fact_sheet = _fact_sheet(summary)
    narrative = await _narrate(fact_sheet)
    return {
        "as_of": summary["as_of"],
        "html": _render_html(summary, narrative),
        "text": narrative,
        "fact_sheet": fact_sheet,
    }
