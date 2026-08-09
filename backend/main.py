import os
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Ensure backend folder is in python path
sys.path.insert(0, os.path.dirname(__file__))

from app.core.config import settings
from app.api import chat, leads, orders, handoff, health

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Scalable Multi-Channel Customer Support Chatbot API for Clinderma"
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

# Mount Frontend directory for static web serving
FRONTEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
