import sqlite3
from fastapi import APIRouter, HTTPException
from app.models.schemas import LeadCreateRequest, LeadResponse
from app.providers.crm_provider import get_crm_provider
from app.core.config import settings

router = APIRouter()
crm_provider = get_crm_provider()

@router.post("/leads", response_model=LeadResponse)
def create_lead(req: LeadCreateRequest):
    try:
        res = crm_provider.create_lead(
            phone_number=req.phone_number,
            name=req.name,
            concern=req.concern,
            channel=req.channel
        )
        return LeadResponse(**res)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/leads")
def get_all_leads():
    conn = sqlite3.connect(settings.DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM leads ORDER BY created_at DESC")
    rows = cursor.fetchall()
    leads = [dict(r) for r in rows]
    conn.close()
    return {"leads": leads, "count": len(leads)}
