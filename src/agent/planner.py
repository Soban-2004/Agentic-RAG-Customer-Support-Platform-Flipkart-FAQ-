"""
Planning layer: a lightweight intent classifier that runs before the agent
acts on a message.

This does NOT control which tool the agent calls -- the agent decides that
itself via tool-calling (see src/agent/chat_agent.py). The classification is
used for orchestration decisions that need to happen outside the agent loop:
  - Semantic cache eligibility (only faq_lookup may be cached -- see
    CACHEABLE_INTENTS below for why general_chat was dropped from this set)
  - Observability tagging (which kind of question is this, for logging/traces)
"""

import logging
from enum import Enum

from llama_index.core.llms import LLM
from llama_index.core.prompts import PromptTemplate
from pydantic import BaseModel, Field

logger = logging.getLogger("agent.planner")


class IntentLabel(str, Enum):
    FAQ_LOOKUP = "faq_lookup"
    ORDER_STATUS = "order_status"
    REFUND_STATUS = "refund_status"
    ESCALATE = "escalate"
    GENERAL_CHAT = "general_chat"


# Only these intents may ever be served from / written to the semantic cache.
#
# general_chat used to be included here too, on the assumption that smalltalk
# is stable/generic enough to share globally. That's true for "hi"/"thanks",
# but general_chat also catches session-referential meta-questions ("what
# was my previous question", "what did I just ask you") -- confirmed live
# (traced from a real deployed conversation, then reproduced directly against
# the cache): a "you haven't asked anything yet" answer generated for one
# user's empty-history turn got cached globally under CACHE_VERSION 2, then
# served verbatim to an unrelated later conversation that really had asked a
# prior question. There's no way to distinguish "safe to cache globally" from
# "session-specific, must never be cached" within general_chat by the intent
# label alone, so the whole bucket is excluded rather than trying to
# sub-classify it -- the cost is a few skipped LLM-call savings on repeated
# small talk, which is cheap and infrequent enough not to matter.
CACHEABLE_INTENTS = {IntentLabel.FAQ_LOOKUP}


class Intent(BaseModel):
    label: IntentLabel = Field(description="The single best-matching intent for the message.")


_PLANNER_PROMPT = PromptTemplate(
    "Classify the customer support message into exactly one intent:\n"
    "- faq_lookup: general policy/how-to questions (returns, refunds policy, payments, EMI, shipping, etc)\n"
    "- order_status: asking about the delivery/tracking status of a specific order\n"
    "- refund_status: asking about the status of a specific refund already requested\n"
    "- escalate: explicitly wants a human agent, or is angry/frustrated with an unresolved issue\n"
    "- general_chat: greetings, small talk, or anything unrelated to Flipkart support\n\n"
    "Message: {query}\n"
)


async def classify_intent(llm: LLM, query: str) -> IntentLabel:
    """Classify a message's intent. Defaults to FAQ_LOOKUP (the safest, fully-supported
    path) if classification itself fails, rather than breaking the chat turn."""
    try:
        result = await llm.astructured_predict(Intent, _PLANNER_PROMPT, query=query)
        return result.label
    except Exception:
        logger.exception("planner: intent classification failed, defaulting to faq_lookup")
        return IntentLabel.FAQ_LOOKUP
