"""
MCP Tools server: a real Model Context Protocol server (stdio transport)
exposing Flipkart account-specific actions -- order status, refund status,
human escalation, and order notes (long-term memory) -- backed by the mock
SQLite database in mock_backend.py.

Launched as a subprocess by the agent (src/agent/chat_agent.py via
llama-index-tools-mcp's BasicMCPClient), not run standalone in normal use.
You can run it directly for manual testing:
    python src/tools/mcp_server.py
and speak stdio MCP to it, or use `mcp dev src/tools/mcp_server.py` (from the
official MCP SDK) for an interactive inspector.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from mcp.server.fastmcp import FastMCP

from src.tools.mock_backend import (
    add_note,
    create_escalation,
    get_notes,
    get_order,
    get_refund,
    init_db,
)

mcp = FastMCP("flipkart-support-tools")


@mcp.tool()
def get_order_status(order_id: str) -> str:
    """Look up the delivery/tracking status of a specific Flipkart order by its order ID."""
    order = get_order(order_id)
    if not order:
        return f"No order found with ID '{order_id}'. Please double-check the order ID."
    result = (
        f"Order {order['order_id']} ({order['item_name']}): status = {order['status']}, "
        f"expected delivery = {order['eta']}."
    )
    notes = get_notes(order_id)
    if notes:
        result += " Notes from previous conversations about this order: " + " | ".join(notes)
    return result


@mcp.tool()
def get_refund_status(refund_id: str) -> str:
    """Look up the status of a specific refund by its refund ID."""
    refund = get_refund(refund_id)
    if not refund:
        return f"No refund found with ID '{refund_id}'. Please double-check the refund ID."
    return (
        f"Refund {refund['refund_id']} for order {refund['order_id']}: "
        f"status = {refund['status']}, amount = Rs.{refund['amount']:.2f}."
    )


@mcp.tool()
def add_order_note(order_id: str, note: str) -> str:
    """
    Save a short note against a specific order for future conversations to see
    (e.g. a recurring complaint, a special request, a preference the customer
    mentioned). Surfaced automatically the next time get_order_status is called
    for the same order -- this is how the assistant remembers context about an
    order across separate conversations.
    """
    add_note(order_id=order_id, note=note)
    return f"Noted for order {order_id.strip().upper()}: {note}"


@mcp.tool()
def escalate_to_human(summary: str, order_id: str = "") -> str:
    """
    Create a support escalation ticket for a human agent to follow up on.
    `summary` should briefly describe the customer's issue. `order_id` is
    optional -- include it if the escalation relates to a specific order.
    """
    ticket = create_escalation(summary=summary, order_id=order_id or None)
    return (
        f"Escalation ticket {ticket['ticket_id']} created -- a human support agent "
        f"will follow up on this shortly."
    )


if __name__ == "__main__":
    init_db()
    mcp.run(transport="stdio")
