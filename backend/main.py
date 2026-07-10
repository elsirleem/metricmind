import logging
import os

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from backend.db.database import create_tables, get_db
from backend.db.seed import seed_database
from backend.routers import intelligence, metrics, profile

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="MetricMind API", version="0.1.0")

# Additional origins (e.g. a deployed frontend URL) can be added via a
# comma-separated FRONTEND_URL env var without touching this list.
_allowed_origins = ["http://localhost:3000"]
if extra_origin := os.environ.get("FRONTEND_URL"):
    _allowed_origins += [o.strip() for o in extra_origin.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(profile.router)
app.include_router(metrics.router)
app.include_router(intelligence.router)


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
@app.on_event("startup")
def on_startup():
    create_tables()


# ---------------------------------------------------------------------------
# Seed endpoint (Step 13)
# ---------------------------------------------------------------------------
@app.post("/api/seed")
def seed(db: Session = Depends(get_db)):
    """Load mock data for the seed profile, bypassing ingestion."""
    seed_database(db)
    return {"status": "ok", "profile_id": "seed-profile-001"}


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"status": "ok"}
