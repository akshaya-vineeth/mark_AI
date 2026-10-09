# ============================================================
# KLEOS — Engine Step: Generate (Python)
# Converted from: src/lib/engine/steps/generate.ts
# ============================================================

from backend.engine.types import CycleConfig, GenerateResult
from backend.agents.creative_agent import creative_agent


async def step_generate(org_id: str, config: CycleConfig) -> GenerateResult:
    predictions = await creative_agent.predict_fatigue_for_all(org_id)
    fatiguing = [p for p in predictions if p.fatigue_score >= config.fatigue_threshold]

    if not fatiguing:
        return GenerateResult(variants_generated=0, variants=[])

    variants: list[dict] = []

    for creative in fatiguing:
        generated = await creative_agent.generate_variants(org_id, creative.creative_id, "run_cycle_fatigue")

        for g in generated:
            variants.append({
                "variantId": g.variant_id,
                "creativeId": creative.creative_id,
                "creativeName": creative.name,
                "headline": g.headline,
                "primaryText": g.primary_text,
                "cta": g.cta,
                "preLaunchScore": 75,
            })

    return GenerateResult(
        variants_generated=len(variants),
        variants=variants,
    )
