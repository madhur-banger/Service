from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from app.api.router import router
from app.db.base import Base, engine

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Webhook Delivery Service",
    description="A service for webhook ingestion, queuing, and delivery with retry capability",
    version="0.1.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(router, prefix="/api")

# Mount static files
if os.path.exists("app/static"):
    app.mount("/app", StaticFiles(directory="app/static", html=True), name="static")

@app.get("/")
async def root():
    return {"message": "Welcome to the Webhook Delivery Service API"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)