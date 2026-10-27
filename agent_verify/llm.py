# -*- coding: utf-8 -*-
"""Minimal LLM client, standard library only. Supports OpenAI and Google Gemini.

Keys come from the environment, never from the repository:
    OPENAI_API_KEY   for provider "openai"
    GEMINI_API_KEY   for provider "gemini"
Optional:
    LLM_MIN_INTERVAL seconds to wait between calls (use ~6.5 on the Gemini free tier)
"""
import json
import os
import time
import urllib.error
import urllib.request

_last_call = [0.0]


class LLMError(RuntimeError):
    pass


def _post(url, headers, body, timeout=90, tries=6):
    data = json.dumps(body).encode()
    for attempt in range(tries):
        gap = float(os.environ.get("LLM_MIN_INTERVAL", "0"))
        wait = _last_call[0] + gap - time.time()
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.time()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **headers})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:300]
            if e.code in (429, 500, 502, 503, 504) and attempt < tries - 1:
                time.sleep(min(60, 2 ** attempt * 2))
                continue
            raise LLMError(f"HTTP {e.code}: {msg}") from None
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < tries - 1:
                time.sleep(2 ** attempt)
                continue
            raise LLMError(f"network: {e}") from None
    raise LLMError("retries exhausted")


def _key(name):
    k = os.environ.get(name)
    if not k:
        raise LLMError(f"{name} is not set. Locally: export {name}=...; in CI: add it as a repository secret.")
    return k


def complete(provider, model, system, user, temperature, max_tokens):
    """Return (text, usage) where usage = {"input": n, "output": n}."""
    if provider == "openai":
        r = _post("https://api.openai.com/v1/chat/completions",
                  {"Authorization": f"Bearer {_key('OPENAI_API_KEY')}"},
                  {"model": model, "temperature": temperature, "max_tokens": max_tokens,
                   "response_format": {"type": "json_object"},
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
        u = r.get("usage", {})
        return r["choices"][0]["message"]["content"], {"input": u.get("prompt_tokens"), "output": u.get("completion_tokens")}
    if provider == "gemini":
        r = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                  {"x-goog-api-key": _key("GEMINI_API_KEY")},
                  {"systemInstruction": {"parts": [{"text": system}]},
                   "contents": [{"role": "user", "parts": [{"text": user}]}],
                   "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens,
                                        "responseMimeType": "application/json"}})
        try:
            text = "".join(p.get("text", "") for p in r["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError):
            raise LLMError(f"gemini returned no text: {json.dumps(r)[:300]}") from None
        u = r.get("usageMetadata", {})
        return text, {"input": u.get("promptTokenCount"), "output": u.get("candidatesTokenCount")}
    raise LLMError(f"unknown provider {provider!r}")
