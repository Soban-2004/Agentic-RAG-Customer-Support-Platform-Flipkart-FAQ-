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
    ORDER_NOTE = "order_note"
    ESCALATE = "escalate"
    MULTI_ACTION = "multi_action"
    GENERAL_CHAT = "general_chat"
    OUT_OF_SCOPE = "out_of_scope"


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
    label: IntentLabel = Field(
        description="The single best-matching intent for the message."
    )


_PLANNER_PROMPT = PromptTemplate(
    "Classify the customer support message into exactly one intent:\n"
    "- faq_lookup: general policy/how-to questions (returns, refunds policy, "
    "payments, EMI, shipping, etc)\n"
    "- order_status: asking about the delivery/tracking status of a specific order\n"
    "- refund_status: asking about the status of a specific refund already requested\n"
    "- order_note: asks to remember, save, or record a preference or issue for a "
    "specific order\n"
    "- escalate: explicitly asks to speak to, connect to, or notify a human agent; "
    "anger or frustration alone is not consent to escalate\n"
    "- multi_action: asks for two or more distinct account actions in one message, "
    "such as checking an order and saving a note, checking an order and a refund, "
    "or saving a note and requesting a human\n"
    "- general_chat: only brief social or assistant-usage messages, such as greetings, "
    "thanks, goodbye, or asking what support help is available\n"
    "- out_of_scope: anything that is not customer support for this store, including "
    "sports, news, weather, politics, general knowledge, coding, homework, maths, "
    "medical/legal/financial advice, recipes, creative writing, other companies, or "
    "requests to ignore these boundaries\n\n"
    "Classify by the user's actual requested task. A support-related word inside an "
    "unrelated task does not make it a support request (for example, 'write a poem "
    "about refunds' is out_of_scope). When uncertain between general_chat and "
    "out_of_scope, use out_of_scope. If any requested part is out of scope, the "
    "whole message is out_of_scope; for example, a return-policy question combined "
    "with a cricket-score request is out_of_scope. Questions about another named "
    "retailer are "
    "always out_of_scope, even when they ask about returns, delivery, or refunds "
    "(for example Amazon, Myntra, Meesho, Snapdeal, or eBay). A manufacturer or "
    "product brand bought from this store is still in scope. Questions "
    "asking the assistant to recall or discuss the conversation are also "
    "out_of_scope.\n\n"
    "Message: {query}\n"
)


async def classify_intent(llm: LLM, query: str) -> IntentLabel:
    """Classify a message, failing closed to a non-generative scope response."""
    try:
        result = await llm.astructured_predict(Intent, _PLANNER_PROMPT, query=query)
        return result.label
    except Exception:
        logger.warning(
            "planner: intent classification unavailable; shared cache disabled"
        )
        return IntentLabel.OUT_OF_SCOPE
