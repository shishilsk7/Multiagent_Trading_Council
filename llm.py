import os
import time
from dotenv import load_dotenv

load_dotenv()

# OpenRouter free models — fallback
_OPENROUTER_MODELS = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "meta-llama/llama-3.1-8b-instruct:free",
    "mistralai/mistral-7b-instruct:free",
    "google/gemma-2-9b-it:free",
]

_gemini_client = None
_openrouter_client = None
_openai_client = None
_groq_client = None
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


def _get_openai():
    global _openai_client
    if _openai_client is not None:
        return _openai_client
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
        _openai_client = OpenAI(api_key=api_key)
        return _openai_client
    except Exception as e:
        global _last_error
        _last_error = f"OpenAI client configuration failed: {e}"
        return None


def _get_groq():
    global _groq_client
    if _groq_client is not None:
        return _groq_client
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
        _groq_client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
        return _groq_client
    except Exception as e:
        global _last_error
        _last_error = f"Groq client configuration failed: {e}"
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
    
    # 429 Retry logic
    backoff = 1.5
    for attempt in range(3):
        try:
            response = client.generate_content(
                prompt,
                generation_config={"temperature": 0.1, "max_output_tokens": 250},
            )
            return response.text.strip() if response.text else ""
        except Exception as e:
            err = str(e)
            _last_error = f"Gemini Error: {err}"
            print(f"llm.py: Gemini failed (attempt {attempt+1}): {err[:80]}")
            if "429" in err or "quota" in err.lower() or "limit" in err.lower():
                time.sleep(backoff)
                backoff *= 1.8
            else:
                break
    return ""


def _ask_groq(prompt: str) -> str:
    global _last_error
    client = _get_groq()
    if not client:
        return ""
    
    # Try models in order of capability
    for model in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gemma2-9b-it"]:
        backoff = 1.5
        for attempt in range(2):
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
                err = str(e)
                _last_error = f"Groq ({model}) Error: {err}"
                print(f"llm.py: Groq {model} failed (attempt {attempt+1}): {err[:80]}")
                if "429" in err or "quota" in err.lower() or "limit" in err.lower():
                    time.sleep(backoff)
                    backoff *= 1.8
                else:
                    break
    return ""


def _ask_openai(prompt: str) -> str:
    global _last_error
    client = _get_openai()
    if not client:
        return ""
    
    backoff = 1.5
    for attempt in range(2):
        try:
            res = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=250,
                timeout=20,
            )
            text = res.choices[0].message.content
            if text and text.strip():
                return text.strip()
        except Exception as e:
            err = str(e)
            _last_error = f"OpenAI Error: {err}"
            print(f"llm.py: OpenAI failed (attempt {attempt+1}): {err[:80]}")
            if "429" in err or "quota" in err.lower() or "limit" in err.lower():
                time.sleep(backoff)
                backoff *= 1.8
            else:
                break
    return ""


def _ask_openrouter(prompt: str) -> str:
    global _last_error
    client = _get_openrouter()
    if not client:
        return ""
    errors = []
    for model in _OPENROUTER_MODELS:
        backoff = 1.5
        for attempt in range(2):
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
                errors.append(f"{model}: {err[:60]}")
                print(f"llm.py: OpenRouter {model} failed (attempt {attempt+1}): {err[:80]}")
                if "429" in err or "quota" in err.lower() or "limit" in err.lower():
                    time.sleep(backoff)
                    backoff *= 1.8
                else:
                    break
    if errors:
        _last_error = "OpenRouter errors: " + " | ".join(errors)
    return ""


def ask_llm(role: str, prompt: str) -> str:
    """Try Gemini first, fall back to Groq, then OpenAI, then OpenRouter."""
    # 1. Try Gemini
    text = _ask_gemini(prompt)
    if text:
        return text
        
    # 2. Try Groq
    text = _ask_groq(prompt)
    if text:
        return text
        
    # 3. Try OpenAI
    text = _ask_openai(prompt)
    if text:
        return text
        
    # 4. Try OpenRouter
    text = _ask_openrouter(prompt)
    if text:
        return text
        
    return "WAIT (all LLMs unavailable)"


def check_llm_connectivity() -> tuple[bool, str]:
    """Check API key presence only — no live probe (avoids burning rate limit)."""
    providers = []
    if os.getenv("GEMINI_API_KEY"):
        providers.append("Gemini")
    if os.getenv("GROQ_API_KEY"):
        providers.append("Groq")
    if os.getenv("OPENAI_API_KEY"):
        providers.append("OpenAI")
    if os.getenv("OPENROUTER_API_KEY"):
        providers.append("OpenRouter")
        
    if providers:
        return True, f"Configured: {', '.join(providers)}"
    return False, "No API keys configured — set GEMINI_API_KEY, GROQ_API_KEY, OPENAI_API_KEY, or OPENROUTER_API_KEY"


def test_llm_connectivity_live() -> tuple[bool, str]:
    """Perform a live probe to check if the API key is active and working."""
    global _last_error
    tested = []
    
    # 1. Test Gemini
    if os.getenv("GEMINI_API_KEY"):
        client = _get_gemini()
        if client:
            try:
                response = client.generate_content("ping", generation_config={"max_output_tokens": 5})
                if response.text:
                    tested.append("Gemini ✅")
            except Exception as e:
                _last_error = f"Gemini test failed: {e}"
                
    # 2. Test Groq
    if os.getenv("GROQ_API_KEY"):
        client = _get_groq()
        if client:
            try:
                res = client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[{"role": "user", "content": "ping"}],
                    max_tokens=5,
                    timeout=10,
                )
                if res.choices[0].message.content:
                    tested.append("Groq ✅")
            except Exception as e:
                _last_error = f"Groq test failed: {e}"
                
    # 3. Test OpenAI
    if os.getenv("OPENAI_API_KEY"):
        client = _get_openai()
        if client:
            try:
                res = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": "ping"}],
                    max_tokens=5,
                    timeout=10,
                )
                if res.choices[0].message.content:
                    tested.append("OpenAI ✅")
            except Exception as e:
                _last_error = f"OpenAI test failed: {e}"
                
    # 4. Test OpenRouter
    if os.getenv("OPENROUTER_API_KEY"):
        client = _get_openrouter()
        if client:
            try:
                res = client.chat.completions.create(
                    model="meta-llama/llama-3.1-8b-instruct:free",
                    messages=[{"role": "user", "content": "ping"}],
                    max_tokens=5,
                    timeout=10,
                )
                if res.choices[0].message.content:
                    tested.append("OpenRouter ✅")
            except Exception as e:
                _last_error = f"OpenRouter test failed: {e}"

    if tested:
        return True, f"Live probe succeeded for: {', '.join(tested)}"
    return False, f"All configured API tests failed. Last error details: {_last_error}"
