# ============================================================
# KLEOS — Run Cycle Orchestrator (Python)
# Converted from: src/lib/engine/run-cycle.ts
# ============================================================

import time
from typing import Optional, Callable
from dataclasses import dataclass

from backend.engine.types import CycleConfig, CycleResults, STEP_ORDER, DEFAULT_CYCLE_CONFIG
from backend.engine.steps.analyze import step_analyze
from backend.engine.steps.detect import step_detect
from backend.engine.steps.generate import step_generate
from backend.engine.steps.launch import step_launch
from backend.engine.steps.shift import step_shift
from backend.engine.steps.report import step_report

# Maps each step name to its runner function
STEP_RUNNERS = {
    "analyze": step_analyze,
    "detect": step_detect,
    "generate": step_generate,
    "launch": step_launch,
    "shift": step_shift,
    "report": step_report,  # NOTE: report also needs results; handled below
}


async def execute_run_cycle(
    org_id: str = "org-1",
    config: Optional[dict] = None,
    on_progress: Optional[Callable[[dict], None]] = None,
) -> dict:
    """
    Executes the full KLEOS run cycle: analyze → detect → generate → launch → shift → report.

    Returns:
        {"success": bool, "results": CycleResults | None, "error": str | None}
    """
    cycle_config = CycleConfig(
        autonomy_level=3,
        max_budget_shift_percent=20,
        launch_tests_as_draft=True,
        generate_variants_per_creative=5,
        fatigue_threshold=70,
        **(config or {}),
    )

    # Use dataclass override correctly
    if config:
        cycle_config = CycleConfig(
            autonomy_level=config.get("autonomy_level", 3),
            max_budget_shift_percent=config.get("max_budget_shift_percent", 20),
            launch_tests_as_draft=config.get("launch_tests_as_draft", True),
            generate_variants_per_creative=config.get("generate_variants_per_creative", 5),
            fatigue_threshold=config.get("fatigue_threshold", 70),
        )
    else:
        cycle_config = DEFAULT_CYCLE_CONFIG

    results: dict = {}
    start_time = int(time.time() * 1000)

    for step in STEP_ORDER:
        if on_progress:
            on_progress({"type": "step_start", "step": step, "message": f"Starting {step}..."})

        try:
            if step == "report":
                # Report step needs accumulated results
                from backend.engine.types import AnalyzeResult, DetectResult, GenerateResult, LaunchResult, ShiftResult
                assembled = CycleResults(
                    analyze=results["analyze"],
                    detect=results["detect"],
                    generate=results["generate"],
                    launch=results["launch"],
                    shift=results["shift"],
                    report=None,  # not yet
                )
                duration_ms = int(time.time() * 1000) - start_time
                step_result = await step_report(org_id, cycle_config, assembled, duration_ms)
            else:
                step_result = await STEP_RUNNERS[step](org_id, cycle_config)

            results[step] = step_result

            if on_progress:
                on_progress({"type": "step_complete", "step": step, "data": step_result, "message": f"{step} completed"})

        except Exception as error:
            if on_progress:
                on_progress({"type": "step_failed", "step": step, "message": str(error)})
            return {"success": False, "error": f"{step} failed: {error}"}

    final_results = CycleResults(
        analyze=results["analyze"],
        detect=results["detect"],
        generate=results["generate"],
        launch=results["launch"],
        shift=results["shift"],
        report=results["report"],
    )

    if on_progress:
        on_progress({"type": "complete", "data": final_results, "message": "Run cycle completed"})

    return {"success": True, "results": final_results}
