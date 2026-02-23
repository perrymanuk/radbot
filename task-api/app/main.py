from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.routes import projects, tasks

app = FastAPI(
    title="Radbot Task API",
    description="API for accessing Radbot task and project data",
    version="0.1.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

@app.get("/healthz")
async def healthz_check():
    """Healthz endpoint."""
    return {"status": "ok"}

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}

# Include routers
app.include_router(projects.router, prefix=settings.API_V1_STR)
app.include_router(tasks.router, prefix=settings.API_V1_STR)