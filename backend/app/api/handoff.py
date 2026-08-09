from fastapi import APIRouter
from pydantic import BaseModel
from app.services.handoff_manager import HandoffManager

router = APIRouter()

class ResolveRequest(BaseModel):
    session_id: str

@router.get("/handoff")
def get_handoffs():
    handoffs = HandoffManager.get_all_handoffs()
    return {"handoffs": handoffs, "count": len(handoffs)}

@router.post("/handoff/resolve")
def resolve_handoff(req: ResolveRequest):
    HandoffManager.resolve_handoff(req.session_id)
    return {"status": "success", "session_id": req.session_id}
