from fastapi import APIRouter, HTTPException
from app.models.schemas import ChatRequest, ChatResponse
from app.services.rag_engine import rag_engine

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
def handle_chat(req: ChatRequest):
    try:
        res = rag_engine.process_chat(req)
        return ChatResponse(**res)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
