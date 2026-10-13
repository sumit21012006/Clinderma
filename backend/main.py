import os
import sys
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Ensure backend folder is in python path
sys.path.insert(0, os.path.dirname(__file__))

from app.core.config import settings
from app.core.auth import ensure_default_admin
from app.core.db import run_migrations
from app.api import chat, leads, orders, handoff, health, dashboard
from app.api import auth_api, kb_admin, offers_admin, doctor_review, audit_log, analytics, admin_users
from app.services.rag_engine import rag_engine

FRONTEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "frontend"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Run DB migrations (creates all tables including new PRD tables) ────────
    run_migrations()

    # ── Seed default admin/doctor/viewer users if none exist ──────────────────
    ensure_default_admin()

    # ── LLM/Vector provider startup warnings ─────────────────────────────────
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
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials="*" not in settings.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Original API Routers (unchanged) ─────────────────────────────────────────
app.include_router(health.router,     prefix=settings.API_PREFIX, tags=["Health"])
app.include_router(chat.router,       prefix=settings.API_PREFIX, tags=["Chatbot"])
app.include_router(leads.router,      prefix=settings.API_PREFIX, tags=["CRM Leads"])
app.include_router(orders.router,     prefix=settings.API_PREFIX, tags=["Order Tracking"])
app.include_router(handoff.router,    prefix=settings.API_PREFIX, tags=["Human Agent Handoff"])
app.include_router(dashboard.router,  prefix=settings.API_PREFIX, tags=["Dashboard Analytics"])

# ─── New PRD API Routers ───────────────────────────────────────────────────────
app.include_router(auth_api.router,      prefix=settings.API_PREFIX, tags=["Auth"])
app.include_router(kb_admin.router,      prefix=settings.API_PREFIX, tags=["Knowledge Base Admin"])
app.include_router(offers_admin.router,  prefix=settings.API_PREFIX, tags=["Offers Management"])
app.include_router(doctor_review.router, prefix=settings.API_PREFIX, tags=["Doctor Review"])
app.include_router(audit_log.router,     prefix=settings.API_PREFIX, tags=["Change Log"])
app.include_router(analytics.router,     prefix=settings.API_PREFIX, tags=["Analytics"])
app.include_router(admin_users.router,   prefix=settings.API_PREFIX, tags=["Admin Users"])


# The dashboard shell is public; its clinical APIs require a doctor/admin JWT.
# Keeping authentication in the page avoids a new browser Basic-Auth prompt on
# every navigation while still protecting all patient data.
@app.get("/dashboard.html", include_in_schema=False)
@app.get("/dashboard", include_in_schema=False)
def serve_dashboard():
    """Serve the Skin Coach dashboard; client-side JWT login protects data."""
    dashboard_file = os.path.join(FRONTEND_DIR, "dashboard.html")
    return FileResponse(dashboard_file)


# New admin panel (JWT login — no Basic Auth required, handled client-side)
@app.get("/admin", include_in_schema=False)
@app.get("/admin.html", include_in_schema=False)
def serve_admin_panel():
    """Serves the new PRD Admin Panel (JWT login handled in-browser)."""
    admin_file = os.path.join(FRONTEND_DIR, "admin.html")
    if os.path.exists(admin_file):
        return FileResponse(admin_file)
    return FileResponse(os.path.join(FRONTEND_DIR, "dashboard.html"))


# Mount Frontend directory for static web serving
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
