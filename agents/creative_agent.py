# ============================================================
# KLEOS — Creative Agent (Python)
# Converted from: src/lib/agents/creative-agent.ts
# ============================================================

import uuid
import math
import random
import time
import json
from typing import Optional
from dataclasses import dataclass

from backend.ai.agents import generate_with_agent
from backend.memory.shared_memory import shared_memory
from backend.integrations.manager import integration_manager

FATIGUE_THRESHOLD = 70
CRITICAL_FATIGUE_THRESHOLD = 85


@dataclass
class CreativeAnalysis:
    creative_id: str
    name: str
    provider: str
    status: str
    campaign_id: str
    format: str
    impressions: int
    clicks: int
    spend: float
    ctr: float
    peak_ctr: float
    ctr_decay_percent: int
    fatigue_score: int
    fatigue_trend: str  # rising | stable | falling
    days_running: int
    frequency: float
    brand_alignment_score: int
    analyzed_at: int


@dataclass
class FatiguePrediction:
    creative_id: str
    name: str
    campaign_name: str
    fatigue_score: int
    days_to_burnout: int
    confidence: float
    factors: dict  # {ctrDecayRate, frequency, audienceSaturation, creativeAge}
    recommendation: str


@dataclass
class GeneratedVariant:
    variant_id: str
    based_on_creative_id: str
    trigger_reason: str
    format: str
    platform: str
    headline: str
    primary_text: str
    description: str
    cta: str
    image_prompt: str
    based_on_evidence: list[str]
    brand_kit_applied: bool


class CreativeAgent:
    async def analyze_all_creatives(self, organization_id: str) -> list[CreativeAnalysis]:
        creatives = await integration_manager.get_all_creatives(organization_id)
        analyses: list[CreativeAnalysis] = []

        for creative in creatives:
            peak_ctr = creative.ctr * (1 + random.random() * 0.5)
            ctr_decay_percent = (
                round(((peak_ctr - creative.ctr) / peak_ctr) * 100) if peak_ctr > 0 else 0
            )
            days_running = creative.days_running or math.ceil(random.random() * 30)
            frequency = creative.impressions / max(creative.clicks, 1) if creative.impressions > 0 else 0

            fatigue_score = self._calculate_fatigue_score({
                "ctrDecayPercent": ctr_decay_percent,
                "frequency": frequency,
                "daysRunning": days_running,
                "peakCtr": peak_ctr,
                "currentCtr": creative.ctr,
                "spend": creative.spend,
            })

            analysis = CreativeAnalysis(
                creative_id=creative.id,
                name=creative.name,
                provider=creative.provider,
                status=creative.status,
                campaign_id=creative.campaign_id,
                format=self._infer_format(creative.id),
                impressions=creative.impressions,
                clicks=creative.clicks,
                spend=creative.spend,
                ctr=creative.ctr,
                peak_ctr=peak_ctr,
                ctr_decay_percent=ctr_decay_percent,
                fatigue_score=fatigue_score,
                fatigue_trend=(
                    "rising" if ctr_decay_percent > 30
                    else "stable" if ctr_decay_percent > 15
                    else "falling"
                ),
                days_running=days_running,
                frequency=frequency,
                brand_alignment_score=round(70 + random.random() * 25),
                analyzed_at=int(time.time() * 1000),
            )
            analyses.append(analysis)

            if fatigue_score >= FATIGUE_THRESHOLD:
                days_to_burnout = self._predict_days_to_burnout(fatigue_score)
                await shared_memory.save_fatigue_alert(organization_id, creative.id, fatigue_score, days_to_burnout)

            if creative.ctr > 2.5 and creative.spend > 1000:
                await shared_memory.save_winning_creative(organization_id, {
                    "creativeId": creative.id,
                    "provider": creative.provider,
                    "campaignId": creative.campaign_id,
                    "campaignName": "",
                    "format": self._infer_format(creative.id),
                    "hook": "",
                    "cta": "",
                    "copyTheme": "",
                    "visualStyle": "",
                    "peakCtr": peak_ctr,
                    "currentCtr": creative.ctr,
                    "peakRoas": 0,
                    "currentRoas": 0,
                    "totalImpressions": creative.impressions,
                    "totalSpend": creative.spend,
                    "totalConversions": 0,
                    "daysToPeak": 0,
                    "analyzedAt": int(time.time() * 1000),
                })

        return analyses

    async def predict_fatigue_for_all(self, organization_id: str) -> list[FatiguePrediction]:
        analyses = await self.analyze_all_creatives(organization_id)
        predictions: list[FatiguePrediction] = []
        for a in analyses:
            days_to_burnout = self._predict_days_to_burnout(a.fatigue_score)
            predictions.append(FatiguePrediction(
                creative_id=a.creative_id,
                name=a.name or f"Creative {a.creative_id[:8]}",
                campaign_name="",
                fatigue_score=a.fatigue_score,
                days_to_burnout=days_to_burnout,
                confidence=0.9 if a.fatigue_score > 80 else 0.7 if a.fatigue_score > 60 else 0.5,
                factors={
                    "ctrDecayRate": a.ctr_decay_percent,
                    "frequency": round(a.frequency * 10) / 10,
                    "audienceSaturation": min(round(a.frequency / 10 * 100), 100),
                    "creativeAge": a.days_running,
                },
                recommendation=(
                    "IMMEDIATE: Pause and replace" if a.fatigue_score >= CRITICAL_FATIGUE_THRESHOLD
                    else "URGENT: Prepare replacement within 48h" if a.fatigue_score >= FATIGUE_THRESHOLD
                    else "MONITOR: Review in 3-5 days" if a.fatigue_score >= 50
                    else "HEALTHY: No action needed"
                ),
            ))
        return predictions

    async def generate_variants(self, organization_id: str, trigger_creative_id: str, trigger_reason: str) -> list[GeneratedVariant]:
        brand_kit = await shared_memory.get_brand_kit(organization_id)
        winning_patterns = await shared_memory.get_top_winning_patterns(organization_id)
        competitor_patterns = await shared_memory.get_competitor_patterns(organization_id)
        fatigue_alerts = await shared_memory.get_active_fatigue_alerts(organization_id)
        context = await shared_memory.build_context_for_agent(organization_id, "creative_agent")
        alert = next((a for a in fatigue_alerts if a["creativeId"] == trigger_creative_id), None)

        output = await generate_with_agent("creative_agent", "generateVariants", {
            "triggerReason": trigger_reason,
            "triggerCreativeId": trigger_creative_id,
            "fatigueScore": alert.get("fatigueScore", 0) if alert else 0,
            "brandKit": json.dumps(brand_kit) if brand_kit else "{}",
            "winningHooks": ", ".join(winning_patterns.get("hooks", [])),
            "winningCTAs": ", ".join(winning_patterns.get("ctas", [])),
            "competitorPatterns": json.dumps(competitor_patterns[:10]),
        }, {"brandContext": context})

        lines = [l.strip() for l in output.split("\n") if l.strip()]
        headline = next(
            (l.split(":", 1)[-1].strip() for l in lines if "headline" in l.lower()),
            (brand_kit.get("name") if brand_kit else None) or "New Creative Variant"
        )
        primary_text = " ".join(lines[:5])[:500]
        cta = next(
            (l.split(":", 1)[-1].strip() for l in lines if "cta" in l.lower()),
            "Learn More"
        )
        image_desc = next(
            (l.split(":", 1)[-1].strip() for l in lines if "image" in l.lower() or "visual" in l.lower()),
            output[:200]
        )

        hooks = winning_patterns.get("hooks", [])
        ctas = winning_patterns.get("ctas", [])
        evidence = [
            f'Winning hook pattern: "{hooks[0]}"' if hooks else "No winning hook data",
            f'Winning CTA: "{ctas[0]}"' if ctas else "No winning CTA data",
            f"Competitor pattern: {competitor_patterns[0]['competitorName']} - {competitor_patterns[0]['patternValue']}" if competitor_patterns else "No competitor data",
            f"Brand kit: {brand_kit['name']}" if brand_kit else "No brand kit configured",
        ]

        return [GeneratedVariant(
            variant_id=str(uuid.uuid4()),
            based_on_creative_id=trigger_creative_id,
            trigger_reason=trigger_reason,
            format="image",
            platform="meta",
            headline=headline,
            primary_text=primary_text,
            description=f"Generated for creative {trigger_creative_id} (fatigue: {alert['fatigueScore'] if alert else 'unknown'})",
            cta=cta,
            image_prompt=image_desc,
            based_on_evidence=evidence,
            brand_kit_applied=bool(brand_kit),
        )]

    async def get_portfolio_gaps(self, organization_id: str) -> str:
        context = await shared_memory.build_context_for_agent(organization_id, "creative_agent")
        competitors = await shared_memory.get_competitor_patterns(organization_id)
        winners = await shared_memory.get_top_winning_patterns(organization_id)
        return await generate_with_agent("creative_agent", "getPortfolioGaps", {
            "competitorPatterns": json.dumps(competitors[:20]),
            "winningHooks": ", ".join(winners.get("hooks", [])),
            "winningCTAs": ", ".join(winners.get("ctas", [])),
            "winningThemes": ", ".join(winners.get("themes", [])),
        }, {"brandContext": context})

    async def analyze_and_recommend(self, organization_id: str) -> str:
        context = await shared_memory.build_context_for_agent(organization_id, "creative_agent")
        predictions = await self.predict_fatigue_for_all(organization_id)
        fatiguing = [p for p in predictions if p.fatigue_score >= FATIGUE_THRESHOLD]
        return await generate_with_agent("creative_agent", "analyzeCreatives", {
            "totalAnalyzed": len(predictions),
            "fatiguingCount": len(fatiguing),
            "criticalCount": sum(1 for p in fatiguing if p.fatigue_score >= CRITICAL_FATIGUE_THRESHOLD),
            "topFatigue": json.dumps([vars(p) for p in fatiguing[:5]]),
        }, {"brandContext": context})

    def _infer_format(self, id: str) -> str:
        if id.startswith("v_"):
            return "video"
        if id.startswith("c_"):
            return "carousel"
        return "image"

    def _calculate_fatigue_score(self, params: dict) -> int:
        ctr_decay_percent = params.get("ctrDecayPercent", 0)
        frequency = params.get("frequency", 0)
        days_running = params.get("daysRunning", 0)
        spend = params.get("spend", 0)

        decay_score = min(ctr_decay_percent, 100) * 0.4
        frequency_score = min(frequency / 10, 1) * 100 * 0.25
        age_score = min(days_running / 45, 1) * 100 * 0.2
        spend_score = min(spend / 10000, 1) * 100 * 0.15
        return round(min(decay_score + frequency_score + age_score + spend_score, 100))

    def _predict_days_to_burnout(self, fatigue_score: int) -> int:
        if fatigue_score >= CRITICAL_FATIGUE_THRESHOLD:
            return 1
        if fatigue_score >= FATIGUE_THRESHOLD:
            return max(2, round((100 - fatigue_score) / 8))
        if fatigue_score >= 50:
            return max(4, round((100 - fatigue_score) / 5))
        return max(7, round((100 - fatigue_score) / 3))


    async def process_message(self, organization_id: str, message: str) -> str:
        context = await shared_memory.build_context_for_agent(organization_id, "creative_agent")
        return await generate_with_agent("creative_agent", "createContent", {
            "query": message,
            "context": context
        }, {"brandContext": context})


# Singleton
creative_agent = CreativeAgent()
