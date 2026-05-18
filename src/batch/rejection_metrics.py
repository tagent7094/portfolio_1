"""v6 rejection metrics accumulator.

Per ORCHESTRATOR_SPEC §"Pack rejection economics". Tracks per-run:
- total_packs_attempted, shipped, rejected
- rejection_rate
- cost_per_shipped_pack
- rejection_reasons_breakdown

Surfaced via `to_dict()` so the orchestrator can include it in the final
output metadata block.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class RejectionMetrics:
    total_packs_attempted: int = 0
    total_packs_shipped: int = 0
    total_packs_rejected: int = 0
    total_cost_spent_usd: float = 0.0
    rejection_reasons: Counter = field(default_factory=Counter)
    cost_per_shipped_pack: float = 0.0

    def record_attempt(self) -> None:
        self.total_packs_attempted += 1

    def record_ship(self, pack_cost_usd: float = 0.0) -> None:
        self.total_packs_shipped += 1
        self.total_cost_spent_usd += pack_cost_usd
        self._recompute()

    def record_rejection(self, primary_reason: str, pack_cost_usd: float = 0.0) -> None:
        self.total_packs_rejected += 1
        if primary_reason:
            self.rejection_reasons[primary_reason] += 1
        self.total_cost_spent_usd += pack_cost_usd
        self._recompute()

    def _recompute(self) -> None:
        if self.total_packs_shipped > 0:
            self.cost_per_shipped_pack = self.total_cost_spent_usd / self.total_packs_shipped
        else:
            self.cost_per_shipped_pack = 0.0

    @property
    def rejection_rate(self) -> float:
        if self.total_packs_attempted == 0:
            return 0.0
        return self.total_packs_rejected / self.total_packs_attempted

    def to_dict(self) -> dict:
        return {
            "total_packs_attempted": self.total_packs_attempted,
            "total_packs_shipped": self.total_packs_shipped,
            "total_packs_rejected": self.total_packs_rejected,
            "rejection_rate": round(self.rejection_rate, 3),
            "total_cost_spent_usd": round(self.total_cost_spent_usd, 4),
            "cost_per_shipped_pack": round(self.cost_per_shipped_pack, 4),
            "rejection_reasons_breakdown": dict(self.rejection_reasons),
        }
