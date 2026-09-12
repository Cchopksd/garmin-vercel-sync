from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GarminSnapshot:
    date: str
    stats: dict[str, Any]
    heart_rate: dict[str, Any]
    sleep: dict[str, Any]
    hrv: dict[str, Any] | None
    stress: dict[str, Any]
    body_battery: list[dict[str, Any]]
    respiration: dict[str, Any] = field(default_factory=dict)
    spo2: dict[str, Any] = field(default_factory=dict)
    intensity: dict[str, Any] = field(default_factory=dict)
    all_day_stress: dict[str, Any] = field(default_factory=dict)
    training_readiness: dict[str, Any] | None = None
    training_status: dict[str, Any] = field(default_factory=dict)
    activities: list[dict[str, Any]] = field(default_factory=list)
