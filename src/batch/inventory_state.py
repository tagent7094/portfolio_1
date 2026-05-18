"""PackInventoryState — v6 consumable inventory across sequential generate calls.

Per ORCHESTRATOR_SPEC §1: anchors_available and voice_marker_budget are mutable
across the 9 sequential `_generate_one_post` calls in a pack. When a post
consumes an anchor or a voice marker, the inventory is mutated so subsequent
posts cannot reuse them.

The inventory is initialized once per pack from the anchor_inventory dict
(produced by `00_anchor_inventory.txt` once per founder per run) and the
voice_marker_budget (produced by `01_voice_load.txt` once per batch).
"""

from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PackInventoryState:
    anchors_available: list[dict] = field(default_factory=list)
    anchors_used_in_pack: list[dict] = field(default_factory=list)
    voice_marker_budget: dict[str, int] = field(default_factory=dict)
    voice_markers_used_in_pack: list[dict] = field(default_factory=list)
    pack_history: list[dict] = field(default_factory=list)

    @classmethod
    def from_anchor_inventory(
        cls,
        anchor_inventory: dict,
        voice_marker_budget: list[dict],
        pack_history: list[dict] | None = None,
    ) -> "PackInventoryState":
        """Build a fresh inventory state for a pack.

        anchor_inventory is the full v6 dict from `00_anchor_inventory.txt`.
        voice_marker_budget is the v6 voice_markers_with_budget list from
        `01_voice_load.txt`. pack_history is the rolling 30-day record.
        """
        anchors = list(anchor_inventory.get("anchor_inventory", []) or [])
        # deepcopy so consumption doesn't mutate the shared inventory dict.
        anchors = [deepcopy(a) for a in anchors]

        marker_budget: dict[str, int] = {}
        for m in (voice_marker_budget or []):
            mid = m.get("marker_id") or m.get("marker_text", "")
            if mid:
                marker_budget[mid] = int(m.get("max_uses_per_pack", 1) or 1)

        return cls(
            anchors_available=anchors,
            anchors_used_in_pack=[],
            voice_marker_budget=marker_budget,
            voice_markers_used_in_pack=[],
            pack_history=list(pack_history or []),
        )

    # ── Consumption helpers ──

    def consume_anchor(self, anchor_id: str | None) -> dict | None:
        """Move an anchor from available → used. Returns the consumed record
        (or None if no match — caller can decide whether to warn).

        Match order:
          1. Exact `anchor_id` match (preferred; transpose.txt declares slugs).
          2. Fuzzy text match — when the LLM emitted the full anchor_text
             instead of the slug. We compare a normalized prefix of the
             passed-in value against each anchor's `anchor_text` (case-
             insensitive, first 60 chars). Saves the warning + missed
             consumption path from the v6.0 era where most posts emitted text.
        """
        if not anchor_id:
            return None

        # Step 1: exact slug match.
        for i, a in enumerate(self.anchors_available):
            if a.get("anchor_id") == anchor_id:
                consumed = self.anchors_available.pop(i)
                self.anchors_used_in_pack.append(consumed)
                logger.info(
                    "[inventory] consumed anchor %s (%d remaining)",
                    anchor_id, len(self.anchors_available),
                )
                return consumed

        # Step 2: fuzzy text match. Sometimes the generator emits the full
        # anchor text instead of the slug. Match against anchor_text prefix.
        needle = anchor_id.strip().lower()
        if len(needle) >= 12:
            probe = needle[:60]
            for i, a in enumerate(self.anchors_available):
                hay = (a.get("anchor_text") or "").strip().lower()
                if not hay:
                    continue
                if hay.startswith(probe) or probe in hay[:120]:
                    consumed = self.anchors_available.pop(i)
                    self.anchors_used_in_pack.append(consumed)
                    logger.info(
                        "[inventory] consumed anchor %s via fuzzy text match (declared as text, matched slug=%r, %d remaining)",
                        consumed.get("anchor_id", "?"), anchor_id[:40], len(self.anchors_available),
                    )
                    return consumed

        logger.warning(
            "[inventory] anchor_id %r not found in anchors_available "
            "(post claimed to use it but inventory lacks the record; "
            "fuzzy text match also failed)",
            anchor_id[:80],
        )
        return None

    def consume_voice_marker(self, marker_id: str | None) -> None:
        """Decrement a marker's remaining budget. When 0, mark fully consumed."""
        if not marker_id:
            return
        if marker_id not in self.voice_marker_budget:
            logger.warning(
                "[inventory] marker_id %r not in voice_marker_budget", marker_id,
            )
            return
        self.voice_marker_budget[marker_id] = max(0, self.voice_marker_budget[marker_id] - 1)
        self.voice_markers_used_in_pack.append({"marker_id": marker_id})
        if self.voice_marker_budget[marker_id] == 0:
            logger.info("[inventory] marker %s exhausted (budget=0)", marker_id)

    # ── Query helpers ──

    def remaining_anchors_for_mechanic(self, mechanic: str) -> list[dict]:
        """Filter anchors_available to those whose supported_mechanics contain `mechanic`.

        v6.1 schema: each `supported_mechanics` entry is a dict
        `{family, sub_mechanic, example_phrasing}`. We match against either
        field — caller passes whichever they care about (family OR sub_mechanic).

        Back-compat: tolerates v6's bare-string entries if a stale cache exists.
        """
        if not mechanic:
            return list(self.anchors_available)
        out: list[dict] = []
        for a in self.anchors_available:
            supports = a.get("supported_mechanics", []) or []
            for sm in supports:
                matched = False
                if isinstance(sm, dict):
                    if sm.get("family") == mechanic or sm.get("sub_mechanic") == mechanic:
                        matched = True
                elif isinstance(sm, str):
                    # v6 back-compat: bare-string entries from old caches.
                    if sm == mechanic:
                        matched = True
                if matched:
                    out.append(a)
                    break
        return out

    def voice_marker_budget_remaining(self) -> list[dict]:
        """Return the marker budget as a list with uses_remaining > 0."""
        out: list[dict] = []
        for mid, remaining in self.voice_marker_budget.items():
            if remaining > 0:
                out.append({"marker_id": mid, "uses_remaining": remaining})
        return out

    def voice_markers_consumed_summary(self) -> list[dict]:
        """Aggregate consumed markers as [{marker_id, uses}]."""
        counts: dict[str, int] = {}
        for u in self.voice_markers_used_in_pack:
            mid = u.get("marker_id", "")
            if mid:
                counts[mid] = counts.get(mid, 0) + 1
        return [{"marker_id": k, "uses": v} for k, v in counts.items()]
