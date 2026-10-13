import datetime
import json
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.auth import require_role
from app.core.db import get_conn
from app.providers.order_provider import DatabaseOrderProvider, get_order_provider
from app.models.schemas import OrderResponse

router = APIRouter()
order_provider = get_order_provider()


class OrderUpsertRequest(BaseModel):
    status: str
    customer_name: str = ""
    items: List[str] = Field(default_factory=list)
    estimated_delivery: str = ""
    tracking_url: str = ""
    order_value: float = 0
    created_at: Optional[str] = None

@router.get("/orders/{order_id}", response_model=OrderResponse)
def get_order(order_id: str):
    res = order_provider.get_order_status(order_id)
    return OrderResponse(**res)


@router.put("/admin/orders/{order_id}")
def upsert_order(
    order_id: str,
    req: OrderUpsertRequest,
    user: dict = Depends(require_role("admin")),
):
    """Create or update fulfilment state consumed by chat and analytics."""
    normalized_id = DatabaseOrderProvider._extract_order_id(order_id)
    now = datetime.datetime.now().isoformat()
    created_at = req.created_at or now
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO orders (
            order_id, status, customer_name, items, estimated_delivery,
            tracking_url, order_value, created_at, updated_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (order_id) DO UPDATE SET
            status = EXCLUDED.status,
            customer_name = EXCLUDED.customer_name,
            items = EXCLUDED.items,
            estimated_delivery = EXCLUDED.estimated_delivery,
            tracking_url = EXCLUDED.tracking_url,
            order_value = EXCLUDED.order_value,
            updated_at = EXCLUDED.updated_at
    """, (
        normalized_id,
        req.status,
        req.customer_name,
        json.dumps(req.items),
        req.estimated_delivery,
        req.tracking_url,
        req.order_value,
        created_at,
        now,
    ))
    cursor.execute("""
        INSERT INTO audit_log (
            action_type, entity_id, entity_name, new_value,
            performed_by, performed_at
        ) VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        "order_upsert",
        normalized_id,
        normalized_id,
        json.dumps({"status": req.status, "order_value": req.order_value}),
        user["username"],
        now,
    ))
    conn.commit()
    cursor.close()
    conn.close()
    return {"status": "saved", "order_id": normalized_id, "updated_at": now}
