import os
import time
import logging
from google import genai
from google.genai import types

def get_api_keys() -> list[str]:
    # 1. Environment variable
    api_key_str = os.environ.get("GEMINI_API_KEY")
    # 2. Streamlit secrets fallback
    if not api_key_str:
        try:
            import streamlit as st
            api_key_str = st.secrets.get("GEMINI_API_KEY")
        except Exception:
            pass
            
    if not api_key_str:
        # Also try config if loaded
        try:
            from placement_tracker.config import GEMINI_API_KEY
            api_key_str = GEMINI_API_KEY
        except Exception:
            pass
    
    if not api_key_str:
        return []
    
    # Support multiple comma-separated keys, aggressively strip quotes and spaces
    return [k.strip().strip("'\"").strip() for k in api_key_str.split(",") if k.strip().strip("'\"").strip()]

def generate_content_with_fallback(prompt: str, config: types.GenerateContentConfig = None, model: str = 'gemini-3.5-flash'):
    keys = get_api_keys()
    if not keys:
        raise ValueError("No GEMINI_API_KEY found in environment or secrets.")
        
    base_wait_time = 15
    max_retries_per_key = 3
    
    # Attempt to cycle through keys if one hits a limit
    for attempt in range(max_retries_per_key):
        for key_idx, key in enumerate(keys):
            try:
                # Force SDK to NOT use GCP Application Default Credentials by explicitly passing vertexai=False
                client = genai.Client(api_key=key, vertexai=False)
                
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config
                )
                return response
            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "quota" in err_str or "exhausted" in err_str or "rate limit" in err_str:
                    logging.warning(f"API Key {key_idx+1}/{len(keys)} exhausted/rate limited. Trying next key...")
                    continue
                else:
                    # If it's a structural error (400, etc), raise immediately
                    raise e
                    
        # If we reach here, we exhausted all keys in this cycle.
        wait_time = base_wait_time * (2 ** attempt)
        logging.warning(f"All {len(keys)} Gemini keys hit rate limits. Waiting {wait_time}s before retrying...")
        time.sleep(wait_time)
        
    raise Exception(f"All Gemini API keys failed after {max_retries_per_key} retry cycles due to rate limiting.")
