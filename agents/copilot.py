# ============================================================
# KLEOS — Copilot Agent (Python)
# ============================================================

import json
from typing import Optional, Literal
from dataclasses import dataclass, field

from backend.ai.agents import generate_with_agent
from backend.memory.shared_memory import shared_memory
from backend.integrations.manager import integration_manager
from backend.agents.campaign_agent import campaign_agent
from backend.agents.creative_agent import creative_agent
from backend.agents.social_agent import social_agent
from backend.agents.seo_agent import seo_agent
from backend.agents.analytics_agent import analytics_agent

IntentType = Literal["copilot", "campaign_agent", "creative_agent", "social_agent", "seo_agent", "analytics_agent"]

CAMPAIGN_TRIGGERS = [
    "campaign", "ad budget", "ads", "spend", "pause ad", "scale campaign", 
    "bid", "optimize campaign", "allocate budget", "marketing campaign", 
    "meta ads", "google ads", "increase budget", "decrease budget", 
    "increase spend", "decrease spend", "adjust budget"
]

CREATIVE_TRIGGERS = [
    "creative", "generate ad", "visual", "make video", "write caption", 
    "ad script", "write reel", "blog post", "landing page", "email copy", 
    "generate variant", "refresh creative", "make a 15-second", "instagram reel"
]

SOCIAL_TRIGGERS = [
    "post", "schedule", "publish", "tweet", "linkedin", "instagram post", 
    "track engagement", "trending content", "reply to comments", "social media"
]

SEO_TRIGGERS = [
    "seo", "search engine", "keywords", "google ranking", "website page", 
    "suggest blog topics", "search query", "meta description", "rank for", "rank my website"
]

ANALYTICS_TRIGGERS = [
    "report", "analytics", "roas", "roi", "metric", "sales drop", "revenue", 
    "performance overview", "campaign performance", "track results", "measure return",
    "why did my sales drop", "what's working"
]


@dataclass
class CopilotRequest:
    message: str
    conversation_history: list[dict]  # [{role: "user"|"assistant", content: str}]
    organization_id: str


@dataclass
class CopilotResponse:
    message: str
    intent: str
    triggered_actions: list[dict] = field(default_factory=list)  # [{type, description}]


class CopilotService:
    async def process_message(self, request: CopilotRequest) -> CopilotResponse:
        message = request.message
        conversation_history = request.conversation_history
        organization_id = request.organization_id

        intent = self._classify_intent(message, conversation_history)
        context = await self._build_context(organization_id)
        triggered_actions: list[dict] = []
        response_message: str

        try:
            if intent == "campaign_agent":
                triggered_actions.append({"type": "campaign_optimization", "description": "Routing to Campaign Agent"})
                response_message = await campaign_agent.process_message(organization_id, message)

            elif intent == "creative_agent":
                triggered_actions.append({"type": "creative_generation", "description": "Routing to Creative Agent"})
                response_message = await creative_agent.process_message(organization_id, message)

            elif intent == "social_agent":
                triggered_actions.append({"type": "social_management", "description": "Routing to Social Agent"})
                response_message = await social_agent.process_message(organization_id, message)

            elif intent == "seo_agent":
                triggered_actions.append({"type": "seo_optimization", "description": "Routing to SEO Agent"})
                response_message = await seo_agent.process_message(organization_id, message)

            elif intent == "analytics_agent":
                triggered_actions.append({"type": "analytics_report", "description": "Routing to Analytics Agent"})
                response_message = await analytics_agent.process_message(organization_id, message)

            else:  # "copilot"
                response_message = await generate_with_agent("copilot", "answerQuestion", {
                    "question": message,
                    "context": context,
                    "conversationHistory": json.dumps(conversation_history[-6:]),
                }, {"brandContext": context})

        except Exception as err:
            response_message = f"I encountered an error processing that request: {err}. Could you try rephrasing or ask me something else?"

        return CopilotResponse(
            message=response_message,
            intent=intent,
            triggered_actions=triggered_actions,
        )

    def _classify_intent(self, message: str, history: list[dict]) -> str:
        lower = message.lower().strip()

        # If it's a generic definitional question (e.g., "what is ROAS?", "define conversion rate")
        # and doesn't ask about specific account/campaign data (containing "my", "our", "we", "this week")
        if any(q in lower for q in ["what is", "define", "explain", "who are you"]) and not any(own in lower for own in ["my", "our", "we"]):
            return "copilot"

        is_campaign = any(t in lower for t in CAMPAIGN_TRIGGERS)
        is_creative = any(t in lower for t in CREATIVE_TRIGGERS)
        is_social = any(t in lower for t in SOCIAL_TRIGGERS)
        is_seo = any(t in lower for t in SEO_TRIGGERS)
        is_analytics = any(t in lower for t in ANALYTICS_TRIGGERS)

        # Priority order
        if is_campaign:
            return "campaign_agent"
        if is_creative:
            return "creative_agent"
        if is_social:
            return "social_agent"
        if is_seo:
            return "seo_agent"
        if is_analytics:
            return "analytics_agent"
        return "copilot"

    async def _build_context(self, organization_id: str) -> str:
        return await shared_memory.build_context_for_agent(organization_id, "copilot")


# Singleton
copilot_service = CopilotService()
