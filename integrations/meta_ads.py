# ============================================================
# KLEOS — Meta Ads Client (Python)
# Converted from: src/lib/integrations/meta-ads.ts
# ============================================================

import httpx
import time
from typing import Optional
from dataclasses import dataclass


@dataclass
class MetaConfig:
    access_token: str
    ad_account_id: str
    access_token_expires_at: Optional[int] = None


@dataclass
class MetaCampaign:
    id: str
    name: str
    status: str
    objective: str
    daily_budget: float
    lifetime_budget: float
    start_time: str


@dataclass
class MetaAdSet:
    id: str
    name: str
    campaign_id: str
    status: str
    daily_budget: float
    bid_amount: float
    optimization_goal: str


@dataclass
class MetaAd:
    id: str
    name: str
    ad_set_id: str
    status: str
    creative_id: str


@dataclass
class MetaInsights:
    impressions: int
    clicks: int
    spend: float
    ctr: float
    cpm: float
    cpc: float
    reach: int
    frequency: float
    conversions: int
    cost_per_conversion: float
    roas: float


# Simple in-memory LRU-like cache
class _InsightsCache:
    def __init__(self, max_size: int = 200, ttl_ms: int = 300_000):
        self._cache: dict[str, tuple[MetaInsights, float]] = {}
        self.max_size = max_size
        self.ttl_ms = ttl_ms

    def get(self, key: str) -> Optional[MetaInsights]:
        entry = self._cache.get(key)
        if entry:
            value, ts = entry
            if (time.time() * 1000 - ts) < self.ttl_ms:
                return value
            del self._cache[key]
        return None

    def set(self, key: str, value: MetaInsights) -> None:
        if len(self._cache) >= self.max_size:
            # Remove oldest entry
            oldest = min(self._cache, key=lambda k: self._cache[k][1])
            del self._cache[oldest]
        self._cache[key] = (value, time.time() * 1000)


_insights_cache = _InsightsCache()


class MetaAdsClient:
    BASE_URL = "https://graph.facebook.com/v21.0"

    def __init__(self, config: MetaConfig):
        self.config = config

    async def _get(self, path: str, params: Optional[dict] = None) -> dict:
        if params is None:
            params = {}
        params["access_token"] = self.config.access_token
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(f"{self.BASE_URL}{path}", params=params)
            response.raise_for_status()
            return response.json()

    async def _paginate(self, path: str, params: Optional[dict] = None) -> list[dict]:
        if params is None:
            params = {}
        items: list[dict] = []
        cursor: Optional[str] = None
        while True:
            p = {**params, "after": cursor} if cursor else params
            data = await self._get(path, p)
            items.extend(data.get("data", []))
            cursor = data.get("paging", {}).get("cursors", {}).get("after")
            if not cursor or len(items) >= 500:
                break
        return items

    async def get_campaigns(self) -> list[MetaCampaign]:
        items = await self._paginate(
            f"/act_{self.config.ad_account_id}/campaigns",
            {"fields": "id,name,status,objective,daily_budget,lifetime_budget,start_time", "limit": "100"},
        )
        return [
            MetaCampaign(
                id=c["id"],
                name=c["name"],
                status=c["status"],
                objective=c.get("objective", ""),
                daily_budget=float(c.get("daily_budget") or 0),
                lifetime_budget=float(c.get("lifetime_budget") or 0),
                start_time=c.get("start_time", ""),
            )
            for c in items
        ]

    async def get_ad_sets(self, campaign_id: str) -> list[MetaAdSet]:
        items = await self._paginate(
            f"/{campaign_id}/adsets",
            {"fields": "id,name,campaign_id,status,daily_budget,bid_amount,optimization_goal", "limit": "100"},
        )
        return [
            MetaAdSet(
                id=a["id"],
                name=a["name"],
                campaign_id=a.get("campaign_id", ""),
                status=a["status"],
                daily_budget=float(a.get("daily_budget") or 0),
                bid_amount=float(a.get("bid_amount") or 0),
                optimization_goal=a.get("optimization_goal", ""),
            )
            for a in items
        ]

    async def get_ads(self, ad_set_id: str) -> list[MetaAd]:
        items = await self._paginate(
            f"/{ad_set_id}/ads",
            {"fields": "id,name,adset_id,status,creative{id}", "limit": "100"},
        )
        return [
            MetaAd(
                id=a["id"],
                name=a["name"],
                ad_set_id=a.get("adset_id", ""),
                status=a["status"],
                creative_id=(a.get("creative") or {}).get("id", ""),
            )
            for a in items
        ]

    async def get_insights(
        self, level: str, entity_id: str, date_preset: str = "last_30d"
    ) -> MetaInsights:
        cache_key = f"{entity_id}:{date_preset}"
        cached = _insights_cache.get(cache_key)
        if cached:
            return cached

        data = await self._get(
            f"/{entity_id}/insights",
            {
                "fields": "impressions,clicks,spend,ctr,cpm,cpc,reach,frequency,conversions,cost_per_conversion,action_values",
                "date_preset": date_preset,
                "level": level,
            },
        )
        d = (data.get("data") or [{}])[0]
        action_values = d.get("action_values") or []
        purchase_value = next(
            (float(a["value"]) for a in action_values if a.get("action_type") == "purchase"), 0.0
        )
        spend = float(d.get("spend") or 0)
        result = MetaInsights(
            impressions=int(d.get("impressions") or 0),
            clicks=int(d.get("clicks") or 0),
            spend=spend,
            ctr=float(d.get("ctr") or 0),
            cpm=float(d.get("cpm") or 0),
            cpc=float(d.get("cpc") or 0),
            reach=int(d.get("reach") or 0),
            frequency=float(d.get("frequency") or 0),
            conversions=int(d.get("conversions") or 0),
            cost_per_conversion=float(d.get("cost_per_conversion") or 0),
            roas=purchase_value / spend if spend > 0 else 0,
        )
        _insights_cache.set(cache_key, result)
        return result

    async def batch_get_insights(
        self, level: str, entity_ids: list[str], date_preset: str = "last_30d"
    ) -> dict[str, MetaInsights]:
        results: dict[str, MetaInsights] = {}
        batch_size = 50
        for i in range(0, len(entity_ids), batch_size):
            batch = entity_ids[i:i + batch_size]
            import json
            data = await self._get(
                f"/act_{self.config.ad_account_id}/insights",
                {
                    "fields": "id,impressions,clicks,spend,ctr,cpm,cpc,reach,frequency,conversions,cost_per_conversion",
                    "date_preset": date_preset,
                    "level": level,
                    "filter": json.dumps([{"field": f"{level}.id", "operator": "IN", "value": [id_]} for id_ in batch]),
                },
            )
            for row in data.get("data") or []:
                spend = float(row.get("spend") or 0)
                results[row["id"]] = MetaInsights(
                    impressions=int(row.get("impressions") or 0),
                    clicks=int(row.get("clicks") or 0),
                    spend=spend,
                    ctr=float(row.get("ctr") or 0),
                    cpm=float(row.get("cpm") or 0),
                    cpc=float(row.get("cpc") or 0),
                    reach=int(row.get("reach") or 0),
                    frequency=float(row.get("frequency") or 0),
                    conversions=int(row.get("conversions") or 0),
                    cost_per_conversion=float(row.get("cost_per_conversion") or 0),
                    roas=0,
                )
        return results

    async def update_campaign_budget(self, campaign_id: str, daily_budget_in_paise: int) -> None:
        if daily_budget_in_paise < 100:
            raise Exception(f"Budget {daily_budget_in_paise} too low for campaign {campaign_id}")
        async with httpx.AsyncClient(timeout=15.0) as client:
            await client.post(
                f"{self.BASE_URL}/{campaign_id}",
                data={"daily_budget": daily_budget_in_paise, "access_token": self.config.access_token},
            )

    async def update_ad_set_budget(self, ad_set_id: str, daily_budget_in_paise: int) -> None:
        async with httpx.AsyncClient(timeout=15.0) as client:
            await client.post(
                f"{self.BASE_URL}/{ad_set_id}",
                data={"daily_budget": daily_budget_in_paise, "access_token": self.config.access_token},
            )

    async def update_campaign_status(self, campaign_id: str, status: str) -> None:
        async with httpx.AsyncClient(timeout=15.0) as client:
            await client.post(
                f"{self.BASE_URL}/{campaign_id}",
                data={"status": status, "access_token": self.config.access_token},
            )
