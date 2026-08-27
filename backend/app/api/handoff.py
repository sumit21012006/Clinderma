from fastapi import APIRouter
from pydantic import BaseModel
from app.services.handoff_manager import handoff_manager

router = APIRouter()

class ResolveRequest(BaseModel):
    session_id: str

@router.get("/handoff")
def get_handoffs():
    handoffs = handoff_manager.get_all_handoffs()
    return {"handoffs": handoffs, "count": len(handoffs)}

@router.post("/handoff/resolve")
def resolve_handoff(req: ResolveRequest):
    handoff_manager.resolve_handoff(req.session_id)
    return {"status": "success", "session_id": req.session_id}

