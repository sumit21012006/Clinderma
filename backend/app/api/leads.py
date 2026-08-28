from fastapi import APIRouter, HTTPException
from app.models.schemas import LeadCreateRequest, LeadResponse
from app.providers.crm_provider import get_crm_provider
from app.core.db import get_conn

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
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM leads ORDER BY created_at DESC")
    leads = cursor.fetchall()
    cursor.close()
    conn.close()
    return {"leads": [dict(r) for r in leads], "count": len(leads)}
