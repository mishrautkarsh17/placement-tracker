from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from typing import List, Dict, Any
from pydantic import BaseModel
import sys
import os
import io
import logging

# Ensure we can import from the existing project structure
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from placement_tracker.storage import sheets_client

# In-memory store for the OAuth refresh token pushed by the frontend after login.
# Falls back to GOOGLE_REFRESH_TOKEN env var if never set at runtime.
_runtime_refresh_token: str | None = None

router = APIRouter()

# --- Simple manual caching for MVP ---
import time
CACHE_TTL = 300 # 5 minutes

class SimpleCache:
    def __init__(self):
        self.cache = {}
        self.timestamps = {}

    def get(self, key):
        if key in self.cache and time.time() - self.timestamps.get(key, 0) < CACHE_TTL:
            return self.cache[key]
        return None

    def set(self, key, value):
        self.cache[key] = value
        self.timestamps[key] = time.time()

data_cache = SimpleCache()

@router.get("/calendar")
def get_calendar():
    cached = data_cache.get("calendar")
    if cached is not None:
        return {"data": cached}
        
    try:
        df = sheets_client.read_calendar()
        if df.empty:
            return {"data": []}
        data = df.fillna("").to_dict(orient="records")
        data_cache.set("calendar", data)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/offers")
def get_offers():
    cached = data_cache.get("offers")
    if cached is not None:
        return {"data": cached}
        
    try:
        df = sheets_client.read_offers()
        if df.empty:
            return {"data": []}
        data = df.fillna("").to_dict(orient="records")
        data_cache.set("offers", data)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/applications/{student_id}")
def get_applications(student_id: str):
    # Personal data, caching might be tricky if it updates often, but 5 mins is okay
    cache_key = f"apps_{student_id}"
    cached = data_cache.get(cache_key)
    if cached is not None:
        return {"data": cached}
        
    try:
        df = sheets_client.read_applications(student_id)
        if df.empty:
            return {"data": []}
        data = df.fillna("").to_dict(orient="records")
        data_cache.set(cache_key, data)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/analytics")
def get_analytics():
    cached = data_cache.get("analytics")
    if cached is not None:
        return cached

    try:
        df_offers = sheets_client.read_offers()
        
        if df_offers.empty:
            return {"total_offers": 0, "companies_hiring": 0, "offers_by_role": {}}

        total_offers = len(df_offers)
        companies_hiring = int(df_offers["company_name"].nunique()) if "company_name" in df_offers.columns else 0
        
        offers_by_role = {}
        if "offer_type" in df_offers.columns:
            counts = df_offers["offer_type"].value_counts().to_dict()
            offers_by_role = {str(k): int(v) for k, v in counts.items()}
            
        result = {
            "total_offers": total_offers,
            "companies_hiring": companies_hiring,
            "offers_by_role": offers_by_role
        }
        
        data_cache.set("analytics", result)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class ChatRequest(BaseModel):
    message: str
    student_id: str

@router.post("/chat")
def chat_copilot(request: ChatRequest):
    from ai.router import route_query, generate_copilot_response
    
    intent_info = route_query(request.message)
    
    if intent_info["intent"] == "DATA_QUERY":
        # Handle deterministic query (MVP: just return a canned response instructing to use the analytics tab)
        return {
            "reply": "I see you're looking for specific company data! Please check the Analytics and Global Offers tabs for real-time filtered data.",
            "sources": []
        }
    
    # Handle REASONING intent
    # Assemble context
    app_data = get_applications(request.student_id).get("data", [])
    cal_data = get_calendar().get("data", [])
    
    context = {}
    context["my_applications"] = app_data
    context["calendar_events"] = _get_filtered_upcoming_events(cal_data, app_data)[:10]
    
    # Call Gemini
    reply = generate_copilot_response(request.message, context)
    
    return {
        "reply": reply,
        "sources": ["Calendar", "Applications"]
    }

def _get_filtered_upcoming_events(cal_data, app_data):
    if not cal_data:
        return []
        
    import re
    import pandas as pd
    def norm(name): return re.sub(r'[^a-z0-9]', '', str(name).lower())
    
    ineligible_companies = set()
    for app in app_data:
        status = str(app.get("status", "")).strip().lower()
        if "not eligible" in status or "not-eligible" in status:
            ineligible_companies.add(norm(app.get("company_name", "")))

    upcoming_events = []
    date_col = next((k for k in cal_data[0].keys() if "date" in str(k).lower()), None)
    comp_col = next((k for k in cal_data[0].keys() if "company" in str(k).lower()), None)
    
    if date_col:
        today = pd.Timestamp.now().normalize()
        for row in cal_data:
            comp_name = norm(row.get(comp_col, "")) if comp_col else ""
            if comp_name and comp_name in ineligible_companies:
                continue
                
            try:
                event_date = pd.to_datetime(row.get(date_col, ""), dayfirst=True)
                if event_date >= today:
                    upcoming_events.append(row)
            except Exception:
                upcoming_events.append(row)
    else:
        upcoming_events = [r for r in cal_data if (norm(r.get(comp_col, "")) not in ineligible_companies if comp_col else True)]
        
    return upcoming_events

@router.get("/daily-brief/{student_id}")
def get_daily_brief(student_id: str):
    cache_key = f"daily_brief_{student_id}"
    cached = data_cache.get(cache_key)
    if cached is not None:
        return {"brief": cached}
        
    from ai.router import generate_copilot_response
    
    # Gather Context
    cal_data = get_calendar().get("data", [])
    app_data = get_applications(student_id).get("data", [])
    
    upcoming_events = _get_filtered_upcoming_events(cal_data, app_data)
    
    try:
        import json
        with open(os.path.join(os.path.dirname(__file__), "../data/company_kb.json"), "r") as f:
            kb = json.load(f)
    except Exception:
        kb = {}
        
    context = {
        "calendar_upcoming_7_days": upcoming_events[:15],
        "my_active_applications": app_data,
        "company_knowledge_base": kb
    }
    
    prompt = """
    Generate a concise daily placement briefing for the student.
    IMPORTANT: If historical preparation data or interview patterns are not available in the provided context for an upcoming company, YOU MUST use your Google Search tool to find typical interview questions, interview formats, and recent interview experiences for that company. Do not say data is unavailable!
    
    Format exactly like this (use markdown):
    
    ### 🎯 Today's Placement Summary
    - [Key event 1]
    - [Key event 2]
    
    ### 📚 Suggested Preparation
    - [Topic 1]: [Brief reason why, referencing upcoming events and company historical data]
    - [Topic 2]: [Brief reason why]
    
    ### 🚦 Priority
    [High/Medium/Low]
    """
    
    brief = generate_copilot_response(prompt, context)
    data_cache.set(cache_key, brief)
    return {"brief": brief}

@router.get("/company/{company_name}")
def get_company_info(company_name: str):
    try:
        import json
        with open(os.path.join(os.path.dirname(__file__), "../data/company_kb.json"), "r") as f:
            kb = json.load(f)
            
        # Case insensitive search
        for key in kb:
            if key.lower() == company_name.lower():
                return {"data": kb[key]}
        return {"data": None, "message": "Company not found in KB."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/sync-calendar")
def sync_calendar():
    try:
        res = sheets_client.sync_college_calendar()
        data_cache.cache.clear()  # Calendar updated, invalidate cache
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class RefreshTokenRequest(BaseModel):
    refresh_token: str

@router.post("/store-refresh-token")
def store_refresh_token(req: RefreshTokenRequest):
    """Called by the frontend after OAuth login to give the backend a refresh token.
    This lets the cron watcher perform calendar sync without a user session."""
    global _runtime_refresh_token
    _runtime_refresh_token = req.refresh_token.strip()
    # Also inject into environment so auth.py picks it up immediately
    os.environ["GOOGLE_REFRESH_TOKEN"] = _runtime_refresh_token
    logging.info("[AUTH] Runtime refresh token updated from frontend login.")
    return {"success": True}

class SyncAppRequest(BaseModel):
    pod_ai_username: str
    pod_ai_password: str
    student_name: str
    student_id: str

@router.post("/sync-applications")
def sync_applications(req: SyncAppRequest):
    from placement_tracker.pipeline import orchestrator
    try:
        res = orchestrator.sync_job_applications(
            pod_ai_username=req.pod_ai_username,
            pod_ai_password=req.pod_ai_password,
            student_name=req.student_name,
            student_id=req.student_id
        )
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync-email-offers")
def sync_email_offers():
    """Syncs offer letters from Gmail only (lightweight, no Playwright)."""
    from placement_tracker.pipeline import orchestrator
    try:
        res = orchestrator.sync_offer_letters()
        data_cache.cache.clear()  # Invalidate cache so dashboard refreshes
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/sync-ctc-enrichment")
def sync_ctc_enrichment():
    """Scrapes pod.ai to enrich CTC and offer type data (heavy, uses Playwright)."""
    from placement_tracker.pipeline import orchestrator
    from placement_tracker.config import POD_AI_USERNAME, POD_AI_PASSWORD
    if not POD_AI_USERNAME or not POD_AI_PASSWORD:
        raise HTTPException(status_code=400, detail="Pod.ai credentials not configured.")
    try:
        res = orchestrator.sync_global_opportunities(POD_AI_USERNAME, POD_AI_PASSWORD)
        data_cache.cache.clear()  # Invalidate cache so dashboard refreshes
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/clear-offers")
def clear_offers():
    from placement_tracker.storage import sheets_client
    try:
        return sheets_client.clear_all_offers()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/recommend-companies")
async def recommend_companies(resume: UploadFile = File(...)):
    """Accepts a PDF resume upload, extracts text, and returns AI-powered company recommendations."""
    from ai.router import generate_resume_recommendation

    if not resume.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    try:
        import pypdf
        contents = await resume.read()
        reader = pypdf.PdfReader(io.BytesIO(contents))
        resume_text = "\n".join(
            page.extract_text() for page in reader.pages if page.extract_text()
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not parse PDF: {e}")

    if not resume_text.strip():
        raise HTTPException(status_code=422, detail="No readable text found in the PDF. Please ensure it's not a scanned image.")

    # Get active companies from calendar cache
    try:
        cal_data = get_calendar().get("data", [])
        active_companies = [
            {"company": row.get("Company", row.get("company", "")), "ctc": row.get("CTC", "N/A")}
            for row in cal_data if row.get("Company") or row.get("company")
        ]
    except Exception:
        active_companies = []

    recommendation = generate_resume_recommendation(resume_text, active_companies)
    return {"recommendation": recommendation}
