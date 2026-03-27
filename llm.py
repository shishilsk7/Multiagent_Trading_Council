import os
from dotenv import load_dotenv

load_dotenv()

# Use openrouter/free as primary — auto-picks best available free model
# Specific models as fallbacks in case the router has issues
MODELS = {
    "technical": ["openrouter/auto", "meta-llama/llama-3.3-70b-instruct:free", "qwen/qwen3-8b:free"],
    "momentum":  ["openrouter/auto", "meta-llama/llama-3.3-70b-instruct:free", "qwen/qwen3-8b:free"],
    "news":      ["openrouter/auto", "meta-llama/llama-3.3-70b-instruct:free", "qwen/qwen3-8b:free"],
    "risk":      ["openrouter/auto", "meta-llama/llama-3.3-70b-instruct:free", "qwen/qwen3-8b:free"],
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
    """Query LLM with automatic model fallback."""
    client = _get_client()
    if not client:
        return "WAIT (API key not configured)"

    for model in MODELS.get(role, ["openrouter/auto"]):
        try:
            res = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=250,
                timeout=20,
            )
            text = res.choices[0].message.content
            if text and text.strip():
                return text.strip()
        except Exception as e:
            print(f"Model {model} failed: {e}")
            continue

    return "WAIT (all LLMs unavailable)"