# ============================================================
# KLEOS — Engine Step: Analyze (Python)
# Converted from: src/lib/engine/steps/analyze.ts
# ============================================================

from backend.engine.types import CycleConfig, AnalyzeResult
from backend.integrations.manager import integration_manager


async def step_analyze(org_id: str, config: CycleConfig) -> AnalyzeResult:
    campaigns = await integration_manager.get_all_campaigns(org_id)
    creatives = await integration_manager.get_all_creatives(org_id)

    total_spend = sum(c.spend for c in campaigns)
    avg_roas = (
        sum(c.roas for c in campaigns) / len(campaigns)
        if campaigns else 0
    )

    anomalies: list[str] = []
    for c in campaigns:
        if c.roas < 0.5 and c.spend > 5000:
            anomalies.append(f"{c.name}: ROAS {c.roas:.1f}x with ₹{c.spend:.0f} spend")
        if c.impressions == 0 and c.status == "ACTIVE":
            anomalies.append(f"{c.name}: Active but zero impressions")

    return AnalyzeResult(
        campaigns_analyzed=len(campaigns),
        creatives_analyzed=len(creatives),
        total_spend=total_spend,
        avg_roas=avg_roas,
        anomalies=anomalies,
    )
