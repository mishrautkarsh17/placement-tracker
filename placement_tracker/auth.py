import os
import json
import logging
import streamlit as st
from google.oauth2.credentials import Credentials
import urllib.parse
from google.auth.transport.requests import Request
import requests
import datetime

from placement_tracker import config

# If modifying these scopes, delete the file token.json.
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid"
]
TOKEN_FILE = 'user_token.json'

def get_oauth_url():
    params = {
        "client_id": config.GOOGLE_CLIENT_ID,
        "redirect_uri": config.get_secret("GOOGLE_REDIRECT_URI", default="http://localhost:8501"),
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent"
    }
    return "https://accounts.google.com/o/oauth2/auth?" + urllib.parse.urlencode(params)

def exchange_code_for_token(code):
    data = {
        "code": code,
        "client_id": config.GOOGLE_CLIENT_ID,
        "client_secret": config.GOOGLE_CLIENT_SECRET,
        "redirect_uri": config.get_secret("GOOGLE_REDIRECT_URI", default="http://localhost:8501"),
        "grant_type": "authorization_code"
    }
    res = requests.post("https://oauth2.googleapis.com/token", data=data)
    if res.status_code == 200:
        token_data = res.json()
        refresh_token = token_data.get("refresh_token")

        # Build google.oauth2.credentials format
        creds_data = {
            "token": token_data.get("access_token"),
            "refresh_token": refresh_token,
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": config.GOOGLE_CLIENT_ID,
            "client_secret": config.GOOGLE_CLIENT_SECRET,
            "scopes": SCOPES,
            "expiry": (datetime.datetime.utcnow() + datetime.timedelta(seconds=token_data.get("expires_in", 3600))).isoformat() + "Z"
        }
        with open(TOKEN_FILE, 'w') as f:
            json.dump(creds_data, f)

        # Push refresh token to the backend so the cron watcher can use it for calendar sync.
        # This keeps the cron self-sustaining — every login refreshes the backend's token.
        if refresh_token:
            try:
                api_url = config.get_secret("API_URL", default="http://localhost:8000/api")
                requests.post(
                    f"{api_url}/store-refresh-token",
                    json={"refresh_token": refresh_token},
                    timeout=5
                )
                logging.info("[AUTH] Pushed refresh token to backend for cron use.")
            except Exception as e:
                logging.warning(f"[AUTH] Could not push refresh token to backend: {e}")

        return True
    else:
        logging.error(f"Failed to exchange token: {res.text}")
        return False

def get_user_credentials():
    """Gets valid user credentials from storage or from env var (for server deployments)."""
    creds = None

    # 1. Try token file first (local dev / frontend-authenticated)
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except Exception as e:
            logging.warning(f"Could not load token file: {e}")

    # 2. Fall back to GOOGLE_REFRESH_TOKEN env var (Render / server deployments)
    if not creds:
        refresh_token = os.environ.get("GOOGLE_REFRESH_TOKEN")
        if not refresh_token:
            # Also try config
            try:
                from placement_tracker.config import get_secret
                refresh_token = get_secret("GOOGLE_REFRESH_TOKEN")
            except Exception:
                pass

        if refresh_token:
            try:
                creds = Credentials(
                    token=None,
                    refresh_token=refresh_token.strip().strip("'\"\n"),
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=config.GOOGLE_CLIENT_ID,
                    client_secret=config.GOOGLE_CLIENT_SECRET,
                    scopes=SCOPES,
                )
                logging.info("[AUTH] Using GOOGLE_REFRESH_TOKEN from environment.")
            except Exception as e:
                logging.error(f"Failed to build credentials from refresh token: {e}")

    # 3. Refresh if expired
    if creds and (not creds.valid) and creds.refresh_token:
        try:
            creds.refresh(Request())
            # Persist back to file if we can
            try:
                with open(TOKEN_FILE, 'w') as token:
                    token.write(creds.to_json())
            except Exception:
                pass  # Fine on Render, ephemeral fs
        except Exception as e:
            logging.error(f"Failed to refresh token: {e}")
            creds = None

    return creds

def get_user_profile():
    """Fetches the authenticated user's profile information."""
    creds = get_user_credentials()
    if not creds:
        return None
        
    try:
        response = requests.get(
            "https://www.googleapis.com/oauth2/v1/userinfo?alt=json",
            headers={"Authorization": f"Bearer {creds.token}"}
        )
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        logging.error(f"Failed to fetch user profile: {e}")
        
    return None
