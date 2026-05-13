"""
ai_client.py — Free AI provider with intelligent fallback for Pinterest content
Copied from meeeshop-youtube for consistency across projects.
Primary   : Gemini 2.0 Flash  (Google AI Studio — 1M tokens/day, free)
Secondary : Groq Llama-3.3-70B (groq.com — ~500K tokens/day, free)
Tertiary  : OpenRouter free models with auto-fallback
Fallback  : returns None → caller uses hardcoded template
"""

import os, sys, time, requests
from pathlib import Path
from typing import List, Optional


def _load_env():
    for candidate in [Path(__file__).with_name(".env"), Path(".env")]:
        if candidate.exists():
            for line in candidate.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"'))


_load_env()

GEMINI_KEY     = os.getenv("GEMINI_API_KEY", "")
GROQ_KEY       = os.getenv("GROQ_API_KEY", "")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")

_GEMINI_URL      = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
_GROQ_URL        = "https://api.groq.com/openai/v1/chat/completions"
_OPENROUTER_URL  = "https://openrouter.ai/api/v1/chat/completions"

_OPENROUTER_FREE_MODELS = [
    "poolside/laguna-m1:free",
    "inclusionai/ring-2.6-1t:free",
    "openai/gpt-oss-120b:free",
    "qwen/qwen3-coder-480b-a35b:free",
    "nvidia/nemotron-3-nano-30b-a3b:free",
    "openai/gpt-oss-20b:free",
    "poolside/laguna-xs2:free",
    "baidu/qianfan-cobuddy:free",
    "minimax/minimax-m2.5:free",
    "z-ai/glm-4.5-air:free",
    "liquidai/lfm2.5-1.2b-thinking:free",
    "nous/hermes-3-405b-instruct:free",
    "nvidia/nemotron-3-nano-omni:free",
    "nvidia/nemotron-nano-12b-vl-2:free",
    "google/gemma-4-31b:free",
    "google/gemma-4-26b-a4b:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "meta-llama/llama-3.2-3b-instruct:free",
    "baidu/qianfan-ocr-fast:free",
    "venice/uncensored:free",
    "openrouter/free",
]

_OPENROUTER_MODEL_CATEGORIES = {
    "seo": [
        "minimax/minimax-m2.5:free",
        "baidu/qianfan-cobuddy:free",
        "meta-llama/llama-3.3-70b-instruct:free",
    ],
    "general": [
        "poolside/laguna-m1:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "qwen/qwen3-next-80b-a3b-instruct:free",
    ],
}


def _get_openrouter_models(category: Optional[str] = None) -> List[str]:
    if category and category in _OPENROUTER_MODEL_CATEGORIES:
        return _OPENROUTER_MODEL_CATEGORIES[category]
    return _OPENROUTER_FREE_MODELS


def _call_gemini(prompt: str, max_tokens: int, temperature: float) -> str:
    if not GEMINI_KEY:
        raise RuntimeError("GEMINI_API_KEY not set")
    r = requests.post(
        _GEMINI_URL,
        params={"key": GEMINI_KEY},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
        },
        timeout=30,
    )
    if r.status_code == 429:
        raise RuntimeError("rate-limited")
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()


def _call_groq(prompt: str, max_tokens: int, temperature: float) -> str:
    if not GROQ_KEY:
        raise RuntimeError("GROQ_API_KEY not set")
    r = requests.post(
        _GROQ_URL,
        headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        },
        timeout=30,
    )
    if r.status_code == 429:
        raise RuntimeError("rate-limited")
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def _call_openrouter(prompt: str, max_tokens: int, temperature: float, category: Optional[str] = None) -> str:
    if not OPENROUTER_KEY:
        raise RuntimeError("OPENROUTER_API_KEY not set")

    models = _get_openrouter_models(category)
    attempt_logs: List[str] = []

    for model in models:
        try:
            r = requests.post(
                _OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://us.meeeshop.com",
                    "X-Title": "MeeeShop",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
                timeout=45,
            )

            if r.status_code == 429:
                attempt_logs.append(f"{model}: rate-limited (HTTP 429)")
                continue

            if r.status_code >= 400:
                try:
                    err_json = r.json()
                    err_msg = str(err_json.get("error", ""))
                except Exception:
                    err_msg = r.text

                if "context_length_exceeded" in err_msg.lower() or "token" in err_msg.lower():
                    attempt_logs.append(f"{model}: token limit")
                    continue

                attempt_logs.append(f"{model}: error {r.status_code}")
                continue

            attempt_logs.append(f"{model}: OK")
            return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            attempt_logs.append(f"{model}: exception")
            continue

    log_blob = " | ".join(attempt_logs) if attempt_logs else "no attempts"
    raise RuntimeError(f"All OpenRouter models failed: {log_blob}")


_PROVIDERS = [
    ("Gemini",     _call_gemini),
    ("Groq",       _call_groq),
    ("OpenRouter", lambda p, m, t: _call_openrouter(p, m, t, "seo")),
]

_PROVIDER_BLACKLIST: set = set()
_MAX_RETRIES = 2


def reset_provider_state():
    _PROVIDER_BLACKLIST.clear()


def generate(prompt: str, max_tokens: int = 400, temperature: float = 0.8) -> str | None:
    """Try providers in order, skipping ones already known to be failing in this run.
    If every provider fails, retry the full set up to _MAX_RETRIES times before
    returning None (caller then uses standard product fallback)."""
    active = [(n, f) for n, f in _PROVIDERS if n not in _PROVIDER_BLACKLIST]
    if not active:
        active = list(_PROVIDERS)
        _PROVIDER_BLACKLIST.clear()

    for name, fn in active:
        try:
            text = fn(prompt, max_tokens, temperature)
            if text:
                print(f"  [AI:{name}] OK")
                return text
        except Exception as e:
            print(f"  [AI:{name}] {e} - blacklisted for session")
            _PROVIDER_BLACKLIST.add(name)
            time.sleep(0.3)

    for attempt in range(1, _MAX_RETRIES + 1):
        print(f"  [AI] all providers failed — retry {attempt}/{_MAX_RETRIES}")
        time.sleep(1.0 * attempt)
        for name, fn in _PROVIDERS:
            try:
                text = fn(prompt, max_tokens, temperature)
                if text:
                    print(f"  [AI:{name}] OK (recovered)")
                    _PROVIDER_BLACKLIST.discard(name)
                    return text
            except Exception as e:
                print(f"  [AI:{name}] {e}")
                continue

    print("  [AI] all providers failed after retries — using standard fallback")
    return None


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print("Testing AI providers...\n")
    probe = "Reply with: ok"
    for name, fn in _PROVIDERS:
        try:
            r = fn(probe, 10, 0.1)
            safe_s = (r[:40] if r else "(empty)").encode("ascii", errors="replace").decode("ascii")
            print(f"  {name:<14}: OK {safe_s}")
        except Exception as e:
            print(f"  {name:<14}: FAIL {e}")
