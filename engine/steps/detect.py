# ============================================================
# KLEOS — Engine Step: Detect (Python)
# Converted from: src/lib/engine/steps/detect.ts
# ============================================================

from backend.engine.types import CycleConfig, DetectResult
from backend.agents.creative_agent import creative_agent
from backend.agents.campaign_agent import campaign_agent


async def step_detect(org_id: str, config: CycleConfig) -> DetectResult:
    predictions = await creative_agent.predict_fatigue_for_all(org_id)
    fatiguing = [p for p in predictions if p.fatigue_score >= config.fatigue_threshold]

    cycle = await campaign_agent.run_autonomous_cycle(org_id)

    opportunities: list[dict] = []

    for f in fatiguing:
        opportunities.append({
            "type": "creative_fatigue",
            "description": f"{f.name} is fatiguing (score: {f.fatigue_score}/100, {f.days_to_burnout}d to burnout)",
            "expectedImpact": "Replace before performance drops further",
            "confidence": 0.9 if f.fatigue_score > 85 else 0.7,
        })

    for d in cycle.decisions:
        if d.get("type") == "budget_shift":
            opportunities.append({
                "type": "budget_shift",
                "description": d["reason"],
                "expectedImpact": d["expectedImpact"],
                "confidence": 0.8,
            })

    return DetectResult(
        fatiguing_creatives=[
            {
                "creativeId": f.creative_id,
                "name": f.name,
                "fatigueScore": f.fatigue_score,
                "daysToBurnout": f.days_to_burnout,
                "campaignName": f.campaign_name,
            }
            for f in fatiguing
        ],
        opportunities=opportunities,
    )
