# ============================================================
# KLEOS — Google Ads Client (Python)
# Converted from: src/lib/integrations/google-ads.ts
# ============================================================

import time
import httpx
from typing import Optional
from dataclasses import dataclass


@dataclass
class GoogleAdsConfig:
    developer_token: str
    client_id: str
    client_secret: str
    refresh_token: str
    login_customer_id: str


@dataclass
class GoogleCampaign:
    id: str
    resource_name: str
    name: str
    status: str
    campaign_budget_resource_name: str
    budget_amount_micros: int
    advertising_channel_type: str


@dataclass
class GoogleInsights:
    impressions: int
    clicks: int
    cost_micros: float
    conversions: float
    cost_per_conversion: float
    ctr: float
    average_cpc: float
    conversions_value: float
    roas: float


class GoogleAdsClient:
    def __init__(self, config: GoogleAdsConfig):
        self.config = config
        self._access_token: str = ""
        self._token_expires_at: float = 0

    async def _refresh_access_token(self) -> str:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                json={
                    "client_id": self.config.client_id,
                    "client_secret": self.config.client_secret,
                    "refresh_token": self.config.refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            data = response.json()
            self._access_token = data["access_token"]
            self._token_expires_at = time.time() + (data.get("expires_in", 3600))
            return self._access_token

    async def _ensure_token(self) -> str:
        if not self._access_token or time.time() > self._token_expires_at - 60:
            return await self._refresh_access_token()
        return self._access_token

    async def _query(self, gaql: str) -> dict:
        token = await self._ensure_token()
        url = f"https://googleads.googleapis.com/v18/customers/{self.config.login_customer_id}/googleAds:search"
        headers = {
            "Authorization": f"Bearer {token}",
            "developer-token": self.config.developer_token,
            "login-customer-id": self.config.login_customer_id,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.post(url, json={"query": gaql, "pageSize": 10000}, headers=headers)
                if response.status_code == 401:
                    await self._refresh_access_token()
                    headers["Authorization"] = f"Bearer {self._access_token}"
                    response = await client.post(url, json={"query": gaql, "pageSize": 10000}, headers=headers)
                return response.json()
            except Exception as e:
                raise e

    async def get_campaigns(self) -> list[GoogleCampaign]:
        data = await self._query("""
            SELECT
                campaign.id, campaign.resource_name, campaign.name, campaign.status,
                campaign.campaign_budget, campaign.advertising_channel_type,
                campaign_budget.amount_micros
            FROM campaign
            LEFT JOIN campaign_budget ON campaign.campaign_budget = campaign_budget.resource_name
            WHERE campaign.status != 'REMOVED'
        """)
        results = []
        for r in data.get("results", []):
            results.append(GoogleCampaign(
                id=r["campaign"]["id"],
                resource_name=r["campaign"]["resourceName"],
                name=r["campaign"]["name"],
                status=r["campaign"]["status"],
                campaign_budget_resource_name=r["campaign"].get("campaignBudget", ""),
                budget_amount_micros=int(r.get("campaignBudget", {}).get("amountMicros", "0")),
                advertising_channel_type=r["campaign"]["advertisingChannelType"],
            ))
        return results

    async def get_insights(self, campaign_resource_names: list[str], date_range: str = "LAST_30_DAYS") -> dict[str, GoogleInsights]:
        results: dict[str, GoogleInsights] = {}
        if not campaign_resource_names:
            return results

        batch_size = 50
        for i in range(0, len(campaign_resource_names), batch_size):
            batch = campaign_resource_names[i:i + batch_size]
            conditions = " OR ".join(f"campaign.resource_name = '{name}'" for name in batch)
            data = await self._query(f"""
                SELECT campaign.id, campaign.resource_name,
                    metrics.impressions, metrics.clicks, metrics.cost_micros,
                    metrics.conversions, metrics.cost_per_conversion, metrics.ctr,
                    metrics.average_cpc, metrics.conversions_value
                FROM campaign
                WHERE ({conditions})
                    AND segments.date DURING {date_range}
            """)
            for row in data.get("results", []):
                m = row.get("metrics", {})
                cost_micros = float(m.get("costMicros", 0))
                conversions_value = float(m.get("conversionsValue", 0))
                results[str(row["campaign"]["id"])] = GoogleInsights(
                    impressions=int(m.get("impressions", 0)),
                    clicks=int(m.get("clicks", 0)),
                    cost_micros=cost_micros,
                    conversions=float(m.get("conversions", 0)),
                    cost_per_conversion=float(m.get("costPerConversion", 0)) / 1_000_000,
                    ctr=float(m.get("ctr", 0)),
                    average_cpc=float(m.get("averageCpc", 0)) / 1_000_000,
                    conversions_value=conversions_value,
                    roas=conversions_value / (cost_micros / 1_000_000) if cost_micros > 0 else 0,
                )
        return results

    async def mutate(self, operations: list[dict]) -> None:
        token = await self._ensure_token()
        url = f"https://googleads.googleapis.com/v18/customers/{self.config.login_customer_id}/googleAds:mutate"
        async with httpx.AsyncClient(timeout=15.0) as client:
            await client.post(
                url,
                json={"mutateOperations": [{"mutateOperation": op} for op in operations]},
                headers={
                    "Authorization": f"Bearer {token}",
                    "developer-token": self.config.developer_token,
                    "login-customer-id": self.config.login_customer_id,
                },
            )

    async def update_budget(self, campaign_budget_resource_name: str, amount_micros: int) -> None:
        await self.mutate([{
            "campaignBudgetOperation": {
                "update": {
                    "resourceName": campaign_budget_resource_name,
                    "amountMicros": amount_micros,
                },
                "updateMask": "amount_micros",
            },
        }])

    async def pause_campaign(self, campaign_resource_name: str) -> None:
        await self.mutate([{
            "campaignOperation": {
                "update": {
                    "resourceName": campaign_resource_name,
                    "status": "PAUSED",
                },
                "updateMask": "status",
            },
        }])
