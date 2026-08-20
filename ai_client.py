"""
ai_client.py — Free AI provider with intelligent fallback for Pinterest content
Primary   : Groq with Primary & Fallback API Keys (openai/gpt-oss-120b, qwen3.6, etc.)
Secondary : OpenRouter Free Models with Primary & Fallback API Keys (poolside, gemma, gpt-oss, etc.)
Fallback  : returns None → caller uses hardcoded template
"""

import os
import re
import sys
import time
import requests
from typing import List, Optional

# Add parent directory to path to load secrets_manager
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from secrets_manager import inject_to_env, get_secret
    inject_to_env()
except Exception:
    get_secret = lambda k: os.getenv(k, "")


def _get_api_keys(primary_name: str, fallback_names: List[str]) -> List[str]:
    """Retrieve all available API keys (primary + fallbacks), deduplicated and non-empty."""
    keys: List[str] = []
    try:
        k = get_secret(primary_name)
        if k and k.strip():
            keys.append(k.strip())
    except Exception:
        pass

    for name in fallback_names:
        try:
            k = get_secret(name)
            if k and k.strip() and k.strip() not in keys:
                keys.append(k.strip())
        except Exception:
            pass

    for name in [primary_name] + fallback_names:
        k = os.getenv(name, "").strip()
        if k and k not in keys:
            keys.append(k)

    return keys


_GROQ_KEYS = _get_api_keys("GROQ_API_KEY", ["GROQ_API_KEY_FALLBACK", "FALLBACK_GROQ_API_KEY"])
_OPENROUTER_KEYS = _get_api_keys("OPENROUTER_API_KEY", ["OPENROUTER_API_KEY_FALLBACK", "FALLBACK_OPENROUTER_API_KEY"])

GROQ_KEY = _GROQ_KEYS[0] if _GROQ_KEYS else ""
OPENROUTER_KEY = _OPENROUTER_KEYS[0] if _OPENROUTER_KEYS else ""

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Active and validated model pools
_GROQ_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.6-27b",
    "groq/compound-mini",
    "groq/compound",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]

_OPENROUTER_FREE_MODELS = [
    "openrouter/free",
    "poolside/laguna-s-2.1:free",
    "poolside/laguna-xs-2.1:free",
    "google/gemma-4-26b-a4b-it:free",
    "google/gemma-4-31b-it:free",
    "openai/gpt-oss-20b:free",
    "nvidia/nemotron-3-nano-30b-a3b:free",
    "z-ai/glm-5.2:free",
    "liquid/lfm-2.5-2.6b:free",
    "dots-studio/dots-3-note-preview:free",
]

_OPENROUTER_MODEL_CATEGORIES = {
    "seo": [
        "openrouter/free",
        "poolside/laguna-s-2.1:free",
        "google/gemma-4-26b-a4b-it:free",
        "openai/gpt-oss-20b:free",
    ],
    "general": _OPENROUTER_FREE_MODELS,
}

_session = requests.Session()


def _clean_response_text(text: Optional[str]) -> str:
    """Clean markdown artifacts, thinking blocks, and whitespace."""
    if not text:
        return ""
    # Strip <think>...</think> blocks from reasoning models
    text = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE)
    # If the response starts with reasoning analysis, extract clean output
    lines = text.strip().splitlines()
    cleaned_lines = []
    for line in lines:
        if line.startswith("Here's a thinking process:") or line.startswith("Analysis:"):
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def _get_openrouter_models(category: Optional[str] = None) -> List[str]:
    if category and category in _OPENROUTER_MODEL_CATEGORIES:
        return _OPENROUTER_MODEL_CATEGORIES[category]
    return _OPENROUTER_FREE_MODELS


def _call_groq(prompt: str, max_tokens: int = 400, temperature: float = 0.7) -> str:
    if not _GROQ_KEYS:
        raise RuntimeError("No GROQ_API_KEY configured")

    last_error = None
    for key_idx, key in enumerate(_GROQ_KEYS):
        key_label = "primary" if key_idx == 0 else f"fallback-{key_idx}"
        for model in _GROQ_MODELS:
            try:
                r = _session.post(
                    _GROQ_URL,
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                    },
                    timeout=25,
                )
                if r.status_code == 200:
                    data = r.json()
                    msg = data.get("choices", [{}])[0].get("message", {})
                    content = _clean_response_text(msg.get("content") or msg.get("reasoning"))
                    if content:
                        return content

                if r.status_code == 404:
                    continue  # Model not found on Groq, try next model

                if r.status_code in (401, 403, 429):
                    last_error = f"Groq {key_label} returned HTTP {r.status_code}"
                    break  # Key invalid or rate-limited, switch to fallback key

                last_error = f"HTTP {r.status_code}: {r.text[:120]}"
            except Exception as e:
                last_error = str(e)
                continue

    raise RuntimeError(f"All Groq keys and models failed: {last_error}")


def _call_openrouter(prompt: str, max_tokens: int = 400, temperature: float = 0.7, category: Optional[str] = None) -> str:
    if not _OPENROUTER_KEYS:
        raise RuntimeError("No OPENROUTER_API_KEY configured")

    models = _get_openrouter_models(category)
    store_domain = os.getenv("STORE_DOMAIN", "us.meeeshop.com")
    brand_name = os.getenv("BRAND_NAME", "MeeeShop")
    last_error = None

    for key_idx, key in enumerate(_OPENROUTER_KEYS):
        key_label = "primary" if key_idx == 0 else f"fallback-{key_idx}"
        for model in models:
            try:
                r = _session.post(
                    _OPENROUTER_URL,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": f"https://{store_domain}",
                        "X-Title": brand_name,
                    },
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                    },
                    timeout=30,
                )

                if r.status_code == 200:
                    data = r.json()
                    choices = data.get("choices", [])
                    if choices:
                        msg = choices[0].get("message", {})
                        content = _clean_response_text(msg.get("content") or msg.get("reasoning"))
                        if content:
                            return content

                if r.status_code in (400, 404):
                    continue  # Model slug unavailable, try next model

                if r.status_code in (401, 403):
                    last_error = f"OpenRouter {key_label} returned HTTP {r.status_code}"
                    break  # Key invalid, switch to next key

                if r.status_code == 429:
                    continue  # Specific free model rate-limited upstream, try next free model

                last_error = f"HTTP {r.status_code}: {r.text[:120]}"
            except Exception as e:
                last_error = str(e)
                continue

    raise RuntimeError(f"All OpenRouter keys and models failed: {last_error}")


_PROVIDERS = [
    ("Groq",       _call_groq),
    ("OpenRouter", lambda p, m, t: _call_openrouter(p, m, t, "seo")),
]


def reset_provider_state():
    """Retained for backward compatibility."""
    pass


def generate(prompt: str, max_tokens: int = 400, temperature: float = 0.8) -> Optional[str]:
    """
    Try Groq (Primary -> Fallback Key) then OpenRouter (Primary -> Fallback Key).
    Returns generated text on success, or None on failure for fallback templates.
    """
    for name, fn in _PROVIDERS:
        try:
            text = fn(prompt, max_tokens, temperature)
            if text:
                print(f"  [AI:{name}] OK")
                return text
        except Exception as e:
            print(f"  [AI:{name}] {e} - trying next provider...")
            time.sleep(0.3)

    print("  [AI] all providers failed — using standard fallback")
    return None


def test_providers() -> dict:
    results = {}
    probe = "Reply with the single word: ok"
    for name, fn in _PROVIDERS:
        try:
            r = fn(probe, 10, 0.1)
            results[name] = "OK  " + (r[:40] if r else "(empty)")
        except Exception as e:
            results[name] = f"FAIL {e}"
    return results


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print("Testing AI providers...\n")
    for p, s in test_providers().items():
        safe_s = s.encode("ascii", errors="replace").decode("ascii")
        print(f"  {p:<14}: {safe_s}")
