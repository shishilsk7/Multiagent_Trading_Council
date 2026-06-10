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
_last_error = "No errors logged yet."


def get_last_error() -> str:
    global _last_error
    return _last_error


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
    except Exception as e:
        global _last_error
        _last_error = f"Gemini configuration failed: {e}"
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
    except Exception as e:
        global _last_error
        _last_error = f"OpenRouter configuration failed: {e}"
        return None


def _ask_gemini(prompt: str) -> str:
    global _last_error
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
        _last_error = f"Gemini API Error: {e}"
        print(f"llm.py: Gemini failed: {e}")
        return ""


def _ask_openrouter(prompt: str) -> str:
    global _last_error
    client = _get_openrouter()
    if not client:
        return ""
    errors = []
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
            errors.append(f"{model}: {err[:80]}")
            if "429" in err:
                time.sleep(5)
            print(f"llm.py: {model} failed: {err[:80]}")
            continue
    if errors:
        _last_error = "OpenRouter errors: " + " | ".join(errors)
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
    """Check API key presence only — no live probe (avoids burning rate limit)."""
    if os.getenv("GEMINI_API_KEY"):
        client = _get_gemini()
        if client is not None:
            return True, "Gemini ✅ (key set)"
        return False, "GEMINI_API_KEY set but google-generativeai import failed"
    if os.getenv("OPENROUTER_API_KEY"):
        return True, "OpenRouter ✅ (key set)"
    return False, "No API keys configured — set GEMINI_API_KEY or OPENROUTER_API_KEY"


def test_llm_connectivity_live() -> tuple[bool, str]:
    """Perform a live probe to check if the API key is active and working."""
    global _last_error
    
    # Try Gemini if key is set
    if os.getenv("GEMINI_API_KEY"):
        client = _get_gemini()
        if not client:
            return False, "Gemini initialization failed (check package import)"
        try:
            # Send a tiny prompt to check API key validity
            response = client.generate_content("ping", generation_config={"max_output_tokens": 5})
            if response.text:
                return True, "Gemini connection verified! API key is active and working."
        except Exception as e:
            _last_error = f"Gemini Live Probe Failed: {e}"
            return False, f"Gemini connection test failed: {e}"

    # Try OpenRouter if key is set
    if os.getenv("OPENROUTER_API_KEY"):
        client = _get_openrouter()
        if not client:
            return False, "OpenRouter initialization failed"
        try:
            res = client.chat.completions.create(
                model="meta-llama/llama-3.1-8b-instruct:free",
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
                timeout=10,
            )
            if res.choices[0].message.content:
                return True, "OpenRouter connection verified! API key is active and working."
        except Exception as e:
            _last_error = f"OpenRouter Live Probe Failed: {e}"
            return False, f"OpenRouter connection test failed: {e}"

    return False, "No API keys found. Set GEMINI_API_KEY or OPENROUTER_API_KEY first."
