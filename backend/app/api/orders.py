from fastapi import APIRouter
from app.providers.order_provider import get_order_provider
from app.models.schemas import OrderResponse

router = APIRouter()
order_provider = get_order_provider()

@router.get("/orders/{order_id}", response_model=OrderResponse)
def get_order(order_id: str):
    res = order_provider.get_order_status(order_id)
    return OrderResponse(**res)
