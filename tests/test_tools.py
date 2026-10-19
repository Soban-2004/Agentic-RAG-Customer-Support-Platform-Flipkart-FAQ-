import pytest

from src.agent.context import ToolContext, tool_context
from src.tools import service


@pytest.mark.asyncio
async def test_tools_require_trusted_context():
    with pytest.raises(PermissionError):
        await service.get_order_status("FK1001")


@pytest.mark.asyncio
async def test_demo_mutations_are_session_local():
    alice = ToolContext("a", "demo-a", "one", demo=True)
    bob = ToolContext("b", "demo-b", "two", demo=True)
    with tool_context(alice):
        await service.add_order_note("FK1001", "private marker")
        assert "private marker" in await service.get_order_status("FK1001")
    with tool_context(bob):
        assert "private marker" not in await service.get_order_status("FK1001")
        bob.turn_id = "next-turn"
        bob.tool_calls.clear()
        message = await service.escalate_to_human("Damaged product", "FK1001")
        assert "No human agent has been notified" in message


@pytest.mark.asyncio
async def test_regeneration_cannot_mutate():
    with tool_context(ToolContext("a", "demo-a", "one", demo=True, read_only=True)):
        with pytest.raises(PermissionError):
            await service.add_order_note("FK1001", "changed")


@pytest.mark.asyncio
async def test_unknown_resources_return_clear_results():
    with tool_context(ToolContext("a", "demo-a", "one", demo=True)):
        assert "No demonstration order found" in await service.get_order_status(
            "UNKNOWN999"
        )
        assert "No demonstration refund found" in await service.get_refund_status(
            "RF9999"
        )
