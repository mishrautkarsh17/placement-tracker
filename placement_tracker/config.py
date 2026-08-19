import os

def get_secret(key, default=None):
    """Get secret from environment variable first, then Streamlit secrets, then default."""
    # 1. Check environment variable (used by GitHub Actions)
    env_val = os.environ.get(key)
    if env_val:
        return env_val
    
    # 2. Check Streamlit secrets (used by Streamlit Cloud / local dev)
    try:
        import streamlit as st
        if st.secrets and key in st.secrets:
            return st.secrets[key]
    except (ImportError, FileNotFoundError, Exception):
        pass
    
    return default

# Gmail Config
GMAIL_USER = get_secret("GMAIL_USER")
GMAIL_APP_PASSWORD = get_secret("GMAIL_APP_PASSWORD")

# Gemini Config
GEMINI_API_KEY = get_secret("GEMINI_API_KEY")

# Sheets Config
GOOGLE_SHEET_ID = get_secret("GOOGLE_SHEET_ID")
COLLEGE_CALENDAR_SHEET_ID = get_secret("COLLEGE_CALENDAR_SHEET_ID", default="1FqgXNGWUUa5uHRYEHEZ7iYz3ZpOpah7TnGIBGLhyoRU")
CALENDAR_SHEET_TAB = get_secret("CALENDAR_SHEET_TAB", default="Calendar")
OFFERS_SHEET_TAB = get_secret("OFFERS_SHEET_TAB", default="Offers")
MTECH_OFFERS_SHEET_TAB = get_secret("MTECH_OFFERS_SHEET_TAB", default="Mtech offers")
PRIVATE_SHEET_ID = get_secret("PRIVATE_SHEET_ID", default="1PhkTax9UdjG7cv5vdsHbrn721YtnUnQvlUsfoEllwms")
APPLICATIONS_SHEET_TAB = get_secret("APPLICATIONS_SHEET_TAB", default="application")

POD_AI_URL = get_secret("POD_AI_URL", default="https://td.pod.ai")
POD_AI_USERNAME = get_secret("POD_AI_USERNAME")
POD_AI_PASSWORD = get_secret("POD_AI_PASSWORD")

def _get_local_google_creds():
    import json
    try:
        # Check one level up for google_credentials.json since we are inside placement_tracker/
        creds_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "google_credentials.json")
        with open(creds_path, "r") as f:
            return json.load(f).get("web", {})
    except Exception:
        return {}

_local_creds = _get_local_google_creds()

GOOGLE_CLIENT_ID = get_secret("GOOGLE_CLIENT_ID") or _local_creds.get("client_id")
GOOGLE_CLIENT_SECRET = get_secret("GOOGLE_CLIENT_SECRET") or _local_creds.get("client_secret")
GOOGLE_REDIRECT_URI = get_secret("GOOGLE_REDIRECT_URI") or _local_creds.get("redirect_uris", ["http://localhost:8501"])[0]

# Pod.ai Scraper Selectors (Placeholders to be updated)
POD_AI_SELECTORS = {
    "applications_tab": "a:has-text('Applications')",
    "card": ".application-card", # Needs update
    "job_title": ".job-title", # Needs update
    "company_name": ".company-name", # Needs update
    "status_badge": ".status-badge", # Needs update
    "ctc": ".ctc-value", # Needs update
    "job_type": ".job-type", # Needs update
    "location": ".location", # Needs update
    "next_button": "button:has-text('Next')" # Needs update
}

SHEET_COLUMNS = [
    "student_name", 
    "student_id", 
    "company_name", 
    "job_role", 
    "ctc", 
    "status", 
    "source", 
    "last_updated"
]
