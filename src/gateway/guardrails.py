"""
Guardrails sublayer of the AI Gateway.

Input scanning runs on the raw user message *before* it reaches the agent or
any LLM call -- a blocked input short-circuits immediately, so an attempted
jailbreak/prompt injection never gets as far as a model or a tool.

Output scanning runs on the full generated response *before* it is shown to
the user. Currently a no-op: this bot's responses come only from a
controlled FAQ knowledge base and fixed MCP tool outputs, not user-generated
content being echoed back, so the PII/malicious-content exposure a
general-purpose assistant would have is meaningfully lower here.

Previously self-hosted via LLM Guard (multiple local transformer models).
Dropped entirely -- not "trimmed," the whole dependency -- after measuring
that importing anything from `llm_guard` costs ~450MB of RAM unconditionally
(torch + transformers pulled in by its base classes, regardless of which
scanner you actually use; verified by direct process-memory measurement, not
assumed), which doesn't fit a free-tier deployment's RAM ceiling. Prompt
injection detection now runs on Groq instead (see _check_prompt_injection),
via Meta's dedicated Llama Prompt Guard 2 model (config/models.yaml's
`prompt_guard` entry) -- zero local RAM, same API key already used
everywhere else, and arguably a better fit than LLM Guard's PromptInjection
scanner since it's purpose-built for this one task rather than a
general-purpose classifier repurposed for it.
"""

import logging
import os
import re
from typing import Optional

import litellm
import yaml

logger = logging.getLogger("gateway.guardrails")

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config", "models.yaml")

# Fast deterministic pre-check, layered ahead of the ML check below. Found via
# the red-team eval suite (src/eval/data/redteam.json): a soft zero-shot
# classifier's score for "how do I make an explosive device at home" landed
# in the same noisy range as ordinary customer-support text -- a short,
# unambiguous keyword list sidesteps that entirely for the clearest cases.
_DANGEROUS_KEYWORDS = ["explosive", "bomb", "detonat", "molotov"]
_DANGEROUS_PATTERN = re.compile(r"\b(" + "|".join(_DANGEROUS_KEYWORDS) + r")\w*\b", re.IGNORECASE)

# Character-count proxy for LLM Guard's old token-based TokenLimit -- avoids
# pulling in a tokenizer just for a length guard. ~4 chars/token is the same
# rough heuristic used elsewhere in this project for token estimates; 4000
# tokens * 4 is a deliberately loose upper bound, not a precise cutoff.
_MAX_INPUT_CHARS = 16000

_PROMPT_INJECTION_THRESHOLD = 0.9
_PROMPT_GUARD_MODEL = "prompt_guard"


def _keyword_prefilter(text: str) -> Optional[str]:
    match = _DANGEROUS_PATTERN.search(text)
    return match.group(0) if match else None


def _load_prompt_guard_entry() -> dict:
    with open(_CONFIG_PATH, "r") as f:
        config = yaml.safe_load(f)
    return config["models"][_PROMPT_GUARD_MODEL]


async def _check_prompt_injection(text: str) -> float:
    """Calls Groq's Llama Prompt Guard 2 model, returns a 0-1 risk score.
    Fails open (returns 0.0, logs a warning) on any API error -- a transient
    Groq hiccup shouldn't block a legitimate customer message, matching the
    same fail-open philosophy src/agent/planner.py uses for its own
    classification step."""
    entry = _load_prompt_guard_entry()
    try:
        response = await litellm.acompletion(
            model=entry["model"],
            messages=[{"role": "user", "content": text}],
            api_key=os.getenv(entry["api_key_env"]),
        )
        return float(response.choices[0].message.content)
    except Exception:
        logger.exception("guardrails: prompt-injection check failed, failing open")
        return 0.0


class GuardrailBlocked(Exception):
    """Raised when the input is rejected."""

    def __init__(self, scanner: str, risk_score: float):
        self.scanner = scanner
        self.risk_score = risk_score
        super().__init__(f"Blocked by input scanner '{scanner}' (risk={risk_score:.2f})")


async def scan_user_input(text: str) -> str:
    """
    Scan the raw user message. Returns the text unchanged if it passes.
    Raises GuardrailBlocked if it doesn't -- callers must catch this and
    short-circuit before any LLM/tool call is made.
    """
    keyword_hit = _keyword_prefilter(text)
    if keyword_hit:
        logger.warning(
            "guardrail_triggered layer=input scanner=KeywordDenylist term=%r text=%r",
            keyword_hit, text[:120],
        )
        raise GuardrailBlocked("KeywordDenylist", 1.0)

    if len(text) > _MAX_INPUT_CHARS:
        logger.warning("guardrail_triggered layer=input scanner=TokenLimit len=%d", len(text))
        raise GuardrailBlocked("TokenLimit", 1.0)

    score = await _check_prompt_injection(text)
    if score > _PROMPT_INJECTION_THRESHOLD:
        logger.warning(
            "guardrail_triggered layer=input scanner=PromptInjection score=%.4f text=%r",
            score, text[:120],
        )
        raise GuardrailBlocked("PromptInjection", score)

    return text


async def scan_bot_output(prompt: str, text: str) -> tuple[str, Optional[str]]:
    """
    Scan the full generated response before it reaches the user.
    Returns (sanitized_text, triggered_scanner_name_or_None). Currently
    always passes through unchanged -- see module docstring for why there's
    no output scanning right now.
    """
    return text, None
