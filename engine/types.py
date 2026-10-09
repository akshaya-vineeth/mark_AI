# ============================================================
# KLEOS — Engine Types (Python)
# Converted from: src/lib/engine/types.ts
# ============================================================

from typing import Optional, Literal
from dataclasses import dataclass, field

CycleStep = Literal["analyze", "detect", "generate", "launch", "shift", "report"]
CycleStatus = Literal["idle", "running", "completed", "failed", "cancelled"]


@dataclass
class CycleConfig:
    autonomy_level: int  # 1 | 2 | 3
    max_budget_shift_percent: float
    launch_tests_as_draft: bool
    generate_variants_per_creative: int
    fatigue_threshold: int


@dataclass
class StepState:
    status: str  # pending | running | completed | failed | skipped
    started_at: Optional[int] = None
    completed_at: Optional[int] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None
    summary: Optional[str] = None


@dataclass
class CycleLogEntry:
    timestamp: int
    step: str
    level: str  # info | success | warning | error
    message: str
    details: Optional[str] = None


@dataclass
class AnalyzeResult:
    campaigns_analyzed: int
    creatives_analyzed: int
    total_spend: float
    avg_roas: float
    anomalies: list[str]


@dataclass
class DetectResult:
    fatiguing_creatives: list[dict]  # [{creativeId, name, fatigueScore, daysToBurnout, campaignName}]
    opportunities: list[dict]  # [{type, description, expectedImpact, confidence}]


@dataclass
class GenerateResult:
    variants_generated: int
    variants: list[dict]  # [{variantId, creativeId, creativeName, headline, primaryText, cta, preLaunchScore}]


@dataclass
class LaunchResult:
    tests_launched: int
    tests: list[dict]  # [{testId, variantId, campaignName, platform, budget, status}]


@dataclass
class ShiftResult:
    decisions: list[dict]  # [{type, campaignId, campaignName, amount, reason, wasAutoExecuted, result}]
    total_shifted: float


@dataclass
class ReportResult:
    summary: str
    metrics: list[dict]  # [{label, value, trend?, accent?}]
    markdown_report: str


@dataclass
class CycleResults:
    analyze: AnalyzeResult
    detect: DetectResult
    generate: GenerateResult
    launch: LaunchResult
    shift: ShiftResult
    report: ReportResult


@dataclass
class CycleState:
    id: str
    status: str
    current_step: Optional[str]
    steps: dict  # CycleStep -> StepState
    started_at: Optional[int]
    completed_at: Optional[int]
    duration_ms: Optional[int]
    config: CycleConfig
    logs: list[CycleLogEntry]
    results: Optional[CycleResults]
    error: Optional[str]


DEFAULT_CYCLE_CONFIG = CycleConfig(
    autonomy_level=3,
    max_budget_shift_percent=20,
    launch_tests_as_draft=True,
    generate_variants_per_creative=5,
    fatigue_threshold=70,
)

STEP_LABELS: dict[str, str] = {
    "analyze": "Analyze Account",
    "detect": "Detect Opportunities",
    "generate": "Generate Creatives",
    "launch": "Launch Tests",
    "shift": "Shift Budget",
    "report": "Report Outcomes",
}

STEP_ICONS: dict[str, str] = {
    "analyze": "🔍",
    "detect": "🎯",
    "generate": "✨",
    "launch": "🚀",
    "shift": "💰",
    "report": "📋",
}

STEP_ORDER: list[str] = ["analyze", "detect", "generate", "launch", "shift", "report"]
