# ============================================================
# KLEOS — Agent Executor
# Converted from: src/lib/ai/agents.ts
# ============================================================

import time
import os
from typing import Optional
from dataclasses import dataclass

from backend.ai.llm import LLMMessage, LLMOptions, llm_chat, detect_provider, get_provider_config
from backend.ai.prompts import AGENTS


@dataclass
class AgentRequest:
    agent_id: str
    action: str
    input: dict
    context: Optional[dict] = None
    provider: Optional[str] = None


@dataclass
class AgentResponse:
    success: bool
    output: str
    agent_id: str
    action: str
    provider: str
    model: str
    duration_ms: int
    error: Optional[str] = None


async def execute_agent(request: AgentRequest) -> AgentResponse:
    start = int(time.time() * 1000)
    agent = AGENTS.get(request.agent_id)
    provider = request.provider or detect_provider()
    config = get_provider_config(provider)

    if not agent:
        return AgentResponse(
            success=False,
            output="",
            agent_id=request.agent_id,
            action=request.action,
            provider=provider,
            model=config["model"],
            duration_ms=int(time.time() * 1000) - start,
            error=f"Unknown agent: {request.agent_id}",
        )

    # Build input string
    input_str = "\n".join(
        f"{k}: {v}" if not isinstance(v, (dict, list)) else f"{k}: {__import__('json').dumps(v)}"
        for k, v in request.input.items()
        if v is not None
    )

    context_str = ""
    if request.context:
        context_lines = "\n".join(
            f"{k}: {v}" if not isinstance(v, (dict, list)) else f"{k}: {__import__('json').dumps(v)}"
            for k, v in request.context.items()
        )
        context_str = f"\n\nContext:\n{context_lines}"

    user_prompt = f"Task: {request.action}\n\nInput:\n{input_str}{context_str}"

    messages = [
        LLMMessage("system", agent["system"]),
        LLMMessage("user", user_prompt),
    ]

    try:
        options = LLMOptions(
            temperature=0.7,
            max_tokens=int(os.environ.get("AGENT_MAX_TOKENS", "4000")),
            provider=provider,
        )
        output = await llm_chat(messages, options)
        return AgentResponse(
            success=True,
            output=output,
            agent_id=request.agent_id,
            action=request.action,
            provider=provider,
            model=config["model"],
            duration_ms=int(time.time() * 1000) - start,
        )
    except Exception as error:
        return AgentResponse(
            success=False,
            output="",
            agent_id=request.agent_id,
            action=request.action,
            provider=provider,
            model=config["model"],
            duration_ms=int(time.time() * 1000) - start,
            error=str(error),
        )


async def generate_with_agent(
    agent_id: str,
    action: str,
    input: dict,
    context: Optional[dict] = None,
    provider: Optional[str] = None,
) -> str:
    response = await execute_agent(AgentRequest(
        agent_id=agent_id,
        action=action,
        input=input,
        context=context,
        provider=provider,
    ))
    if not response.success:
        raise Exception(response.error or "Agent failed")
    return response.output
