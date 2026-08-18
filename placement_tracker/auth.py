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
        
        # Build google.oauth2.credentials format
        creds_data = {
            "token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token"),
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": config.GOOGLE_CLIENT_ID,
            "client_secret": config.GOOGLE_CLIENT_SECRET,
            "scopes": SCOPES,
            "expiry": (datetime.datetime.utcnow() + datetime.timedelta(seconds=token_data.get("expires_in", 3600))).isoformat() + "Z"
        }
        with open(TOKEN_FILE, 'w') as f:
            json.dump(creds_data, f)
        return True
    else:
        logging.error(f"Failed to exchange token: {res.text}")
        return False

def get_user_credentials():
    """Gets valid user credentials from storage."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            # Save updated creds
            with open(TOKEN_FILE, 'w') as token:
                token.write(creds.to_json())
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
