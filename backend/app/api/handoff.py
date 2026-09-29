from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.services.handoff_manager import handoff_manager
from app.core.auth import verify_admin

router = APIRouter()


class ResolveRequest(BaseModel):
    session_id: str


@router.get("/handoff")
def get_handoffs(_admin: str = Depends(verify_admin)):
    """
    Protected endpoint: returns all human escalation tickets for the admin dashboard.
    Requires HTTP Basic Authentication.
    """
    handoffs = handoff_manager.get_all_handoffs()
    return {"handoffs": handoffs, "count": len(handoffs)}


@router.post("/handoff/resolve")
def resolve_handoff(req: ResolveRequest, _admin: str = Depends(verify_admin)):
    """
    Protected endpoint: resolves an escalation ticket.
    Requires HTTP Basic Authentication.
    """
    handoff_manager.resolve_handoff(req.session_id)
    return {"status": "success", "session_id": req.session_id}
