import re
from fastapi import APIRouter, HTTPException, Depends
from app.models.schemas import LeadCreateRequest, LeadResponse, AssessmentRequest, AssessmentResponse
from app.providers.crm_provider import get_crm_provider
from app.core.db import get_conn
from app.core.auth import verify_admin

router = APIRouter()
crm_provider = get_crm_provider()


def _clean_phone(phone: str) -> str:
    """Normalize phone number to 10 digits."""
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    return digits


@router.post("/leads", response_model=LeadResponse)
def create_lead(req: LeadCreateRequest):
    """Public endpoint: records leads captured by chatbot widget."""
    try:
        clean_num = _clean_phone(req.phone_number)
        if len(clean_num) != 10:
            raise HTTPException(status_code=400, detail="Invalid phone number. Must be a 10-digit Indian mobile number.")
        res = crm_provider.create_lead(
            phone_number=clean_num,
            name=req.name,
            concern=req.concern,
            channel=req.channel
        )
        return LeadResponse(**res)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/assessment", response_model=AssessmentResponse)
def submit_assessment(req: AssessmentRequest):
    """
    Public endpoint: receives patient skin assessment form submissions.
    Saves lead to CRM (Kylas/local) with detailed clinical intake information.
    """
    try:
        clean_num = _clean_phone(req.phone_number)
        if len(clean_num) != 10:
            raise HTTPException(status_code=400, detail="Invalid phone number. Must be a 10-digit Indian mobile number.")

        full_concern = (
            f"Skin Assessment: {req.concern} | "
            f"Duration: {req.duration} | "
            f"Skin Type: {req.skin_type}"
        )
        res = crm_provider.create_lead(
            phone_number=clean_num,
            name=req.name.strip(),
            concern=full_concern,
            channel=req.channel or "assessment_form"
        )
        return AssessmentResponse(
            status="success",
            lead_id=res["lead_id"],
            message="Assessment submitted successfully! A Clinderma Skin Coach will contact you within 24 hours."
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/leads")
def get_all_leads(_admin: str = Depends(verify_admin)):
    """
    Protected endpoint: returns all captured leads for the admin dashboard.
    Requires HTTP Basic Authentication.
    """
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM leads ORDER BY created_at DESC")
    leads = cursor.fetchall()
    cursor.close()
    conn.close()
    return {"leads": [dict(r) for r in leads], "count": len(leads)}
