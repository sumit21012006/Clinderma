from fastapi import APIRouter
from app.core.config import settings

router = APIRouter()

@router.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "providers": {
            "llm": settings.LLM_PROVIDER,
            "vector_store": settings.VECTOR_STORE_PROVIDER,
            "crm": settings.CRM_PROVIDER,
            "order": settings.ORDER_PROVIDER
        }
    }
