# ============================================================
# KLEOS — Engine Step: Launch (Python)
# Converted from: src/lib/engine/steps/launch.ts
# ============================================================

from backend.engine.types import CycleConfig, LaunchResult
from backend.agents.creative_agent import creative_agent


async def step_launch(org_id: str, config: CycleConfig) -> LaunchResult:
    predictions = await creative_agent.predict_fatigue_for_all(org_id)
    fatiguing = [p for p in predictions if p.fatigue_score >= config.fatigue_threshold]

    if not fatiguing:
        return LaunchResult(tests_launched=0, tests=[])

    tests: list[dict] = []

    for creative in fatiguing:
        generated = await creative_agent.generate_variants(org_id, creative.creative_id, "run_cycle_launch")

        for g in generated:
            test_id = f"test_{g.variant_id[:8]}"

            tests.append({
                "testId": test_id,
                "variantId": g.variant_id,
                "campaignName": creative.campaign_name or creative.name,
                "platform": "meta",
                "budget": 500,
                "status": "draft" if config.launch_tests_as_draft else "active",
            })

    return LaunchResult(tests_launched=len(tests), tests=tests)
