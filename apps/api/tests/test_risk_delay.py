"""Delay-propensity model (plan §9.5, Phase 7, T7.3)."""

from __future__ import annotations

from datetime import date

from eil.modules.execution.models import WorkItem, WorkType
from eil.modules.risk import delay


def test_isotonic_regression_monotone() -> None:
    y = [0.9, 0.1, 0.8, 0.2, 0.5]
    fitted = delay.isotonic_regression(y)
    assert fitted == sorted(fitted)
    assert all(0.0 <= value <= 1.0 for value in fitted)


def test_train_and_predict_probability_in_range() -> None:
    rows = [
        ({"forecast_slippage_days": 0.0}, 0),
        ({"forecast_slippage_days": 1.0}, 0),
        ({"forecast_slippage_days": 2.0}, 0),
        ({"forecast_slippage_days": 3.0}, 0),
        ({"forecast_slippage_days": 20.0}, 1),
        ({"forecast_slippage_days": 22.0}, 1),
    ]
    model = delay.DelayPropensityModel.train(rows)
    probabilities = [
        model.predict_probability({"forecast_slippage_days": float(v)}) for v in (0, 22)
    ]
    assert all(0.0 <= p <= 1.0 for p in probabilities)
    assert probabilities[1] > probabilities[0]


async def test_build_features(app) -> None:
    async with app.state.session_factory() as session:
        item = WorkItem(
            type=WorkType.TASK,
            title="Feature test",
            status="active",
            planned_start=date(2026, 12, 1),
            planned_end=date(2026, 12, 11),
        )
        session.add(item)
        await session.flush()
        features = await delay.build_features(session, item)

    assert features["planned_duration_days"] == 11
    assert features["forecast_slippage_days"] == 0
    assert features["dependency_fan_in"] == 0
    assert set(features) >= set(delay.FEATURE_NAMES)


def test_top_k_drivers() -> None:
    model = delay.DelayPropensityModel(weights=[1.0, 0.0, -0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    drivers = delay.top_k_drivers(
        model, {"planned_duration_days": 10.0, "forecast_slippage_days": 5.0}, k=2
    )
    assert drivers[0]["feature"] == "planned_duration_days"
    assert drivers[0]["contribution"] == 10.0


def test_calibrate_returns_isotonic_pairs() -> None:
    model = delay.DelayPropensityModel(weights=[0.0] * len(delay.FEATURE_NAMES), intercept=0.0)
    rows = [
        ({"forecast_slippage_days": 5.0}, 1),
        ({"forecast_slippage_days": 1.0}, 0),
        ({"forecast_slippage_days": 5.0}, 1),
    ]
    table = delay.calibrate_delay_model(model, rows)
    assert table == sorted(table)
    assert all(0.0 <= p <= 1.0 for p, _ in table)
