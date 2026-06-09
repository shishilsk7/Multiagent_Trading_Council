import os
import time
from dotenv import load_dotenv

load_dotenv()

# Models verified available on OpenRouter free tier (June 2026)
_FREE_MODELS = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "meta-llama/llama-3.1-8b-instruct:free",
    "mistralai/mistral-7b-instruct:free",
    "google/gemma-2-9b-it:free",
    "nousresearch/hermes-3-llama-3.1-405b:free",
]

MODELS = {
    "technical": _FREE_MODELS,
    "momentum":  _FREE_MODELS,
    "news":      _FREE_MODELS,
    "risk":      _FREE_MODELS,
}

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
        _client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")
        return _client
    except Exception:
        return None


def ask_llm(role: str, prompt: str) -> str:
    """
    Query LLM with automatic model fallback.
    - Tries each model in order
    - On rate-limit (429) waits 5s before trying next model
    - Returns "WAIT (...)" only if ALL models fail
    """
    client = _get_client()
    if not client:
        return "WAIT (API key not configured)"

    last_error = ""
    for model in MODELS.get(role, MODELS["technical"]):
        try:
            res = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=250,
                timeout=25,
            )
            text = res.choices[0].message.content
            if text and text.strip():
                return text.strip()
        except Exception as e:
            last_error = str(e)
            # Rate limit — brief pause before trying next model
            if "429" in last_error or "rate" in last_error.lower():
                time.sleep(5)
            print(f"llm.py: {model} failed ({last_error[:80]})")
            continue

    return f"WAIT (all LLMs unavailable: {last_error[:120]})"


def check_llm_connectivity() -> tuple[bool, str]:
    """
    Quick connectivity probe — tries each free model until one responds.
    Returns (ok: bool, message: str).
    """
    client = _get_client()
    if not client:
        return False, "API key not configured"
    for model in _FREE_MODELS:
        try:
            res = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Reply: OK"}],
                temperature=0,
                max_tokens=5,
                timeout=10,
            )
            text = (res.choices[0].message.content or "").strip()
            if text:
                return True, f"Connected ({model.split('/')[1]})"
        except Exception as e:
            err = str(e)
            if "401" in err:
                return False, "Invalid API key"
            if "429" in err:
                return False, "Rate limited — wait 1 min"
            continue
    return False, "All models unavailable — check openrouter.ai/models for free models"
