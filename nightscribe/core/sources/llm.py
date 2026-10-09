############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - LLM source: OpenAI-compatible chat endpoint
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The one door to a language model (ADR-075).

The endpoint is the OpenAI chat-completions shape on purpose: OpenRouter,
Groq, Google AI Studio and friends speak it, and so does a LOCAL server
(Ollama, LM Studio, llama.cpp). One integration covers the free cloud and
the private machine, and the user picks which by writing a base URL.

The API key never reaches the log: this module reads it from the config,
puts it in the Authorization header and nowhere else. That is why a failed
call reports the URL and the status, never the headers.

Nothing here decides what to ask: the caller builds the messages (the
prompt with the brief). This module only carries them there and brings the
answer back.
"""

import json
import logging

import requests

logger = logging.getLogger(__name__)

# A local model on a slow machine can think for a while before the first
# token; a free cloud model under load too. Two minutes is generous without
# hanging the GUI forever (the call runs in a worker anyway).
DEFAULT_TIMEOUT_S = 120.0


class LlmError(Exception):
    # Raised for anything that stops an answer from coming back: no
    # endpoint configured, a network failure, an HTTP error or a reply
    # shaped in a way we do not understand. The message is safe to show:
    # it never carries the API key.
    pass


def _models_url(base_url):
    # @args: base_url - the configured base
    # @return: the full "list models" URL (the OpenAI-compatible endpoint)
    base = (base_url or "").strip().rstrip("/")
    if base.endswith("/models"):
        return base
    return f"{base}/models"


def _chat_url(base_url):
    # @args: base_url - the configured base, e.g. "https://.../api/v1" or
    #        "http://localhost:11434/v1"
    # @return: the full chat-completions URL. The base is expected to carry
    #          its version path (the Settings presets fill it in); a base
    #          that already names the endpoint is respected as-is.
    base = (base_url or "").strip().rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def is_configured(cfg):
    # @args: cfg - Config
    # @return: True when there is a base URL AND a model to talk to. A key
    #          is NOT required: a local server needs none.
    base = (cfg.get("ai_base_url") or "").strip()
    model = (cfg.get("ai_model") or "").strip()
    return bool(base and model)


# Hosts that are this machine. A bare name with no dot ("ollama", "mybox")
# and a ".local" name are the machine's own too; anything with a public name
# is not. Kept here (not in the GUI) so one function decides, and it never
# touches the network.
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def is_local(base_url):
    # @args: base_url - the configured base (may carry a path and a port)
    # @return: True when the endpoint runs on this machine, so a report
    #          written through it never leaves it
    host = (base_url or "").strip()
    if not host:
        return False
    from urllib.parse import urlparse
    if "://" not in host:
        host = "http://" + host
    h = (urlparse(host).hostname or "").lower()
    if not h:
        return False
    if h in _LOCAL_HOSTS or h.endswith(".local"):
        return True
    # a private address (192.168.x, 10.x, 172.16-31.x) is the LAN, not the
    # internet: nothing leaves the house either, and it costs nothing
    try:
        import ipaddress
        ip = ipaddress.ip_address(h)
        return ip.is_loopback or ip.is_private or ip.is_unspecified
    except ValueError:
        pass
    # a bare hostname with no dot is a machine/LAN name, not a public one
    return "." not in h and ":" not in h


def is_enabled(cfg):
    # The master switch (ADR-075): the AI may be used only when the observer
    # has turned it ON and there is an endpoint to talk to. `is_configured`
    # alone only says "an endpoint exists"; this is what the interface must
    # ask before offering any AI surface. Settings' "test connection" keeps
    # using `is_configured`, so the endpoint can be set up while the AI is
    # still off.
    # @args: cfg - Config
    # @return: True when the AI may be used
    return bool(cfg.get("ai_enabled")) and is_configured(cfg)


def chat(cfg, messages, temperature=None, max_tokens=None,
         timeout=DEFAULT_TIMEOUT_S):
    # Sends a chat-completions request and returns the assistant's text.
    # @args: cfg - Config, messages - the OpenAI message list
    #        [{"role": "system"|"user"|"assistant", "content": str}],
    #        temperature - override the configured one,
    #        max_tokens - cap the answer, or None,
    #        timeout - seconds to wait
    # @return: the assistant's reply as a string; raises LlmError otherwise
    if not is_configured(cfg):
        raise LlmError("The AI endpoint is not configured")
    base = (cfg.get("ai_base_url") or "").strip()
    model = (cfg.get("ai_model") or "").strip()
    payload = {
        "model": model,
        "messages": messages,
        "temperature": (cfg.get("ai_temperature", 0.7)
                        if temperature is None else temperature),
    }
    if max_tokens:
        payload["max_tokens"] = int(max_tokens)
    headers = {"Content-Type": "application/json"}
    key = (cfg.get("ai_api_key") or "").strip()
    if key:
        # the ONLY place the key is used; it is never logged, never echoed
        headers["Authorization"] = f"Bearer {key}"

    url = _chat_url(base)
    try:
        r = requests.post(url, headers=headers,
                          data=json.dumps(payload), timeout=timeout)
    except requests.RequestException as err:
        raise LlmError(f"Could not reach the AI endpoint: {err}") from err
    if r.status_code >= 400:
        # the body usually says what went wrong (bad model, bad key, quota):
        # keep a short slice, it is the user's own endpoint and never
        # carries our Authorization header
        snippet = (r.text or "").strip()[:300]
        raise LlmError(f"The AI endpoint answered {r.status_code}: {snippet}")
    try:
        data = r.json()
        return data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as err:
        raise LlmError(
            "The AI endpoint's answer was not a chat completion") from err


def _model_ids(data):
    # Reads the ids out of whatever the endpoint returned. The OpenAI shape
    # is {"data": [{"id": ...}]}; Ollama's native list uses {"models":
    # [{"name": ...}]}. Accept both, plus a bare list, and ignore the rest.
    # @args: data - the parsed JSON
    # @return: the sorted, de-duplicated list of model ids
    if isinstance(data, dict):
        rows = data.get("data")
        if not isinstance(rows, list):
            rows = data.get("models")
    else:
        rows = data if isinstance(data, list) else []
    out = []
    for row in rows or []:
        if isinstance(row, dict):
            mid = row.get("id") or row.get("name") or row.get("model")
            if mid:
                out.append(str(mid))
        elif isinstance(row, str):
            out.append(row)
    return sorted(set(out))


def list_models(cfg, timeout=30.0):
    # Asks the endpoint which models it has (the "list models" call). It is
    # what makes a LOCAL server painless: Ollama and LM Studio answer with
    # their exact names, so nobody has to type "qwen2.5:7b" from memory.
    # @args: cfg - Config, timeout - seconds to wait
    # @return: a sorted list of model ids; raises LlmError on any failure.
    #          Only the base URL is needed, so it works before a model is
    #          chosen.
    base = (cfg.get("ai_base_url") or "").strip()
    if not base:
        raise LlmError("The AI endpoint is not configured")
    headers = {"Content-Type": "application/json"}
    key = (cfg.get("ai_api_key") or "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    url = _models_url(base)
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
    except requests.RequestException as err:
        raise LlmError(f"Could not reach the AI endpoint: {err}") from err
    if r.status_code >= 400:
        snippet = (r.text or "").strip()[:300]
        raise LlmError(f"The AI endpoint answered {r.status_code}: {snippet}")
    try:
        data = r.json()
    except ValueError as err:
        raise LlmError("The AI endpoint's answer was not JSON") from err
    ids = _model_ids(data)
    if not ids:
        raise LlmError("The endpoint listed no models")
    return ids


def test_connection(cfg):
    # A one-shot check for the Settings button: asks for a very short
    # answer so the user learns whether the endpoint, the key and the model
    # agree. It is the only call that runs on a click, never in the
    # background.
    # @args: cfg - Config
    # @return: (ok, message): ok is a bool, message is ready to show
    if not is_configured(cfg):
        return False, "Fill in the endpoint and the model first"
    try:
        reply = chat(cfg, [{"role": "user", "content": "Reply with: ok"}],
                     temperature=0.0, max_tokens=8, timeout=30.0)
    except LlmError as err:
        return False, str(err)
    text = (reply or "").strip().replace("\n", " ")[:60]
    if text:
        return True, f"Connected: {text}"
    # a reasoning model can spend a tiny token budget "thinking" and answer
    # with no visible text: the connection still works, so say that plainly
    return True, "Connected, but it returned no text (a reasoning model?)"
