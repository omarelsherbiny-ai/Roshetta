# server/app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from server.app.config import settings
from server.app.db.seed import seed_data
from server.app.api.chat import router as chat_router
from server.app.api.actions import router as actions_router
from server.app.api.ocr import router as ocr_router
from server.app.api.ledger import router as ledger_router
from server.app.api.inventory import router as inventory_router
from server.app.api.auth import router as auth_router
from server.app.api.pharmacies import router as pharmacies_router
from server.app.api.staff import router as staff_router
from server.app.api.me import router as me_router
from server.app.api.ai import create_ai_app
from server.app.services.security import validate_auth_configuration


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure database tables & seed Egyptian medicines catalog
    validate_auth_configuration()
    print("[Roshetta] Initializing database and verifying pharmacy catalog...")
    await seed_data()
    micromind_state = "enabled" if settings.USE_MICROMIND and settings.MICROMIND_API_URL else "disabled"
    print(f"[Roshetta] Backend ready. MicroMind text integration {micromind_state}; OCR scans unavailable.")
    yield
    # Shutdown
    print("[Roshetta] Shutting down server.")


class HealthResponse(BaseModel):
    status: str
    app: str
    micromind_configured: bool
    micromind_enabled: bool
    ocr_available: bool
    version: str


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Agentic-AI Pharmacy Operating System for Roshetta (روشتة)",
    lifespan=lifespan
)

# CORS setup for web and mobile frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(chat_router)
app.include_router(actions_router)
app.include_router(ocr_router)
app.include_router(ledger_router)
app.include_router(inventory_router)
app.include_router(auth_router)
app.include_router(pharmacies_router)
app.include_router(staff_router)
app.include_router(me_router)

# AI-safe read tools for MicroMind's OpenAPI Toolkit. The toolkit imports
# /ai/openapi.json (read-only routes, own response models), not /openapi.json.
# AI_PUBLIC_URL (server/.env) is the public HTTPS base, e.g. the tunnel URL.
app.mount("/ai", create_ai_app(settings.AI_PUBLIC_URL))


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return {
        "status": "healthy",
        "app": "Roshetta",
        "micromind_configured": bool(settings.MICROMIND_API_URL),
        "micromind_enabled": bool(settings.USE_MICROMIND and settings.MICROMIND_API_URL),
        "ocr_available": False,
        "version": settings.VERSION
    }