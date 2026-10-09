# ============================================================
# KLEOS — Engine Step: Shift (Python)
# Converted from: src/lib/engine/steps/shift.ts
# NOTE: useRunCycleStore removed (frontend concern); replaced with logging
# ============================================================

import logging
from backend.engine.types import CycleConfig, ShiftResult
from backend.agents.campaign_agent import campaign_agent

logger = logging.getLogger(__name__)


async def step_shift(org_id: str, config: CycleConfig) -> ShiftResult:
    campaign_agent.set_autonomy(org_id, {
        "level": config.autonomy_level,
        "max_budget_shift_percent": config.max_budget_shift_percent,
    })

    logger.info(f"[shift] Running budget reallocation (autonomy: L{config.autonomy_level}, max shift: {config.max_budget_shift_percent}%)...")

    cycle = await campaign_agent.run_autonomous_cycle(org_id)
    total_shifted = sum(abs(d.get("amount") or 0) for d in cycle.decisions if d.get("amount"))

    auto_count = sum(1 for d in cycle.decisions if d.get("wasAutoExecuted"))
    pending_count = sum(1 for d in cycle.decisions if d.get("result") == "pending")

    logger.info(f"[shift] Budget reallocation complete: {len(cycle.decisions)} decisions")
    if auto_count > 0:
        logger.info(f"[shift] {auto_count} decision(s) auto-executed — Total shifted: ₹{total_shifted:.0f}")
    if pending_count > 0:
        logger.warning(f"[shift] {pending_count} decision(s) pending execution")

    return ShiftResult(
        decisions=[
            {
                "type": d["type"],
                "campaignId": d["campaignId"],
                "campaignName": d["campaignName"],
                "amount": d.get("amount") or 0,
                "reason": d["reason"],
                "wasAutoExecuted": d["wasAutoExecuted"],
                "result": d["result"],
            }
            for d in cycle.decisions
        ],
        total_shifted=total_shifted,
    )
