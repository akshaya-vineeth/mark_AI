# ============================================================
# KLEOS — Integration Manager (Python)
# Converted from: src/lib/integrations/manager.ts
# ============================================================

from typing import Optional, Literal
from dataclasses import dataclass, field
import logging

from backend.integrations.meta_ads import MetaAdsClient, MetaConfig
from backend.integrations.google_ads import GoogleAdsClient, GoogleAdsConfig

logger = logging.getLogger(__name__)

AdProvider = Literal["meta", "google", "youtube"]


@dataclass
class AdAccountConfig:
    id: str
    organization_id: str
    provider: AdProvider
    account_id: str
    name: str
    access_token: str
    config: dict = field(default_factory=dict)


@dataclass
class UnifiedCampaign:
    id: str
    provider: AdProvider
    name: str
    status: str
    daily_budget: float
    spend: float
    impressions: int
    clicks: int
    conversions: int
    roas: float
    cpa: float
    ctr: float
    platform_data: Optional[dict] = None


@dataclass
class UnifiedCreative:
    id: str
    provider: AdProvider
    name: str
    status: str
    campaign_id: str
    impressions: int
    clicks: int
    spend: float
    ctr: float
    fatigue_score: float
    days_running: int


@dataclass
class BudgetAllocationDecision:
    account_id: str
    campaign_id: str
    new_budget: float
    reason: str
    platform_data: Optional[dict] = None


class IntegrationManager:
    def __init__(self):
        self._clients: dict[str, MetaAdsClient | GoogleAdsClient] = {}
        self._accounts: dict[str, AdAccountConfig] = {}

    def register_account(self, config: AdAccountConfig) -> None:
        self._accounts[config.id] = config
        if config.provider == "meta":
            self._clients[config.id] = MetaAdsClient(MetaConfig(
                access_token=config.access_token,
                ad_account_id=config.account_id,
            ))
        elif config.provider == "google":
            self._clients[config.id] = GoogleAdsClient(GoogleAdsConfig(
                developer_token=config.config.get("developerToken", ""),
                client_id=config.config.get("clientId", ""),
                client_secret=config.config.get("clientSecret", ""),
                refresh_token=config.access_token,
                login_customer_id=config.account_id,
            ))

    def get_account(self, account_id: str) -> Optional[AdAccountConfig]:
        return self._accounts.get(account_id)

    async def get_all_campaigns(self, organization_id: str) -> list[UnifiedCampaign]:
        campaigns: list[UnifiedCampaign] = []
        org_accounts = [a for a in self._accounts.values() if a.organization_id == organization_id]

        for account in org_accounts:
            client = self._clients.get(account.id)
            if not client:
                continue
            try:
                if isinstance(client, MetaAdsClient):
                    api_campaigns = await client.get_campaigns()
                    ids = [c.id for c in api_campaigns]
                    insights_map = await client.batch_get_insights("campaign", ids)
                    for c in api_campaigns:
                        ins = insights_map.get(c.id)
                        campaigns.append(UnifiedCampaign(
                            id=c.id,
                            provider="meta",
                            name=c.name,
                            status=c.status,
                            daily_budget=c.daily_budget / 100,
                            spend=ins.spend if ins else 0,
                            impressions=ins.impressions if ins else 0,
                            clicks=ins.clicks if ins else 0,
                            conversions=ins.conversions if ins else 0,
                            roas=ins.roas if ins else 0,
                            cpa=ins.cost_per_conversion if ins else 0,
                            ctr=ins.ctr if ins else 0,
                            platform_data={"metaAdAccountId": account.account_id},
                        ))
                elif isinstance(client, GoogleAdsClient):
                    api_campaigns = await client.get_campaigns()
                    resource_names = [c.resource_name for c in api_campaigns]
                    insights_map = await client.get_insights(resource_names)
                    for c in api_campaigns:
                        ins = insights_map.get(c.id)
                        cost = ins.cost_micros if ins else 0
                        campaigns.append(UnifiedCampaign(
                            id=c.id,
                            provider="google",
                            name=c.name,
                            status=c.status,
                            daily_budget=c.budget_amount_micros / 1_000_000,
                            spend=cost / 1_000_000,
                            impressions=ins.impressions if ins else 0,
                            clicks=ins.clicks if ins else 0,
                            conversions=ins.conversions if ins else 0,
                            roas=ins.roas if ins else 0,
                            cpa=ins.cost_per_conversion if ins else 0,
                            ctr=ins.ctr if ins else 0,
                            platform_data={
                                "googleCampaignResourceName": c.resource_name,
                                "googleBudgetResourceName": c.campaign_budget_resource_name,
                            },
                        ))
            except Exception as err:
                logger.error(f"[integration] Failed fetching campaigns for {account.provider}:{account.account_id}: {err}")
        return campaigns

    async def get_all_creatives(self, organization_id: str) -> list[UnifiedCreative]:
        creatives: list[UnifiedCreative] = []
        org_accounts = [a for a in self._accounts.values() if a.organization_id == organization_id]

        for account in org_accounts:
            client = self._clients.get(account.id)
            if not client or not isinstance(client, MetaAdsClient):
                continue
            try:
                campaigns = await client.get_campaigns()
                for camp in campaigns:
                    ad_sets = await client.get_ad_sets(camp.id)
                    for ad_set in ad_sets:
                        ads = await client.get_ads(ad_set.id)
                        ad_ids = [a.id for a in ads]
                        insights_map = await client.batch_get_insights("ads", ad_ids) if ad_ids else {}
                        for ad in ads:
                            ins = insights_map.get(ad.id)
                            creatives.append(UnifiedCreative(
                                id=ad.id,
                                provider="meta",
                                name=ad.name,
                                status=ad.status,
                                campaign_id=camp.id,
                                impressions=ins.impressions if ins else 0,
                                clicks=ins.clicks if ins else 0,
                                spend=ins.spend if ins else 0,
                                ctr=ins.ctr if ins else 0,
                                fatigue_score=0,
                                days_running=0,
                            ))
            except Exception as err:
                logger.error(f"[integration] Failed fetching creatives for {account.provider}:{account.account_id}: {err}")
        return creatives

    async def execute_budget_allocation(self, decisions: list[BudgetAllocationDecision]) -> dict:
        errors: list[str] = []
        for d in decisions:
            try:
                client = self._clients.get(d.account_id)
                if not client:
                    errors.append(f"No client for account {d.account_id}")
                    continue
                if d.new_budget < 1:
                    errors.append(f"Budget {d.new_budget} too low for {d.campaign_id}")
                    continue
                if isinstance(client, MetaAdsClient):
                    await client.update_campaign_budget(d.campaign_id, round(d.new_budget * 100))
                elif isinstance(client, GoogleAdsClient):
                    budget_resource_name = (d.platform_data or {}).get("budgetResourceName")
                    if not budget_resource_name:
                        errors.append(f"No budget resource name for Google campaign {d.campaign_id}")
                        continue
                    await client.update_budget(budget_resource_name, round(d.new_budget * 1_000_000))
            except Exception as e:
                errors.append(f"Failed to update {d.campaign_id}: {e}")
        return {"success": len(errors) == 0, "errors": errors}


# Singleton
integration_manager = IntegrationManager()
