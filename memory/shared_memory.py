# ============================================================
# KLEOS — Shared Memory (in-memory store)
# Converted from: src/lib/memory/shared-memory.ts
# NOTE: localStorage replaced with in-memory dict (server-side compatible)
# ============================================================

import uuid
import time
import json
from typing import Optional, Literal
from dataclasses import dataclass, field

MemoryType = Literal[
    "brand_kit",
    "winning_creatives",
    "competitor_patterns",
    "audience_insights",
    "kpi_targets",
    "approval_history",
    "portfolio_gaps",
    "fatigue_alerts",
    "performance_decisions",
]


@dataclass
class MemoryEntry:
    id: str
    organization_id: str
    memory_type: str
    key: str
    value: dict
    confidence: float
    source_agent: str
    created_at: int
    updated_at: int
    expires_at: Optional[int] = None


@dataclass
class BrandKit:
    name: str
    description: str
    brand_colors: dict  # {primary, secondary?, accent?}
    brand_voice: str
    messaging_pillars: list[str]
    tone_guidelines: list[str]
    approved_claims: list[str]
    do_not_say: list[str]
    visual_guidelines: dict
    tagline: Optional[str] = None
    logo_url: Optional[str] = None


@dataclass
class WinningCreative:
    creative_id: str
    provider: str
    campaign_id: str
    campaign_name: str
    format: str
    hook: str
    cta: str
    copy_theme: str
    visual_style: str
    peak_ctr: float
    current_ctr: float
    peak_roas: float
    current_roas: float
    total_impressions: int
    total_spend: float
    total_conversions: int
    days_to_peak: int
    analyzed_at: int
    sample_url: Optional[str] = None


@dataclass
class CompetitorPattern:
    competitor_name: str
    pattern_type: str  # hook | cta | visual | format | angle | offer
    pattern_value: str
    frequency: int
    avg_performance: float
    first_seen_at: int
    last_seen_at: int
    source_urls: list[str]


@dataclass
class KPITarget:
    id: str
    metric: str  # cpa | roas | cpl | cpi | ctr | custom
    target_value: float
    current_value: float
    unit: str
    timeframe: str  # daily | weekly | monthly
    campaign_ids: list[str]
    is_active: bool


@dataclass
class PerformanceDecision:
    decision_id: str
    type: str  # budget_shift | pause | scale | creative_refresh | kpi_update
    campaign_id: str
    campaign_name: str
    reason: str
    expected_impact: str
    was_auto_executed: bool
    was_approved: bool
    result: str  # pending | success | failed | rejected
    timestamp: int
    amount: Optional[float] = None
    from_: Optional[str] = None
    to: Optional[str] = None
    result_note: Optional[str] = None


class SharedMemory:
    def __init__(self):
        # In-memory store: key = "{orgId}:{memoryType}" -> list[MemoryEntry]
        self._memory: dict[str, list[MemoryEntry]] = {}

    def _storage_key(self, org_id: str, memory_type: str) -> str:
        return f"sm_{org_id}_{memory_type}"

    def _get_index(self, org_id: str, memory_type: str) -> list[MemoryEntry]:
        key = f"{org_id}:{memory_type}"
        if key not in self._memory:
            self._memory[key] = []
        # Filter expired entries
        now = int(time.time() * 1000)
        self._memory[key] = [
            e for e in self._memory[key]
            if not e.expires_at or e.expires_at > now
        ]
        return self._memory[key]

    # ─── Brand Kit ─────────────────────────────────────────────

    async def save_brand_kit(self, org_id: str, kit: dict) -> None:
        entries = self._get_index(org_id, "brand_kit")
        existing = next((i for i, e in enumerate(entries) if e.key == "current"), -1)
        now = int(time.time() * 1000)
        entry = MemoryEntry(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            memory_type="brand_kit",
            key="current",
            value=kit,
            confidence=1.0,
            source_agent="brand_setup",
            created_at=entries[existing].created_at if existing >= 0 else now,
            updated_at=now,
        )
        if existing >= 0:
            entries[existing] = entry
        else:
            entries.append(entry)

    async def get_brand_kit(self, org_id: str) -> Optional[dict]:
        entries = self._get_index(org_id, "brand_kit")
        entry = next((e for e in entries if e.key == "current"), None)
        return entry.value if entry else None

    # ─── Winning Creatives ─────────────────────────────────────

    async def save_winning_creative(self, org_id: str, creative: dict) -> None:
        entries = self._get_index(org_id, "winning_creatives")
        now = int(time.time() * 1000)
        entries.append(MemoryEntry(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            memory_type="winning_creatives",
            key=creative["creativeId"],
            value=creative,
            confidence=0.8,
            source_agent="creative_agent",
            created_at=now,
            updated_at=now,
        ))
        entries.sort(key=lambda e: e.value.get("peakRoas", 0), reverse=True)
        if len(entries) > 100:
            del entries[100:]

    async def get_winning_creatives(self, org_id: str, limit: int = 20) -> list[dict]:
        entries = self._get_index(org_id, "winning_creatives")
        return [e.value for e in entries[:limit]]

    async def get_top_winning_patterns(self, org_id: str) -> dict:
        winners = await self.get_winning_creatives(org_id, 50)
        high_roas = [w for w in winners if w.get("peakRoas", 0) > 1.5]
        hooks = list(dict.fromkeys(w["hook"] for w in high_roas if w.get("hook")))[:10]
        ctas = list(dict.fromkeys(w["cta"] for w in high_roas if w.get("cta")))[:10]
        themes = list(dict.fromkeys(w["copyTheme"] for w in high_roas if w.get("copyTheme")))[:10]
        return {"hooks": hooks, "ctas": ctas, "themes": themes}

    # ─── Competitor Patterns ───────────────────────────────────

    async def save_competitor_pattern(self, org_id: str, pattern: dict) -> None:
        entries = self._get_index(org_id, "competitor_patterns")
        key = f"{pattern['competitorName']}:{pattern['patternType']}:{pattern['patternValue']}"
        existing = next((i for i, e in enumerate(entries) if e.key == key), -1)
        now = int(time.time() * 1000)
        if existing >= 0:
            entries[existing].value["frequency"] = entries[existing].value.get("frequency", 0) + 1
            entries[existing].value["lastSeenAt"] = now
            entries[existing].updated_at = now
        else:
            entries.append(MemoryEntry(
                id=str(uuid.uuid4()),
                organization_id=org_id,
                memory_type="competitor_patterns",
                key=key,
                value=pattern,
                confidence=0.6,
                source_agent="competitor_spy",
                created_at=now,
                updated_at=now,
            ))

    async def get_competitor_patterns(self, org_id: str) -> list[dict]:
        entries = self._get_index(org_id, "competitor_patterns")
        return [e.value for e in entries]

    # ─── KPI Targets ───────────────────────────────────────────

    async def save_kpi_target(self, org_id: str, target: dict) -> None:
        entries = self._get_index(org_id, "kpi_targets")
        existing = next((i for i, e in enumerate(entries) if e.key == target["metric"]), -1)
        now = int(time.time() * 1000)
        entry = MemoryEntry(
            id=target.get("id") or str(uuid.uuid4()),
            organization_id=org_id,
            memory_type="kpi_targets",
            key=target["metric"],
            value=target,
            confidence=1.0,
            source_agent="performance_agent",
            created_at=entries[existing].created_at if existing >= 0 else now,
            updated_at=now,
        )
        if existing >= 0:
            entries[existing] = entry
        else:
            entries.append(entry)

    async def get_kpi_targets(self, org_id: str) -> list[dict]:
        entries = self._get_index(org_id, "kpi_targets")
        return [e.value for e in entries if e.value.get("isActive") is not False]

    # ─── Performance Decisions ─────────────────────────────────

    async def save_decision(self, org_id: str, decision: dict) -> None:
        entries = self._get_index(org_id, "performance_decisions")
        now = int(time.time() * 1000)
        entries.insert(0, MemoryEntry(
            id=decision.get("decisionId") or str(uuid.uuid4()),
            organization_id=org_id,
            memory_type="performance_decisions",
            key=decision.get("decisionId", ""),
            value=decision,
            confidence=1.0,
            source_agent="performance_agent",
            created_at=now,
            updated_at=now,
        ))
        if len(entries) > 200:
            del entries[200:]

    async def get_recent_decisions(self, org_id: str, limit: int = 20) -> list[dict]:
        entries = self._get_index(org_id, "performance_decisions")
        return [e.value for e in entries[:limit]]

    # ─── Fatigue Alerts ────────────────────────────────────────

    async def save_fatigue_alert(self, org_id: str, creative_id: str, fatigue_score: float, days_to_burnout: int) -> None:
        entries = self._get_index(org_id, "fatigue_alerts")
        existing = next((i for i, e in enumerate(entries) if e.key == creative_id), -1)
        now = int(time.time() * 1000)
        entry = MemoryEntry(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            memory_type="fatigue_alerts",
            key=creative_id,
            value={"creativeId": creative_id, "fatigueScore": fatigue_score, "daysToBurnout": days_to_burnout, "alertedAt": now},
            confidence=fatigue_score / 100,
            source_agent="creative_agent",
            created_at=now,
            updated_at=now,
        )
        if existing >= 0:
            entries[existing] = entry
        else:
            entries.append(entry)

    async def get_active_fatigue_alerts(self, org_id: str) -> list[dict]:
        entries = self._get_index(org_id, "fatigue_alerts")
        return [
            e.value for e in entries
            if e.value.get("fatigueScore", 0) >= 50
        ]

    # ─── Context Builder ───────────────────────────────────────

    async def build_context_for_agent(self, org_id: str, agent_type: str) -> str:
        parts: list[str] = []

        brand_kit = await self.get_brand_kit(org_id)
        if brand_kit:
            parts.extend([
                f"Brand: {brand_kit.get('name')} ({brand_kit.get('description')})",
                f"Voice: {brand_kit.get('brandVoice')}",
                f"Colors: {json.dumps(brand_kit.get('brandColors', {}))}",
                f"Pillars: {', '.join(brand_kit.get('messagingPillars', []))}",
                f"Approved Claims: {'; '.join(brand_kit.get('approvedClaims', []))}",
                f"Do Not Say: {'; '.join(brand_kit.get('doNotSay', []))}",
            ])

        if agent_type in ("creative_agent", "campaign_agent"):
            winners = await self.get_top_winning_patterns(org_id)
            if winners["hooks"]:
                parts.append(f"Winning Hooks: {' | '.join(winners['hooks'])}")
            if winners["ctas"]:
                parts.append(f"Winning CTAs: {' | '.join(winners['ctas'])}")
            if winners["themes"]:
                parts.append(f"Winning Themes: {' | '.join(winners['themes'])}")

        if agent_type == "campaign_agent":
            kpis = await self.get_kpi_targets(org_id)
            if kpis:
                parts.append("KPI Targets:")
                for k in kpis:
                    parts.append(f"  {k['metric']}: target {k['targetValue']}{k['unit']} (current: {k['currentValue']}{k['unit']})")
            decisions = await self.get_recent_decisions(org_id, 5)
            if decisions:
                parts.append("Recent Decisions:")
                for d in decisions:
                    parts.append(f"  {d['type']}: {d['campaignName']} - {d['result']}")

        return "\n".join(parts)


# Singleton
shared_memory = SharedMemory()
