# ============================================================
# KLEOS — Multi-LLM Client (Python)
# Auto-detects provider: OPENAI > ANTHROPIC > OLLAMA (fallback)
# Converted from: src/lib/ai/llm.ts
# ============================================================

import os
import httpx
from typing import Literal, Optional

LLMProvider = Literal["openai", "anthropic", "ollama"]


class LLMMessage:
    def __init__(self, role: Literal["system", "user", "assistant"], content: str):
        self.role = role
        self.content = content

    def to_dict(self):
        return {"role": self.role, "content": self.content}


class LLMOptions:
    def __init__(
        self,
        temperature: float = 0.7,
        max_tokens: int = 4000,
        model: Optional[str] = None,
        provider: Optional[LLMProvider] = None,
    ):
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.model = model
        self.provider = provider


# ─── Provider Detection ───────────────────────────────────
def detect_provider() -> LLMProvider:
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "ollama"


def get_provider_config(provider: Optional[LLMProvider] = None) -> dict:
    p = provider or detect_provider()
    if p == "openai":
        return {
            "provider": "openai",
            "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            "api_key": os.environ.get("OPENAI_API_KEY"),
        }
    elif p == "anthropic":
        return {
            "provider": "anthropic",
            "model": os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"),
            "api_key": os.environ.get("ANTHROPIC_API_KEY"),
        }
    else:
        return {
            "provider": "ollama",
            "model": os.environ.get("OLLAMA_MODEL", "mistral-nemo:latest"),
            "base_url": os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        }


# ─── OpenAI ───────────────────────────────────────────────
async def call_openai(messages: list[LLMMessage], options: LLMOptions) -> str:
    config = get_provider_config("openai")
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config['api_key']}",
            },
            json={
                "model": options.model or config["model"],
                "messages": [m.to_dict() for m in messages],
                "temperature": options.temperature,
                "max_tokens": options.max_tokens,
            },
        )
        if not response.is_success:
            raise Exception(f"OpenAI error: {response.text}")
        data = response.json()
        return data["choices"][0]["message"]["content"] or ""


# ─── Anthropic ────────────────────────────────────────────
async def call_anthropic(messages: list[LLMMessage], options: LLMOptions) -> str:
    config = get_provider_config("anthropic")
    system_msg = next((m.content for m in messages if m.role == "system"), "")
    user_messages = [m.to_dict() for m in messages if m.role != "system"]

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": config["api_key"] or "",
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": options.model or config["model"],
                "max_tokens": options.max_tokens,
                "temperature": options.temperature,
                "system": system_msg,
                "messages": user_messages,
            },
        )
        if not response.is_success:
            raise Exception(f"Anthropic error: {response.text}")
        data = response.json()
        return data["content"][0]["text"] or ""


# ─── Ollama ───────────────────────────────────────────────
async def call_ollama(messages: list[LLMMessage], options: LLMOptions) -> str:
    config = get_provider_config("ollama")
    async with httpx.AsyncClient(timeout=300.0) as client:  # 5 min for long-form local generation
        response = await client.post(
            f"{config['base_url']}/api/chat",
            headers={"Content-Type": "application/json"},
            json={
                "model": options.model or config["model"],
                "messages": [m.to_dict() for m in messages],
                "stream": False,
                "options": {
                    "temperature": options.temperature,
                    "top_p": 0.9,
                    "num_predict": options.max_tokens,
                },
            },
        )
        if not response.is_success:
            raise Exception(f"Ollama error: {response.text}")
        data = response.json()
        return data["message"]["content"] or ""


# ─── Unified Chat Interface ──────────────────────────────
async def llm_chat(messages: list[LLMMessage], options: Optional[LLMOptions] = None) -> str:
    if options is None:
        options = LLMOptions()
    provider = options.provider or detect_provider()
    if provider == "openai":
        return await call_openai(messages, options)
    elif provider == "anthropic":
        return await call_anthropic(messages, options)
    else:
        return await call_ollama(messages, options)


# ─── Convenience: Generate with system + user prompt ─────
async def llm_generate(prompt: str, system: str, options: Optional[LLMOptions] = None) -> str:
    return await llm_chat(
        [
            LLMMessage("system", system),
            LLMMessage("user", prompt),
        ],
        options,
    )


# ─── Health Check ─────────────────────────────────────────
async def check_llm_health() -> dict:
    config = get_provider_config()
    try:
        provider = config["provider"]
        if provider == "openai":
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {config['api_key']}"},
                )
            return {"provider": "openai", "healthy": res.is_success, "model": config["model"]}
        elif provider == "anthropic":
            return {"provider": "anthropic", "healthy": bool(config["api_key"]), "model": config["model"]}
        else:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{config['base_url']}/api/tags")
            return {
                "provider": "ollama",
                "healthy": res.is_success,
                "model": config["model"],
                "error": None if res.is_success else "Ollama not reachable",
            }
    except Exception as e:
        return {"provider": config["provider"], "healthy": False, "model": config["model"], "error": str(e)}


# ─── Backward Compatibility ───────────────────────────────
async def ollama_chat(messages: list[LLMMessage], options: Optional[dict] = None) -> str:
    opts = LLMOptions(
        temperature=(options or {}).get("temperature", 0.7),
        max_tokens=(options or {}).get("num_predict", 4000),
        model=(options or {}).get("model"),
        provider="ollama",
    )
    return await llm_chat(messages, opts)


async def check_ollama_health() -> bool:
    result = await check_llm_health()
    return result["healthy"]
