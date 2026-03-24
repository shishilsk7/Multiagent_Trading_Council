import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("OPENROUTER_API_KEY")
if api_key:
    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")
else:
    client = None

# Model roster — primary + fallback per role
MODELS = {
    "technical":  ["google/gemma-3-27b-it:free", "mistralai/mistral-7b-instruct"],
    "momentum":   ["mistralai/mistral-7b-instruct", "meta-llama/llama-3-8b-instruct"],
    "news":       ["mistralai/mistral-7b-instruct", "meta-llama/llama-3-8b-instruct"],
    "risk":       ["google/gemma-3-27b-it:free",   "meta-llama/llama-3-8b-instruct"],
}


def ask_llm(role: str, prompt: str) -> str:
    """Query LLM with automatic model fallback."""
    if not client:
        return "WAIT (API key not configured)"

    for model in MODELS.get(role, ["mistralai/mistral-7b-instruct"]):
        try:
            res = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,   # lower = more deterministic
                max_tokens=200,
            )
            return res.choices[0].message.content.strip()
        except Exception as e:
            print(f"Model {model} failed: {e}")
            continue

    return "WAIT (all LLMs unavailable)"
