# ============================================================
# KLEOS — Engine Step: Report (Python)
# Converted from: src/lib/engine/steps/report.ts
# NOTE: useRunCycleStore replaced with receiving results as parameter
# ============================================================

import logging
from datetime import datetime
from backend.engine.types import CycleConfig, ReportResult, CycleResults

logger = logging.getLogger(__name__)


async def step_report(org_id: str, config: CycleConfig, results: CycleResults, duration_ms: int = 0) -> ReportResult:
    metrics: list[dict] = [
        {
            "label": "Campaigns Analyzed",
            "value": results.analyze.campaigns_analyzed,
            "accent": "electric",
        },
        {
            "label": "Fatiguing Found",
            "value": len(results.detect.fatiguing_creatives),
            "accent": "pulse" if results.detect.fatiguing_creatives else "signal",
        },
        {
            "label": "Variants Generated",
            "value": results.generate.variants_generated,
            "accent": "aura",
        },
        {
            "label": "Tests Launched",
            "value": results.launch.tests_launched,
            "accent": "signal" if results.launch.tests_launched > 0 else "electric",
        },
        {
            "label": "Budget Shifted",
            "value": f"₹{results.shift.total_shifted:.0f}",
            "accent": "gold" if results.shift.total_shifted > 0 else "electric",
        },
        {
            "label": "Total Decisions",
            "value": len(results.shift.decisions),
            "accent": "electric",
        },
    ]

    today = datetime.now().strftime("%Y-%m-%d")
    summary_parts: list[str] = [
        f"# Run Cycle Report — {today}\n",
        "## Overview\n",
        f"- **Campaigns Analyzed:** {results.analyze.campaigns_analyzed}",
        f"- **Creatives Analyzed:** {results.analyze.creatives_analyzed}",
        f"- **Total Spend:** ₹{results.analyze.total_spend:.0f}",
        f"- **Avg ROAS:** {results.analyze.avg_roas:.2f}x",
        f"- **Duration:** {round(duration_ms / 1000)}s\n",
    ]

    if results.detect.fatiguing_creatives:
        summary_parts.append("## Creative Fatigue Detected\n")
        for f in results.detect.fatiguing_creatives:
            summary_parts.append(f"- **{f['name']}** — Score: {f['fatigueScore']}/100, {f['daysToBurnout']}d to burnout")
        summary_parts.append("")

    if results.generate.variants_generated > 0:
        summary_parts.append("## Generated Variants\n")
        summary_parts.append(f"- {results.generate.variants_generated} variant(s) generated")
        for v in results.generate.variants:
            summary_parts.append(f"- \"{v['headline'][:80]}\" — Pre-launch score: {v['preLaunchScore']}/100")
        summary_parts.append("")

    if results.shift.decisions:
        summary_parts.append("## Budget Decisions\n")
        for d in results.shift.decisions:
            status = "✅ Auto-executed" if d.get("wasAutoExecuted") else "⏳ Pending"
            summary_parts.append(f"- **{d['type'].replace('_', ' ')}**: {d['campaignName']} — {d['reason']} ({status})")
        summary_parts.append("")

    if results.analyze.anomalies:
        summary_parts.append("## Anomalies Detected\n")
        for a in results.analyze.anomalies:
            summary_parts.append(f"- ⚠️ {a}")

    markdown_report = "\n".join(summary_parts)

    logger.info(f"[report] Report generated — {len(metrics)} metrics, {len(summary_parts)} report lines")

    return ReportResult(
        summary=(
            f"Cycle complete: Analyzed {results.analyze.campaigns_analyzed} campaigns, "
            f"found {len(results.detect.fatiguing_creatives)} fatiguing creatives, "
            f"generated {results.generate.variants_generated} variants, "
            f"launched {results.launch.tests_launched} tests, "
            f"shifted ₹{results.shift.total_shifted:.0f} in budget."
        ),
        metrics=metrics,
        markdown_report=markdown_report,
    )
