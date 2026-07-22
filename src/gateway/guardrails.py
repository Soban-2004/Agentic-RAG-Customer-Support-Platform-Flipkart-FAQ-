"""
Guardrails sublayer of the AI Gateway.

Input scanners run on the raw user message *before* it reaches the agent or
any LLM call -- a blocked input short-circuits immediately, so an attempted
jailbreak/prompt injection never gets as far as a model or a tool.

Output scanners run on the full generated response *before* it is shown to
the user -- PII is redacted (never just flagged) since a chatbot leaking a
phone number is worse than a chatbot refusing to answer.

Uses LLM Guard (self-hosted, no external API), running its transformer-backed
scanners (PromptInjection, Toxicity, BanTopics, NoRefusal, MaliciousURLs) on
the default torch backend. An ONNX backend is also available in LLM Guard via
`use_onnx=True`, but it additionally requires the `optimum[onnxruntime]`
package on top of raw onnxruntime -- not worth the extra dependency here
since torch is already pulled in transitively.
"""

import asyncio
import logging
import re
from typing import Optional

import anyio
from llm_guard.input_scanners import BanTopics, PromptInjection, TokenLimit, Toxicity
from llm_guard.output_scanners import MaliciousURLs, NoRefusal, Sensitive

logger = logging.getLogger("gateway.guardrails")

# Scope the bot to Flipkart customer support; anything routed here is refused.
BANNED_TOPICS = ["politics", "religion", "violence", "self-harm", "illegal activity"]

# Fast deterministic pre-check, layered ahead of the ML scanners below. Found
# via the red-team eval suite (src/eval/data/redteam.json): BanTopics is a
# soft zero-shot classifier, and its score for "how do I make an explosive
# device at home" (~0.4-0.5 on 'illegal activity') landed in the same range as
# ordinary customer-support text's baseline score for that label (~0.3-0.4) --
# run-to-run noisy enough that lowering the threshold to catch one risks
# false-blocking real customers on the other. A short, unambiguous keyword
# list sidesteps that: customers asking about orders/refunds/payments don't
# say "bomb" or "explosive", so this adds a hard catch for the clearest cases
# without touching BanTopics' threshold at all.
_DANGEROUS_KEYWORDS = ["explosive", "bomb", "detonat", "molotov"]
_DANGEROUS_PATTERN = re.compile(r"\b(" + "|".join(_DANGEROUS_KEYWORDS) + r")\w*\b", re.IGNORECASE)


def _keyword_prefilter(text: str) -> Optional[str]:
    match = _DANGEROUS_PATTERN.search(text)
    return match.group(0) if match else None


_input_scanners = None
_output_scanners = None


def _get_input_scanners() -> list:
    global _input_scanners
    if _input_scanners is None:
        logger.info("guardrails: loading input scanners (first call, downloads models if needed)")
        _input_scanners = [
            PromptInjection(),  # covers both prompt injection and jailbreak attempts
            Toxicity(),
            BanTopics(BANNED_TOPICS),
            TokenLimit(limit=4000),
        ]
    return _input_scanners


def _get_output_scanners() -> list:
    global _output_scanners
    if _output_scanners is None:
        logger.info("guardrails: loading output scanners (first call, downloads models if needed)")
        _output_scanners = [
            Sensitive(redact=True),  # PII detection + redaction via Presidio under the hood
            NoRefusal(),
            MaliciousURLs(),
        ]
    return _output_scanners


async def _scan_prompt_parallel(scanners: list, prompt: str) -> tuple[str, dict, dict]:
    """Runs the 4 input scanners concurrently instead of llm_guard's own
    sequential `scan_prompt()` -- by far the single biggest latency
    contributor in the request path (~1.5-4.5s observed, 4 transformer
    models run one after another on CPU). Safe because all 4
    (PromptInjection/Toxicity/BanTopics/TokenLimit) are pure detectors with
    no cross-scanner data dependency: none of them mutate the prompt except
    TokenLimit, and only when it's already invalidating (at which point
    GuardrailBlocked fires regardless of scan order) -- verified by reading
    each scanner's actual `.scan()` source, not assumed. Cuts wall-clock from
    the sum of all 4 scanners to roughly the slowest single one.
    """
    if not scanners or not prompt.strip():
        return prompt, {}, {}
    results = await asyncio.gather(
        *(anyio.to_thread.run_sync(scanner.scan, prompt) for scanner in scanners)
    )
    sanitized_prompt = prompt
    results_valid, results_score = {}, {}
    for scanner, (out_prompt, is_valid, risk_score) in zip(scanners, results):
        name = type(scanner).__name__
        results_valid[name] = is_valid
        results_score[name] = risk_score
        if not is_valid:
            sanitized_prompt = out_prompt
    return sanitized_prompt, results_valid, results_score


async def _scan_output_parallel(scanners: list, prompt: str, text: str) -> tuple[str, dict, dict]:
    """`Sensitive` (PII redaction) must run first and its redacted text is
    what `NoRefusal`/`MaliciousURLs` should see -- unlike the input scanners,
    these aren't fully independent, so only the last two (already fast, no
    cross-dependency between *them*) run concurrently with each other."""
    if not scanners or not text.strip():
        return text, {}, {}
    sensitive, rest = scanners[0], scanners[1:]

    sanitized_text, is_valid, risk_score = await anyio.to_thread.run_sync(
        sensitive.scan, prompt, text
    )
    results_valid = {type(sensitive).__name__: is_valid}
    results_score = {type(sensitive).__name__: risk_score}

    if rest:
        rest_results = await asyncio.gather(
            *(anyio.to_thread.run_sync(s.scan, prompt, sanitized_text) for s in rest)
        )
        for scanner, (_, is_valid, risk_score) in zip(rest, rest_results):
            name = type(scanner).__name__
            results_valid[name] = is_valid
            results_score[name] = risk_score

    return sanitized_text, results_valid, results_score


class GuardrailBlocked(Exception):
    """Raised when an input scanner rejects the user's message."""

    def __init__(self, scanner: str, risk_score: float):
        self.scanner = scanner
        self.risk_score = risk_score
        super().__init__(f"Blocked by input scanner '{scanner}' (risk={risk_score:.2f})")


async def scan_user_input(text: str) -> str:
    """
    Scan the raw user message. Returns the sanitized text if all scanners pass.
    Raises GuardrailBlocked on the first failing scanner -- callers must catch
    this and short-circuit before any LLM/tool call is made.
    """
    keyword_hit = _keyword_prefilter(text)
    if keyword_hit:
        logger.warning(
            "guardrail_triggered layer=input scanner=KeywordDenylist term=%r text=%r",
            keyword_hit, text[:120],
        )
        raise GuardrailBlocked("KeywordDenylist", 1.0)

    # LLM Guard's scanners are synchronous (torch backend) -- off the event
    # loop so one user's scan can't stall every other concurrently-connected
    # user's streamed chat response. Run concurrently, not sequentially --
    # see _scan_prompt_parallel.
    sanitized, results_valid, results_score = await _scan_prompt_parallel(
        _get_input_scanners(), text
    )
    for scanner_name, is_valid in results_valid.items():
        if not is_valid:
            score = results_score.get(scanner_name, 0.0)
            logger.warning(
                "guardrail_triggered layer=input scanner=%s score=%.2f text=%r",
                scanner_name, score, text[:120],
            )
            raise GuardrailBlocked(scanner_name, score)
    return sanitized


async def scan_bot_output(prompt: str, text: str) -> tuple[str, Optional[str]]:
    """
    Scan the full generated response before it reaches the user.
    Returns (sanitized_text, triggered_scanner_name_or_None). PII is redacted
    in-place rather than the response being discarded; a NoRefusal/MaliciousURLs
    trigger is logged but the (still-flagged) text is returned as-is since there
    is nothing safe to substitute mid-conversation.
    """
    sanitized, results_valid, results_score = await _scan_output_parallel(
        _get_output_scanners(), prompt, text
    )
    triggered = None
    for scanner_name, is_valid in results_valid.items():
        if not is_valid:
            triggered = scanner_name
            logger.warning(
                "guardrail_triggered layer=output scanner=%s score=%.2f",
                scanner_name, results_score.get(scanner_name, 0.0),
            )
    return sanitized, triggered
