"""Mock connectors over seeded synthetic data. Nothing here touches the outside world."""
from pydantic import BaseModel, Field

from ..models import MockOrder, MockTicket
from ..rag import service as rag_service
from .registry import ToolContext, ToolDef, ToolFailure, ToolRegistry, ToolResult

ORDER_ID = r"^ORD-\d{3,8}$"


class SearchArgs(BaseModel):
    query: str = Field(min_length=1, max_length=500)


class OrderArgs(BaseModel):
    order_id: str = Field(pattern=ORDER_ID)


class EmptyArgs(BaseModel):
    pass


class TicketArgs(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=2000)


class RefundArgs(BaseModel):
    order_id: str = Field(pattern=ORDER_ID)
    reason: str = Field(min_length=1, max_length=300)


def _own_order(ctx: ToolContext, order_id: str) -> MockOrder:
    order = ctx.db.get(MockOrder, order_id)
    if order is None or order.user_id != ctx.user_id:  # same answer for "missing" and "not yours"
        raise ToolFailure(f"Order {order_id} not found")
    return order


def search_knowledge_base(ctx: ToolContext, a: SearchArgs) -> ToolResult:
    from ..models import User

    hits = rag_service.retrieve(ctx.db, ctx.db.get(User, ctx.user_id), a.query, top_k=3)
    if not hits:
        return ToolResult("No relevant documents found", {"results": []})
    return ToolResult(f"Found {len(hits)} relevant passages", {"results": [
        {"file": h.filename, "chunk": h.chunk_index, "text": h.content[:300]} for h in hits]})


def lookup_mock_order(ctx: ToolContext, a: OrderArgs) -> ToolResult:
    o = _own_order(ctx, a.order_id)
    state = "refunded" if o.refunded else o.status
    return ToolResult(f"Order {o.id} ({o.item}, ${o.amount_cents / 100:.2f}) is {state}.",
                      {"order_id": o.id, "item": o.item, "status": state,
                       "amount_cents": o.amount_cents})


def get_mock_account_profile(ctx: ToolContext, a: EmptyArgs) -> ToolResult:
    return ToolResult(f"Account {ctx.email} with role {ctx.role}.",
                      {"email": ctx.email, "role": ctx.role, "user_id": ctx.user_id})


def create_mock_support_ticket(ctx: ToolContext, a: TicketArgs) -> ToolResult:
    t = MockTicket(user_id=ctx.user_id, subject=a.subject, body=a.body)
    ctx.db.add(t)
    ctx.db.commit()
    return ToolResult(f"Mock ticket {t.id[:8]} created.", {"ticket_id": t.id, "status": t.status})


def request_mock_refund(ctx: ToolContext, a: RefundArgs) -> ToolResult:
    o = _own_order(ctx, a.order_id)
    if o.refunded:
        raise ToolFailure(f"Order {o.id} was already refunded")
    if o.status != "delivered":
        raise ToolFailure(f"Order {o.id} is {o.status}; only delivered orders can be refunded")
    o.refunded = True
    ctx.db.commit()
    return ToolResult(f"Simulated refund of ${o.amount_cents / 100:.2f} for order {o.id} processed.",
                      {"order_id": o.id, "refunded": True})


def build_registry() -> ToolRegistry:
    return ToolRegistry([
        ToolDef("search_knowledge_base", "Search documents the user may access.", SearchArgs,
                search_knowledge_base, "tool:read"),
        ToolDef("lookup_mock_order", "Look up one of the user's orders by id (e.g. ORD-1001).",
                OrderArgs, lookup_mock_order, "tool:read"),
        ToolDef("get_mock_account_profile", "Get the signed-in user's account profile.", EmptyArgs,
                get_mock_account_profile, "tool:read"),
        ToolDef("create_mock_support_ticket", "Create a (mock) support ticket.", TicketArgs,
                create_mock_support_ticket, "tool:write", risk="medium",
                idempotency_fields=("subject", "body"), redact_fields=("body",)),
        ToolDef("request_mock_refund", "Request a (simulated) refund for a delivered order.",
                RefundArgs, request_mock_refund, "tool:write", risk="high",
                requires_confirmation=True, idempotency_fields=("order_id",)),
    ])
