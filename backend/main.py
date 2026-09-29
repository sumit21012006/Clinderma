import os
import sys
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Ensure backend folder is in python path
sys.path.insert(0, os.path.dirname(__file__))

from app.core.config import settings
from app.core.auth import verify_admin
from app.api import chat, leads, orders, handoff, health, dashboard
from app.services.rag_engine import rag_engine

FRONTEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "frontend"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup validation
    if settings.LLM_PROVIDER == "gemini" and not settings.GEMINI_API_KEY:
        print("[WARNING] GEMINI_API_KEY is not configured! Gemini LLM calls will fail.")
    if settings.CRM_PROVIDER == "kylas_api" and not settings.KYLAS_API_KEY:
        print("[WARNING] KYLAS_API_KEY is not configured! Live Kylas syncing will fail.")

    if settings.RAG_WARMUP_ENABLED:
        await asyncio.to_thread(rag_engine.warmup)
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Scalable Multi-Channel Customer Support Chatbot API for Clinderma",
    lifespan=lifespan,
)

# Enable CORS for cross-origin widget integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(health.router, prefix=settings.API_PREFIX, tags=["Health"])
app.include_router(chat.router, prefix=settings.API_PREFIX, tags=["Chatbot"])
app.include_router(leads.router, prefix=settings.API_PREFIX, tags=["CRM Leads"])
app.include_router(orders.router, prefix=settings.API_PREFIX, tags=["Order Tracking"])
app.include_router(handoff.router, prefix=settings.API_PREFIX, tags=["Human Agent Handoff"])
app.include_router(dashboard.router, prefix=settings.API_PREFIX, tags=["Dashboard Analytics"])


# Protected Admin Dashboard routes (HTTP Basic Auth required)
@app.get("/dashboard.html", include_in_schema=False)
@app.get("/dashboard", include_in_schema=False)
def serve_dashboard(_admin: str = Depends(verify_admin)):
    """Serves the internal admin dashboard to authenticated administrators only."""
    dashboard_file = os.path.join(FRONTEND_DIR, "dashboard.html")
    return FileResponse(dashboard_file)


# Mount Frontend directory for static web serving (homepage, widget, assessment form, assets)
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
