import os
import time
import logging
from google import genai
from google.genai import types

# Per-key cooldown tracking: {key_index: cooldown_expiry_timestamp}
_key_cooldowns: dict[int, float] = {}
KEY_COOLDOWN_SECONDS = 600  # 10 minutes

def _load_api_keys() -> list[str]:
    """Load and parse Gemini API keys from env/secrets. Called once at module load."""
    api_key_str = os.environ.get("GEMINI_API_KEY")
    if not api_key_str:
        try:
            import streamlit as st
            api_key_str = st.secrets.get("GEMINI_API_KEY")
        except Exception:
            pass
    if not api_key_str:
        try:
            from placement_tracker.config import GEMINI_API_KEY
            api_key_str = GEMINI_API_KEY
        except Exception:
            pass
    if not api_key_str:
        return []
    # Render sometimes wraps the entire env var value in quotes, e.g. '"key1,key2"'
    api_key_str = api_key_str.strip().strip("'\"").strip()
    keys = [k.strip().strip("'\"").strip() for k in api_key_str.split(",") if k.strip().strip("'\"").strip()]
    logging.info(f"[LLM] Loaded {len(keys)} Gemini API key(s).")
    return keys

# Cached at import time — re-read only if the list is empty (env var wasn't set yet)
_API_KEYS: list[str] = _load_api_keys()

def get_api_keys() -> list[str]:
    """Returns cached API keys, re-loading if the cache is empty."""
    global _API_KEYS
    if not _API_KEYS:
        _API_KEYS = _load_api_keys()
    return _API_KEYS

def generate_content_with_fallback(prompt: str, config: types.GenerateContentConfig = None, model: str = 'gemini-3.5-flash'):
    keys = get_api_keys()
    if not keys:
        raise ValueError("No GEMINI_API_KEY found in environment or secrets.")

    max_attempts = len(keys) * 3  # Give each key up to 3 full cycles

    for attempt in range(max_attempts):
        now = time.time()

        # Find the next available (non-cooled-down) key
        available_key = None
        available_idx = None
        for key_idx, key in enumerate(keys):
            cooldown_until = _key_cooldowns.get(key_idx, 0)
            if now >= cooldown_until:
                available_key = key
                available_idx = key_idx
                break

        if available_key is None:
            # All keys are on cooldown — find the soonest one to expire and wait for it
            soonest_expiry = min(_key_cooldowns.values())
            wait_secs = max(0, soonest_expiry - now)
            logging.warning(f"[LLM] All {len(keys)} Gemini keys are on cooldown. Waiting {wait_secs:.0f}s for next available key...")
            time.sleep(wait_secs + 1)
            continue

        try:
            client = genai.Client(api_key=available_key, vertexai=False)
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=config
            )
            return response

        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "quota" in err_str or "exhausted" in err_str or "rate limit" in err_str:
                expiry = time.time() + KEY_COOLDOWN_SECONDS
                _key_cooldowns[available_idx] = expiry
                logging.warning(
                    f"[LLM] Key {available_idx + 1}/{len(keys)} rate limited. "
                    f"Cooling down for {KEY_COOLDOWN_SECONDS // 60} min. Trying next key..."
                )
                continue
            else:
                # Structural error (400, auth, etc) — raise immediately, not a rate limit
                raise e

    raise Exception(f"All Gemini API keys failed after {max_attempts} attempts due to rate limiting.")
