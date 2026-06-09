import os
import time
from dotenv import load_dotenv

load_dotenv()

# Gemini free tier: 15 req/min, 1500 req/day — primary
# OpenRouter free models — fallback if Gemini fails
_OPENROUTER_MODELS = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "meta-llama/llama-3.1-8b-instruct:free",
    "mistralai/mistral-7b-instruct:free",
    "google/gemma-2-9b-it:free",
]

_gemini_client = None
_openrouter_client = None


def _get_gemini():
    global _gemini_client
    if _gemini_client is not None:
        return _gemini_client
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        _gemini_client = genai.GenerativeModel("gemini-2.0-flash")
        return _gemini_client
    except Exception:
        return None


def _get_openrouter():
    global _openrouter_client
    if _openrouter_client is not None:
        return _openrouter_client
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
        _openrouter_client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")
        return _openrouter_client
    except Exception:
        return None


def _ask_gemini(prompt: str) -> str:
    client = _get_gemini()
    if not client:
        return ""
    try:
        response = client.generate_content(
            prompt,
            generation_config={"temperature": 0.1, "max_output_tokens": 250},
        )
        return response.text.strip() if response.text else ""
    except Exception as e:
        print(f"llm.py: Gemini failed: {e}")
        return ""


def _ask_openrouter(prompt: str) -> str:
    client = _get_openrouter()
    if not client:
        return ""
    for model in _OPENROUTER_MODELS:
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
            err = str(e)
            if "429" in err:
                time.sleep(5)
            print(f"llm.py: {model} failed: {err[:80]}")
            continue
    return ""


def ask_llm(role: str, prompt: str) -> str:
    """Try Gemini first, fall back to OpenRouter."""
    text = _ask_gemini(prompt)
    if text:
        return text
    text = _ask_openrouter(prompt)
    if text:
        return text
    return "WAIT (all LLMs unavailable)"


def check_llm_connectivity() -> tuple[bool, str]:
    """Probe Gemini first, then OpenRouter. Returns (ok, message)."""
    gemini_key = os.getenv("GEMINI_API_KEY")
    or_key     = os.getenv("OPENROUTER_API_KEY")

    # Try Gemini
    if gemini_key:
        client = _get_gemini()
        if client is None:
            gemini_err = "google-generativeai not installed or import failed"
        else:
            try:
                r = client.generate_content(
                    "Reply: OK",
                    generation_config={"temperature": 0, "max_output_tokens": 5},
                )
                if r.text and r.text.strip():
                    return True, "Gemini ✅"
                gemini_err = "Empty response"
            except Exception as e:
                gemini_err = str(e)[:100]
    else:
        gemini_err = "GEMINI_API_KEY not set"

    # Try OpenRouter
    if or_key:
        or_client = _get_openrouter()
        for model in _OPENROUTER_MODELS[:2]:
            try:
                res = or_client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": "Reply: OK"}],
                    temperature=0, max_tokens=5, timeout=10,
                )
                if res.choices[0].message.content:
                    return True, f"OpenRouter ✅ ({model.split('/')[1]})"
            except Exception as e:
                err = str(e)
                if "401" in err: return False, f"Gemini: {gemini_err} | OpenRouter: Invalid key"
                if "429" in err: return False, f"Gemini: {gemini_err} | OpenRouter: Rate limited"
                continue
        return False, f"Gemini: {gemini_err} | OpenRouter: all models failed"
    else:
        or_err = "OPENROUTER_API_KEY not set"

    return False, f"Gemini: {gemini_err} | OpenRouter: {or_err}"
