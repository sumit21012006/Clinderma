from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default_session"
    language: Optional[str] = "en" # 'en', 'hi', 'mr'
    channel: Optional[str] = "website" # 'website', 'instagram', 'whatsapp'
    user_phone: Optional[str] = None

class KBSource(BaseModel):
    id: str
    source: str
    category: str
    question: str
    score: float

class ChatResponse(BaseModel):
    answer: str
    grounded: bool
    confidence: float
    handoff_recommended: bool = False
    handoff_reason: Optional[str] = None
    sources: List[KBSource] = []
    language: str = "en"
    session_id: str

class LeadCreateRequest(BaseModel):
    name: Optional[str] = "Web Visitor"
    phone_number: str
    concern: Optional[str] = "General Skincare Inquiry"
    channel: str = "website"
    session_id: Optional[str] = None

class LeadResponse(BaseModel):
    lead_id: str
    phone_number: str
    status: str
    kylas_synced: bool
    created_at: str

class OrderResponse(BaseModel):
    order_id: str
    status: str
    customer_name: str
    items: List[str]
    estimated_delivery: str
    tracking_url: str
    found: bool = True

class HandoffRequest(BaseModel):
    session_id: str
    user_name: Optional[str] = "Anonymous"
    user_phone: Optional[str] = None
    reason: str = "User requested human agent or complex query"
    channel: str = "website"

class HandoffSession(BaseModel):
    session_id: str
    user_name: str
    user_phone: Optional[str]
    reason: str
    channel: str
    transcript: List[Dict[str, Any]]
    status: str # 'pending', 'connected', 'resolved'
    created_at: str
