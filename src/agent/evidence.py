"""Grounded public answers and conservative shared-cache eligibility."""

import os
import re
from pathlib import PurePath


# Deliberately closed vocabulary: arbitrary names, secrets, and contextual
# qualifiers must never become input to a globally cached synthesis.
_PUBLIC_TOPICS = {
    "return policy": "returns",
    "what is flipkart's return policy": "returns",
    "how do returns work on flipkart": "returns",
    "refund policy": "refunds",
    "what is flipkart's refund policy": "refunds",
    "what payment methods does flipkart accept": "payments",
    "how does flipkart shipping work": "shipping",
    "what are flipkart's delivery charges": "delivery_charges",
    "what is flipkart's cancellation policy": "cancellation",
    "what are flipkart's emi options": "emi",
}


def public_faq_topic(query):
    normalized = " ".join(
        query.casefold().replace("\u2019", "'").strip().rstrip("?.!").split()
    )
    return _PUBLIC_TOPICS.get(normalized)


def public_faq_query(query):
    return public_faq_topic(query) is not None


def source_metadata(response):
    result = []
    minimum = float(os.getenv("FAQ_MIN_RELEVANCE_SCORE", "0"))
    for item in getattr(response, "source_nodes", []):
        if item.score is None or item.score < minimum:
            continue
        meta = item.node.metadata
        title = PurePath(
            str(meta.get("file_name") or "Policy document").replace("\\", "/")
        ).name[:120]
        result.append(
            {
                "title": title,
                "page": str(meta.get("page_label", ""))[:20],
                "source_id": str(meta.get("source_id", item.node.node_id))[:128],
            }
        )
    return list({(r["source_id"], r["page"]): r for r in result}.values())[:5]


def grounded_text(response):
    sources = source_metadata(response)
    if not sources:
        return (
            "I couldn't find enough supporting policy information. Please provide the product category or check Flipkart's official help center.",
            [],
        )
    text = str(response)
    refs = "\n".join(
        f"- {s['title']}" + (f", page {s['page']}" if s["page"] else "")
        for s in sources
    )
    return text + "\n\n**Sources**\n" + refs, sources
