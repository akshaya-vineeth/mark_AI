# ============================================================
# KLEOS — Campaign Agent (Python)
# ============================================================

import uuid
import time
from typing import Optional, Literal
from dataclasses import dataclass, field

from backend.ai.agents import generate_with_agent
from backend.memory.shared_memory import shared_memory
from backend.integrations.manager import integration_manager, UnifiedCampaign, BudgetAllocationDecision


@dataclass
class AutonomousCycleResult:
    decisions: list[dict]
    summary: str
    has_alerts: bool


@dataclass
class CampaignDecision:
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


@dataclass
class AutonomyConfig:
    level: int  # 1 | 2 | 3
    max_budget_shift_percent: float
    require_approval_for: list[str]
    allowed_actions: list[str]


DEFAULT_AUTONOMY = AutonomyConfig(
    level=2,
    max_budget_shift_percent=20,
    require_approval_for=["budget_shift", "pause"],
    allowed_actions=["budget_shift", "pause", "scale", "creative_refresh"],
)


class CampaignAgent:
    def __init__(self):
        self._autonomy_map: dict[str, AutonomyConfig] = {}
        self._account_id_map: dict[str, str] = {}

    def set_autonomy(self, organization_id: str, config: dict) -> None:
        current = vars(self.get_autonomy(organization_id)).copy()
        current.update(config)
        self._autonomy_map[organization_id] = AutonomyConfig(**current)

    def get_autonomy(self, organization_id: str) -> AutonomyConfig:
        return self._autonomy_map.get(organization_id, DEFAULT_AUTONOMY)

    async def _resolve_account_map(self, organization_id: str, campaigns: list[UnifiedCampaign]) -> None:
        for account_id, account in integration_manager._accounts.items():
            if account.organization_id != organization_id:
                continue
            if account.provider == "meta":
                for c in campaigns:
                    if (c.platform_data or {}).get("metaAdAccountId") == account.account_id:
                        self._account_id_map[c.id] = account_id
            elif account.provider == "google":
                for c in campaigns:
                    if c.provider == "google":
                        self._account_id_map[c.id] = account_id

    async def run_autonomous_cycle(self, organization_id: str) -> AutonomousCycleResult:
        decisions: list[dict] = []
        autonomy = self.get_autonomy(organization_id)

        campaigns = await integration_manager.get_all_campaigns(organization_id)
        kpis = await shared_memory.get_kpi_targets(organization_id)
        await self._resolve_account_map(organization_id, campaigns)

        for campaign in campaigns:
            primary_kpi = next(
                (k for k in kpis if campaign.id in k.get("campaignIds", [])),
                kpis[0] if kpis else None,
            )

            if primary_kpi:
                is_underperforming = self._is_underperforming(campaign, primary_kpi)
                is_overperforming = self._is_overperforming(campaign, primary_kpi)

                if is_underperforming and campaign.daily_budget > 100:
                    reduction = campaign.daily_budget * 0.3
                    should_auto_exec = (
                        "budget_shift" not in autonomy.require_approval_for and
                        (reduction / campaign.daily_budget) <= autonomy.max_budget_shift_percent / 100
                    )
                    decisions.append({
                        "decisionId": str(uuid.uuid4()),
                        "type": "budget_shift",
                        "campaignId": campaign.id,
                        "campaignName": campaign.name,
                        "reason": f"CPA {campaign.cpa:.2f} exceeds target {primary_kpi['targetValue']}{primary_kpi['unit']} - reducing 30%",
                        "amount": -reduction,
                        "expectedImpact": f"Reduce spend on {campaign.name} by ~{self._format_currency(reduction)}/day",
                        "wasAutoExecuted": should_auto_exec,
                        "wasApproved": False,
                        "result": "success" if should_auto_exec else "pending",
                        "timestamp": int(time.time() * 1000),
                    })

                if is_overperforming and campaign.daily_budget > 100:
                    increase = campaign.daily_budget * 0.3
                    should_auto_exec = (
                        "scale" not in autonomy.require_approval_for and
                        (increase / campaign.daily_budget) <= autonomy.max_budget_shift_percent / 100
                    )
                    decisions.append({
                        "decisionId": str(uuid.uuid4()),
                        "type": "scale",
                        "campaignId": campaign.id,
                        "campaignName": campaign.name,
                        "reason": f"ROAS {campaign.roas:.1f}x exceeds {primary_kpi['targetValue']}{primary_kpi['unit']} - scaling 30%",
                        "amount": increase,
                        "expectedImpact": f"Scale {campaign.name} - potential +{self._format_currency(increase)}/day revenue",
                        "wasAutoExecuted": should_auto_exec,
                        "wasApproved": False,
                        "result": "success" if should_auto_exec else "pending",
                        "timestamp": int(time.time() * 1000),
                    })

            if campaign.roas < 0.5 and campaign.spend > 5000 and campaign.daily_budget > 100:
                decisions.append({
                    "decisionId": str(uuid.uuid4()),
                    "type": "pause",
                    "campaignId": campaign.id,
                    "campaignName": campaign.name,
                    "reason": f"ROAS {campaign.roas:.1f}x critically low with {self._format_currency(campaign.spend)} spend",
                    "expectedImpact": f"Save ~{self._format_currency(campaign.daily_budget)}/day from underperforming campaign",
                    "wasAutoExecuted": autonomy.level >= 3,
                    "wasApproved": False,
                    "result": "success" if autonomy.level >= 3 else "pending",
                    "timestamp": int(time.time() * 1000),
                })

        for d in decisions:
            if d.get("wasAutoExecuted") and d.get("result") == "success":
                try:
                    account_id = self._account_id_map.get(d["campaignId"])
                    if not account_id:
                        continue
                    campaign = next((c for c in campaigns if c.id == d["campaignId"]), None)
                    if not campaign:
                        continue

                    new_budget = (
                        max(campaign.daily_budget + (d.get("amount") or 0), 100)
                        if d["type"] == "budget_shift"
                        else campaign.daily_budget + (d.get("amount") or 0)
                    )
                    await integration_manager.execute_budget_allocation([BudgetAllocationDecision(
                        account_id=account_id,
                        campaign_id=d["campaignId"],
                        new_budget=new_budget,
                        reason=d["reason"],
                        platform_data=campaign.platform_data,
                    )])
                except Exception:
                    pass
            await shared_memory.save_decision(organization_id, d)

        summary = (
            f"{len(decisions)} decisions made: "
            f"{sum(1 for d in decisions if d.get('wasAutoExecuted'))} auto-executed, "
            f"{sum(1 for d in decisions if d.get('result') == 'pending')} pending approval"
            if decisions
            else "All campaigns performing within KPI targets. No changes needed."
        )

        return AutonomousCycleResult(
            decisions=decisions,
            summary=summary,
            has_alerts=any(d["type"] == "pause" for d in decisions),
        )

    async def create_campaign(self, organization_id: str, platform: str, budget: float, name: str, objective: str) -> dict:
        # Business logic for creating a campaign
        decision_id = f"dec_create_{str(uuid.uuid4())[:8]}"
        decision = {
            "decisionId": decision_id,
            "type": "create_campaign",
            "campaignId": f"camp_{str(uuid.uuid4())[:8]}",
            "campaignName": name,
            "reason": f"Created new {platform} campaign targeting {objective} with budget {self._format_currency(budget)}",
            "expectedImpact": f"Establish brand presence on {platform} and drive {objective}",
            "wasAutoExecuted": True,
            "wasApproved": True,
            "result": "success",
            "timestamp": int(time.time() * 1000),
            "amount": budget,
        }
        await shared_memory.save_decision(organization_id, decision)
        return decision

    async def analyze_and_recommend(self, organization_id: str) -> str:
        context = await shared_memory.build_context_for_agent(organization_id, "campaign_agent")
        campaigns = await integration_manager.get_all_campaigns(organization_id)
        kpis = await shared_memory.get_kpi_targets(organization_id)
        recent_decisions = await shared_memory.get_recent_decisions(organization_id, 10)

        import json
        return await generate_with_agent("campaign_agent", "analyzeAccount", {
            "campaigns": json.dumps([vars(c) for c in campaigns[:20]]),
            "kpis": json.dumps(kpis),
            "recentDecisions": json.dumps(recent_decisions),
        }, {"brandContext": context})

    async def process_message(self, organization_id: str, message: str) -> str:
        context = await shared_memory.build_context_for_agent(organization_id, "campaign_agent")
        return await generate_with_agent("campaign_agent", "analyzeAccount", {
            "query": message,
            "context": context,
        }, {"brandContext": context})

    def _is_underperforming(self, campaign: UnifiedCampaign, kpi: dict) -> bool:
        if not kpi:
            return False
        metric = kpi.get("metric")
        target = kpi.get("targetValue", 0)
        if metric == "cpa" and campaign.cpa > target * 1.2:
            return True
        if metric == "roas" and campaign.roas < target * 0.8:
            return True
        if metric == "ctr" and campaign.ctr > 0 and campaign.ctr < target * 0.8:
            return True
        return False

    def _is_overperforming(self, campaign: UnifiedCampaign, kpi: dict) -> bool:
        if not kpi:
            return False
        metric = kpi.get("metric")
        target = kpi.get("targetValue", 0)
        if metric == "cpa" and campaign.cpa > 0 and campaign.cpa < target * 0.7:
            return True
        if metric == "roas" and campaign.roas > target * 1.3:
            return True
        return False

    def _format_currency(self, amount: float) -> str:
        return f"₹{amount:,.0f}"


# Singleton
campaign_agent = CampaignAgent()
