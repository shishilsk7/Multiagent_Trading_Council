import os
from dotenv import load_dotenv

load_dotenv()

# Model roster — primary + fallback per role
MODELS = {
    "technical": ["google/gemma-3-27b-it:free", "mistralai/mistral-7b-instruct"],
    "momentum":  ["mistralai/mistral-7b-instruct", "meta-llama/llama-3-8b-instruct"],
    "news":      ["mistralai/mistral-7b-instruct", "meta-llama/llama-3-8b-instruct"],
    "risk":      ["google/gemma-3-27b-it:free",    "meta-llama/llama-3-8b-instruct"],
}

# Lazy client — only created when ask_llm() is first called, NOT at import time
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
    """Query LLM with automatic model fallback."""
    client = _get_client()
    if not client:
        return "WAIT (API key not configured)"

    for model in MODELS.get(role, ["mistralai/mistral-7b-instruct"]):
        try:
            res = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=200,
            )
            return res.choices[0].message.content.strip()
        except Exception as e:
            print(f"Model {model} failed: {e}")
            continue

    return "WAIT (all LLMs unavailable)"