"""
Standalone sync runner for GitHub Actions.
Usage:
    python sync_runner.py --task email
    python sync_runner.py --task calendar
    python sync_runner.py --task ctc
    python sync_runner.py --task all
"""
import argparse
import logging
import sys
import os
import json

sys.path.insert(0, os.path.abspath('.'))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def setup_gcp_credentials():
    """
    If GCP_SERVICE_ACCOUNT_JSON env var is set (GitHub Actions),
    write it to a temp file and set up the env for gspread.
    Also inject into streamlit-compatible format for sheets_client.
    """
    sa_json = os.environ.get("GCP_SERVICE_ACCOUNT_JSON", "").strip()
    if sa_json:
        try:
            parsed = json.loads(sa_json)
        except json.JSONDecodeError as json_err:
            try:
                import tomllib
                toml_parsed = tomllib.loads(sa_json)
                if "gcp_service_account" in toml_parsed:
                    parsed = toml_parsed["gcp_service_account"]
                else:
                    parsed = toml_parsed
                sa_json = json.dumps(parsed)
            except Exception as toml_err:
                logging.error(f"Failed to parse GCP_SERVICE_ACCOUNT_JSON as JSON or TOML. Please ensure the secret is valid. JSON Error: {json_err}")
                return None
            
        sa_path = os.path.join(os.path.dirname(__file__), "_service_account.json")
        with open(sa_path, "w") as f:
            f.write(sa_json)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = sa_path
        logging.info("GCP service account credentials loaded from env.")
        return parsed
    return None


def run_email_sync():
    """Sync placement offer emails from Gmail."""
    from placement_tracker.pipeline import orchestrator
    
    logging.info("=" * 50)
    logging.info("[EMAIL SYNC] Starting...")
    
    result = orchestrator.sync_offer_letters()
    
    if result["new_emails_found"] > 0:
        logging.info(f"[EMAIL SYNC] Processed {result['new_emails_found']} emails, upserted {result['email_records']} records.")
    else:
        logging.info("[EMAIL SYNC] No new emails found.")
    
    if result["errors"]:
        logging.error(f"[EMAIL SYNC] Errors: {result['errors']}")
    
    logging.info("[EMAIL SYNC] Done.")
    return result


def run_calendar_sync(sa_info: dict = None):
    """Sync the college calendar to local sheet."""
    import gspread
    from google.oauth2.service_account import Credentials
    from placement_tracker.config import GOOGLE_SHEET_ID, COLLEGE_CALENDAR_SHEET_ID, CALENDAR_SHEET_TAB
    
    logging.info("=" * 50)
    logging.info("[CALENDAR SYNC] Starting...")
    
    if not COLLEGE_CALENDAR_SHEET_ID:
        logging.warning("[CALENDAR SYNC] COLLEGE_CALENDAR_SHEET_ID not set, skipping.")
        return
    
    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    # Get credentials
    creds = None
    if sa_info:
        creds = Credentials.from_service_account_info(sa_info, scopes=SCOPES)
    else:
        sa_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if sa_path and os.path.exists(sa_path):
            creds = Credentials.from_service_account_file(sa_path, scopes=SCOPES)
        else:
            # Try streamlit secrets
            try:
                import streamlit as st
                creds = Credentials.from_service_account_info(
                    st.secrets["gcp_service_account"].to_dict(), scopes=SCOPES
                )
            except Exception:
                pass
    
    if not creds:
        logging.error("[CALENDAR SYNC] No credentials available.")
        return
    
    try:
        gc = gspread.authorize(creds)
        
        # Read source calendar
        college_sheet = gc.open_by_key(COLLEGE_CALENDAR_SHEET_ID)
        college_ws = college_sheet.get_worksheet(0)
        all_values = college_ws.get_all_values()
        
        if not all_values:
            logging.warning("[CALENDAR SYNC] College calendar is empty.")
            return
        
        # Write to local sheet
        local_sheet = gc.open_by_key(GOOGLE_SHEET_ID)
        local_ws = None
        for ws in local_sheet.worksheets():
            if ws.title.lower() == CALENDAR_SHEET_TAB.lower():
                local_ws = ws
                break
        if not local_ws:
            local_ws = local_sheet.add_worksheet(title=CALENDAR_SHEET_TAB, rows=1000, cols=15)
        
        local_ws.clear()
        local_ws.update(values=all_values, range_name="A1")
        logging.info(f"[CALENDAR SYNC] Done: {len(all_values)} rows written.")
    except Exception as e:
        logging.error(f"[CALENDAR SYNC] Failed: {e}")


def run_ctc_enrichment():
    """Scrape pod.ai and enrich offers with CTC data."""
    from placement_tracker.pipeline import orchestrator
    from placement_tracker.config import POD_AI_USERNAME, POD_AI_PASSWORD
    
    logging.info("=" * 50)
    logging.info("[CTC ENRICHMENT] Starting...")
    
    if not POD_AI_USERNAME or not POD_AI_PASSWORD:
        logging.warning("[CTC ENRICHMENT] Pod.ai credentials not set, skipping.")
        return
    
    result = orchestrator.sync_global_opportunities(POD_AI_USERNAME, POD_AI_PASSWORD)
    logging.info(f"[CTC ENRICHMENT] Done: {result['portal_records']} records enriched.")
    
    if result["errors"]:
        logging.error(f"[CTC ENRICHMENT] Errors: {result['errors']}")


def main():
    parser = argparse.ArgumentParser(description="Placement Tracker Sync Runner")
    parser.add_argument("--task", required=True, choices=["email", "calendar", "ctc", "all"],
                        help="Which sync task to run")
    args = parser.parse_args()
    
    # Setup GCP credentials from env if available
    sa_info = setup_gcp_credentials()
    
    if args.task == "email" or args.task == "all":
        run_email_sync()
    
    if args.task == "calendar" or args.task == "all":
        run_calendar_sync(sa_info)
    
    if args.task == "ctc" or args.task == "all":
        run_ctc_enrichment()
    
    logging.info("All requested tasks complete.")


if __name__ == "__main__":
    main()
