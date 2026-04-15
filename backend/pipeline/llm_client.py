import os
import json
import asyncio
import logging

logger = logging.getLogger(__name__)

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")
MAX_RETRIES = 2


class RateLimitError(Exception):
    pass


async def call_llm(system_prompt: str, user_prompt: str, max_tokens: int = 2000) -> str:
    """
    Single entry point for all LLM calls.
    Returns raw string response. Caller is responsible for JSON parsing.
    Retries once on failure before raising.
    """
    for attempt in range(MAX_RETRIES):
        try:
            if LLM_PROVIDER == "anthropic":
                return await _call_anthropic(system_prompt, user_prompt, max_tokens)
            elif LLM_PROVIDER == "gemini":
                return await _call_gemini(system_prompt, user_prompt, max_tokens)
            elif LLM_PROVIDER == "openai":
                return await _call_openai(system_prompt, user_prompt, max_tokens)
            else:
                raise ValueError(f"Unknown LLM_PROVIDER: {LLM_PROVIDER}")
        except RateLimitError:
            wait = 2 ** attempt * 15   # 15s, then 30s
            logger.warning("Rate limit hit — waiting %ss before retry", wait)
            await asyncio.sleep(wait)
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                raise
            logger.warning("LLM call failed (attempt %d): %s", attempt + 1, e)
            await asyncio.sleep(2)
    raise RuntimeError("LLM call failed after all retries")


async def _call_anthropic(system_prompt: str, user_prompt: str, max_tokens: int) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text


async def _call_gemini(system_prompt: str, user_prompt: str, max_tokens: int) -> str:
    import google.generativeai as genai
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=system_prompt,
    )
    response = model.generate_content(
        user_prompt,
        generation_config=genai.GenerationConfig(
            max_output_tokens=max_tokens,
            temperature=0.1,
        ),
    )
    return response.text


async def _call_openai(system_prompt: str, user_prompt: str, max_tokens: int) -> str:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = await client.chat.completions.create(
        model="gpt-4o",
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content


def _strip_fences(raw: str) -> str:
    """Strip markdown code fences that models sometimes add despite instructions."""
    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.split("```")[1]
        if clean.startswith("json"):
            clean = clean[4:]
    return clean.strip()
