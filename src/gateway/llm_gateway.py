"""
AI Gateway: the single chokepoint every LLM call in this app goes through.

Nothing else in the codebase should import a provider SDK (Groq, OpenAI,
Ollama, ...) directly -- build_gateway_llm() returns a LlamaIndex-compatible
LLM backed by LiteLLM, which gives us provider-agnostic routing, automatic
fallback to another model on error/timeout, retries, and centralized
cost/latency logging for every request (see _log_llm_call below).
"""

import logging
import os
from pathlib import Path
from typing import Any, Optional

import litellm
import yaml
from llama_index.llms.litellm import LiteLLM

logger = logging.getLogger("gateway.llm")

_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "models.yaml"

# Some providers (notably ollama_chat) reject request params other providers
# accept (e.g. `parallel_tool_calls`, sent unconditionally by LlamaIndex's
# FunctionAgent) -- drop unsupported params instead of erroring, rather than
# special-casing every provider/param combination ourselves.
litellm.drop_params = True


def _load_config() -> dict:
    with open(_CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def _resolve_api_base(entry: dict) -> Optional[str]:
    """`config/models.yaml`'s literal `api_base` (http://localhost:11434) only
    resolves correctly for local dev -- inside the Docker container, that
    `localhost` means the container itself, not the host machine's Ollama
    daemon. OLLAMA_API_BASE overrides it (set to
    http://host.docker.internal:11434 in a container); unset, the yaml value
    is used unchanged, so local dev needs no extra config."""
    if not entry.get("api_base"):
        return None
    return os.getenv("OLLAMA_API_BASE") or entry["api_base"]


def _resolve_api_key(entry: dict) -> Optional[str]:
    """Returns None for providers that don't need one (e.g. a local Ollama
    daemon, which handles its own auth to Ollama Cloud via `ollama signin`)."""
    key_env = entry.get("api_key_env")
    if not key_env:
        return None
    api_key = os.getenv(key_env)
    if not api_key:
        raise ValueError(
            f"Missing API key env var '{key_env}' required by model '{entry['model']}' "
            f"(config/models.yaml)"
        )
    return api_key


def _register_unknown_ollama_model(model: str) -> None:
    """LiteLLM's static model registry lags behind Ollama Cloud's own model
    releases -- a brand-new model (e.g. gemma4:cloud) reports
    is_function_calling_model=False purely because LiteLLM doesn't recognize
    the name yet, not because the model can't actually do it (verified
    directly against Ollama's API: it returns clean tool_calls). Without this,
    LlamaIndex's FunctionAgent refuses to use the model for tool calls at all
    (`ValueError: LLM must be a FunctionCallingLLM`). Only patches models
    LiteLLM doesn't already know about; a future LiteLLM release that adds
    real support just makes this a no-op.
    """
    if not model.startswith("ollama") or litellm.supports_function_calling(model):
        return
    litellm.register_model({
        model: {
            "input_cost_per_token": 0.0,
            "output_cost_per_token": 0.0,
            "litellm_provider": model.split("/")[0],
            "mode": "chat",
            "max_input_tokens": 131072,
            "max_output_tokens": 131072,
            "max_tokens": 131072,
            "supports_function_calling": True,
        }
    })


def _log_llm_call(kwargs: dict, completion_response: Any, start_time, end_time) -> None:
    """LiteLLM success callback -- fires after every gateway call, regardless of caller."""
    try:
        usage = getattr(completion_response, "usage", None)
        latency = (end_time - start_time).total_seconds()
        logger.info(
            "llm_call model=%s latency=%.2fs prompt_tokens=%s completion_tokens=%s cost=$%.6f",
            kwargs.get("model"),
            latency,
            getattr(usage, "prompt_tokens", "?"),
            getattr(usage, "completion_tokens", "?"),
            kwargs.get("response_cost") or 0.0,
        )
    except Exception:
        logger.exception("gateway: failed to log successful llm call")


def _log_llm_failure(kwargs: dict, completion_response: Any, start_time, end_time) -> None:
    logger.warning("llm_call_failed model=%s error=%s", kwargs.get("model"), completion_response)


litellm.success_callback = [_log_llm_call]
litellm.failure_callback = [_log_llm_failure]


def build_gateway_llm(model_key: Optional[str] = None) -> LiteLLM:
    """
    Build the LLM used by the rest of the app. Reads config/models.yaml for the
    primary model and wires every *other* configured model in as a LiteLLM
    fallback, so a provider outage/timeout on the primary degrades gracefully
    instead of failing the request.
    """
    config = _load_config()
    model_key = model_key or config["default_model"]
    entry = config["models"][model_key]
    _register_unknown_ollama_model(entry["model"])

    fallback_entries = []
    for key, m in config["models"].items():
        if key == model_key:
            continue
        _register_unknown_ollama_model(m["model"])
        fallback_entry = {"model": m["model"], "api_key": _resolve_api_key(m)}
        api_base = _resolve_api_base(m)
        if api_base:
            fallback_entry["api_base"] = api_base
        fallback_entries.append(fallback_entry)

    return LiteLLM(
        model=entry["model"],
        api_key=_resolve_api_key(entry),
        api_base=_resolve_api_base(entry),
        temperature=entry.get("temperature", 0.2),
        max_tokens=entry.get("max_tokens"),
        max_retries=config.get("max_retries", 2),
        additional_kwargs={
            "timeout": config.get("timeout_seconds", 30),
            "fallbacks": fallback_entries,
        },
    )
