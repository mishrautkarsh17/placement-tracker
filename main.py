from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import threading
import time
import os
import logging

# Set local timezone to IST for Render logs (Linux)
if hasattr(time, 'tzset'):
    os.environ['TZ'] = 'Asia/Kolkata'
    time.tzset()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def start_cron_watcher():
    """Run the cron watcher in a background thread."""
    try:
        from cron_watcher import main
        main()
    except Exception as e:
        logging.error(f"Cron watcher crashed: {e}")

@asynccontextmanager
async def lifespan(app):
    # Start cron watcher in background thread on startup
    cron_thread = threading.Thread(target=start_cron_watcher, daemon=True)
    cron_thread.start()
    logging.info("Background cron watcher started.")
    yield
    # Cleanup on shutdown
    logging.info("Shutting down cron watcher.")

app = FastAPI(
    title="AI Placement Copilot API",
    description="Backend for the AI Placement Copilot Streamlit App",
    version="1.0.0",
    lifespan=lifespan
)

# Allow Streamlit frontend to make requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict this to your Streamlit app domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.api_route("/health", methods=["GET", "HEAD"])
async def health_check():
    return {"status": "ok", "message": "AI Placement Copilot is running"}

@app.api_route("/", methods=["GET", "HEAD"])
async def root_check():
    return {"status": "ok", "message": "API is running. See /docs for more info."}

from api import routes
app.include_router(routes.router, prefix="/api")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
