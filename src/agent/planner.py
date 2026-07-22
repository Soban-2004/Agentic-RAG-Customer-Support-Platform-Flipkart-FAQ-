"""
Planning layer: a lightweight intent classifier that runs before the agent
acts on a message.

This does NOT control which tool the agent calls -- the agent decides that
itself via tool-calling (see src/agent/chat_agent.py). The classification is
used for orchestration decisions that need to happen outside the agent loop:
  - Semantic cache eligibility (only faq_lookup/general_chat may be cached --
    order/refund/escalation answers are per-user and dynamic, see src/gateway/cache.py)
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
CACHEABLE_INTENTS = {IntentLabel.FAQ_LOOKUP, IntentLabel.GENERAL_CHAT}


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
