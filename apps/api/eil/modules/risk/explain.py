"""Explanation service (plan §9.5, Phase 7, T7.7).

Builds the delivery-confidence fact sheet from the Monte Carlo result and
narrates it with the LLM ("Ask EIL" style narration), with a numbers guard and
a template fallback when the LLM is unavailable (R12: AI is optional).
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eil.core.config import get_settings
from eil.core.errors import AppError
from eil.modules.execution.models import WorkItem
from eil.modules.risk import engine
from eil.modules.risk.service import recalc_confidence

_NUMBER_RE = re.compile(r"\d+\.?\d*")


def _numbers_in_text(text: str) -> set[float]:
    numbers = set()
    for match in _NUMBER_RE.findall(text):
        try:
            numbers.add(float(match))
        except ValueError:
            continue
    return numbers


def _numbers_in_fact_sheet(fact_sheet: dict[str, Any]) -> set[float]:
    numbers: set[float] = set()
    for value in fact_sheet.values():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            numbers.add(float(value))
        elif isinstance(value, dict):
            numbers |= _numbers_in_fact_sheet(value)
        elif isinstance(value, list):
            for row in value:
                if isinstance(row, dict):
                    numbers |= _numbers_in_fact_sheet(row)
    return numbers


def _template_narrative(fact_sheet: dict[str, Any]) -> str:
    confidence = fact_sheet["confidence"]
    title = fact_sheet["title"]
    p50 = fact_sheet.get("p50_finish")
    criticality = fact_sheet.get("criticality")
    text = f"Delivery confidence for '{title}' is {confidence:.2f}."
    if p50 is not None:
        text += f" The median finish is {p50:.0f} days."
    if criticality is not None:
        text += f" The criticality index is {criticality:.2f}."
    return text


async def explain_confidence(
    session: AsyncSession, ctx: Any, item_id: UUID, *, mc_result: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Fact sheet + narrated explanation for a delivery confidence (plan §9.5, T7.7)."""
    network = await engine.build_schedule_network(session)
    result = mc_result or engine.run_monte_carlo(network, iterations=5000, seed=42)
    item = (await session.execute(select(WorkItem).where(WorkItem.id == item_id))).scalars().first()
    if item is None:
        raise AppError(404, "not_found", "Not found", "Item not found.")
    horizon_start = item.planned_start or date.today()
    committed = item.baseline_end or item.planned_end
    committed_days = (committed - horizon_start).days + 1 if committed else None
    confidence = engine.delivery_confidence(result["finish"], item_id, float(committed_days or 0))
    predecessor_rows = []
    for pred_id in network.nodes.get(
        item_id, engine.ScheduleNode(id=item_id, title="", type="", duration_days=0)
    ).predecessors:
        predecessor_rows.append(
            {
                "id": str(pred_id),
                "title": network.nodes[pred_id].title,
                "p50_finish": result["p50"].get(pred_id),
                "finish_p80": result["p80"].get(pred_id),
                "finish_p90": result["p90"].get(pred_id),
            }
        )
    fact_sheet: dict[str, Any] = {
        "item_id": str(item_id),
        "title": item.title,
        "committed_days": committed_days,
        "confidence": float(confidence),
        "p50_finish": result["p50"].get(item_id),
        "finish_p80": result["p80"].get(item_id),
        "finish_p90": result["p90"].get(item_id),
        "criticality": result["criticality_index"].get(item_id, 0.0),
        "sensitivity": result["sensitivity"].get(item_id),
        "predecessors": predecessor_rows,
    }
    narrative = await _narrate(fact_sheet)
    return {
        "item_id": item_id,
        "title": item.title,
        "confidence": confidence,
        "fact_sheet": fact_sheet,
        "narrative": narrative,
    }


async def _narrate(fact_sheet: dict[str, Any]) -> str | None:
    """LLM narrator with a numbers guard; template fallback (plan §9.5, T7.7)."""
    settings = get_settings()
    if not settings.ai_enabled:
        return None
    from eil.ai.gateway import get_gateway

    messages = [
        {
            "role": "system",
            "content": (
                "You narrate a short delivery-confidence explanation from a numeric "
                "fact sheet. Quote only numbers that appear in the fact sheet."
            ),
        },
        {"role": "user", "content": repr(fact_sheet)},
    ]
    try:
        result = (
            await get_gateway()
            .client()
            .chat(messages, alias="strong", temperature=0.2, max_tokens=200)
        )
        text = result.content.strip()
    except Exception:
        return None
    narrative_numbers = _numbers_in_text(text)
    if narrative_numbers and not narrative_numbers.issubset(_numbers_in_fact_sheet(fact_sheet)):
        return None
    return text or None


async def recalc_and_explain(
    session: AsyncSession, ctx: Any, item_ids: list[UUID]
) -> dict[UUID, Decimal]:
    """Recalculate confidence for affected items (T7.5 core) and return them."""
    return await recalc_confidence(session, item_ids)
