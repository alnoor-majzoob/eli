"""Delay-propensity model (plan §9.5, Phase 7, T7.3).

Linear-logistic-regression baseline predicting the probability that an item
finishes late beyond tolerance; features per plan §9.5; calibration with an
isotonic-regression implementation; top-k feature drivers as the v1 "SHAP".
Production upgrades to gradient boosting + real SHAP (plan §9.5).
"""

from __future__ import annotations

import math
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eil.core.models import utcnow
from eil.modules.execution.models import Allocation, WorkItem, WorkLink, WorkType

TOLERANCE_DAYS = 3
TRIAGE_TYPES = (WorkType.TASK, WorkType.PROJECT, WorkType.MILESTONE)

FEATURE_NAMES: tuple[str, ...] = (
    "planned_duration_days",
    "completed_percent",
    "forecast_slippage_days",
    "dependency_fan_in",
    "dependency_fan_out",
    "owner_load_hours",
    "owner_on_time_rate",
    "age_days",
    "scope_change_count",
    "delay_history_rate",
)


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    exp_z = math.exp(z)
    return exp_z / (1.0 + exp_z)


def isotonic_regression(y: list[float], weights: list[float] | None = None) -> list[float]:
    """Pool Adjacent Violators: fitted values, non-decreasing (isotonic constraint)."""
    blocks: list[dict[str, float]] = []
    for i, value in enumerate(y):
        weight = 1.0 if weights is None else float(weights[i])
        blocks.append({"value": float(value), "weight": weight, "count": 1.0})
        while len(blocks) >= 2 and blocks[-2]["value"] > blocks[-1]["value"]:
            top = blocks.pop()
            prev = blocks.pop()
            merged_weight = prev["weight"] + top["weight"]
            blocks.append(
                {
                    "value": (prev["value"] * prev["weight"] + top["value"] * top["weight"])
                    / merged_weight,
                    "weight": merged_weight,
                    "count": prev["count"] + top["count"],
                }
            )
    fitted: list[float] = []
    for block in blocks:
        fitted.extend([block["value"]] * int(block["count"]))
    return fitted


class DelayPropensityModel:
    """Linear logistic regression over :data:`FEATURE_NAMES` (v1; GBDT upgrade)."""

    def __init__(self, weights: list[float] | None = None, intercept: float = 0.0):
        fallback = [0.0] * len(FEATURE_NAMES)
        self.weights: list[float] = list(weights or fallback)
        self.intercept = intercept

    def predict_probability(self, features: dict[str, float]) -> float:
        z = self.intercept
        for name, weight in zip(FEATURE_NAMES, self.weights, strict=False):
            z += weight * float(features.get(name, 0.0))
        return _sigmoid(z)

    @classmethod
    def train(
        cls,
        rows: list[tuple[dict[str, float], int]],
        iterations: int = 500,
        learning_rate: float = 0.05,
    ) -> DelayPropensityModel:
        """Gradient descent on the log-loss (R3-independent demo model)."""
        weights = [0.0] * len(FEATURE_NAMES)
        intercept = 0.0
        n = max(len(rows), 1)
        for _ in range(iterations):
            grad_w = [0.0] * len(FEATURE_NAMES)
            grad_b = 0.0
            for features, label in rows:
                x = [float(features.get(name, 0.0)) for name in FEATURE_NAMES]
                z = intercept + sum(w * xi for w, xi in zip(weights, x, strict=False))
                error = _sigmoid(z) - float(label)
                for i in range(len(FEATURE_NAMES)):
                    grad_w[i] += error * x[i]
                grad_b += error
            for i in range(len(FEATURE_NAMES)):
                weights[i] -= learning_rate * grad_w[i] / n
            intercept -= learning_rate * grad_b / n
        return cls(weights, intercept)


def calibrate_delay_model(
    model: DelayPropensityModel, rows: list[tuple[dict[str, float], int]]
) -> list[tuple[float, float]]:
    """Isotonic calibration: sorted (raw probability, isotonic probability) pairs (§9.5)."""
    probabilities = [model.predict_probability(features) for features, _ in rows]
    labels = [float(label) for _, label in rows]
    fitted = isotonic_regression(probabilities, labels)
    return sorted(zip(probabilities, fitted, strict=True))


def top_k_drivers(
    model: DelayPropensityModel, features: dict[str, float], k: int = 5
) -> list[dict[str, Any]]:
    """Top-k feature drivers by absolute contribution (v1 SHAP replacement)."""
    entries: list[dict[str, Any]] = []
    for name, weight in zip(FEATURE_NAMES, model.weights, strict=False):
        value = float(features.get(name, 0.0))
        entries.append({"feature": name, "value": value, "contribution": weight * value})
    entries.sort(key=lambda row: -abs(row["contribution"]))
    return entries[:k]


async def build_features(session: AsyncSession, item: WorkItem) -> dict[str, float]:
    """Feature vector per plan §9.5 (float features)."""
    duration = 0.0
    if item.planned_start is not None and item.planned_end is not None:
        duration = float((item.planned_end - item.planned_start).days + 1)
    attributes = item.attributes or {}
    completed = float(attributes.get("completed_percent") or 0)
    slippage = 0.0
    if item.forecast_end is not None and item.planned_end is not None:
        slippage = float((item.forecast_end - item.planned_end).days)
    fan_in = fan_out = 0
    fan_in_rows = (
        (
            await session.execute(
                select(WorkLink).where(
                    WorkLink.dst_id == item.id,
                    WorkLink.link_type == "depends_on",
                    WorkLink.status == "active",
                )
            )
        )
        .scalars()
        .all()
    )
    fan_in = len(fan_in_rows)
    fan_out_rows = (
        (
            await session.execute(
                select(WorkLink).where(
                    WorkLink.src_id == item.id,
                    WorkLink.link_type == "depends_on",
                    WorkLink.status == "active",
                )
            )
        )
        .scalars()
        .all()
    )
    fan_out = len(fan_out_rows)
    owner_load = 0.0
    owner_rows: list[Allocation] = []
    if item.owner_id is not None:
        owner_rows = list(
            (
                await session.execute(
                    select(Allocation).where(
                        Allocation.resource_id == item.owner_id,
                        Allocation.scenario_id.is_(None),
                        Allocation.hours_per_week.isnot(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        owner_load = float(sum((r.hours_per_week or 0) for r in owner_rows))
    on_time = 0
    on_time_total = 0
    if item.owner_id is not None:
        commitments = (
            (
                await session.execute(
                    select(WorkItem).where(
                        WorkItem.type == WorkType.COMMITMENT,
                        WorkItem.owner_id == item.owner_id,
                        WorkItem.baseline_end.isnot(None),
                        WorkItem.forecast_end.isnot(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        on_time_total = len(commitments)
        on_time = sum(
            1
            for c in commitments
            if c.forecast_end is not None
            and c.baseline_end is not None
            and c.forecast_end <= c.baseline_end + timedelta(days=TOLERANCE_DAYS)
        )
    return {
        "planned_duration_days": duration,
        "completed_percent": completed,
        "forecast_slippage_days": slippage,
        "dependency_fan_in": float(fan_in),
        "dependency_fan_out": float(fan_out),
        "owner_load_hours": owner_load,
        "owner_on_time_rate": (on_time / on_time_total) if on_time_total else 0.0,
        "age_days": float((utcnow().date() - item.created_at.date()).days)
        if item.created_at
        else 0.0,
        "scope_change_count": float(attributes.get("scope_change_count") or 0),
        "delay_history_rate": 0.0,
    }


async def training_rows(
    session: AsyncSession, limit: int = 200
) -> list[tuple[dict[str, float], int]]:
    """Training rows: features + labels (1 = delayed beyond tolerance) from real data."""
    items = (
        (
            await session.execute(
                select(WorkItem)
                .where(
                    WorkItem.type.in_(TRIAGE_TYPES),
                    WorkItem.planned_start.isnot(None),
                    WorkItem.planned_end.isnot(None),
                )
                .order_by(WorkItem.id)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    rows: list[tuple[dict[str, float], int]] = []
    for item in items:
        features = await build_features(session, item)
        delayed = (
            item.forecast_end is not None
            and item.planned_end is not None
            and item.forecast_end > item.planned_end + timedelta(days=TOLERANCE_DAYS)
        )
        rows.append((features, 1 if delayed else 0))
    return rows


async def predict_item_delay(
    session: AsyncSession, model: DelayPropensityModel, item: WorkItem
) -> dict[str, Any]:
    """Prediction + top-k drivers for one item (plan §9.5)."""
    features = await build_features(session, item)
    return {
        "item_id": item.id,
        "probability": model.predict_probability(features),
        "drivers": top_k_drivers(model, features),
    }


def train_delay_model(rows: list[tuple[dict[str, float], int]]) -> DelayPropensityModel:
    return DelayPropensityModel.train(rows)


def default_delay_model() -> DelayPropensityModel:
    """Untrained fallback model (all-zero weights → 0.5 probability)."""
    return DelayPropensityModel()
