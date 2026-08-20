import time
import logging
import sys
import os
import gc
from google.oauth2.service_account import Credentials
from datetime import datetime

sys.path.insert(0, os.path.abspath('.'))
from placement_tracker.pipeline import orchestrator
from placement_tracker.storage import sheets_client
from placement_tracker.config import (
    GOOGLE_SHEET_ID, COLLEGE_CALENDAR_SHEET_ID, CALENDAR_SHEET_TAB,
    POD_AI_USERNAME, POD_AI_PASSWORD
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- INTERVALS (in seconds) ---
EMAIL_SYNC_INTERVAL = 14400        # 4 hours
CALENDAR_SYNC_INTERVAL = 43200     # 12 hours

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def sync_calendar_auto():
    """
    Syncs the college calendar using the User OAuth token.
    On local dev, uses user_token.json. On Render, uses GOOGLE_REFRESH_TOKEN env var.
    """
    try:
        logging.info("Starting calendar sync...")
        res = sheets_client.sync_college_calendar()
        if "error" in res:
            logging.warning(f"Calendar sync could not complete: {res['error']}")
        else:
            logging.info(f"Calendar sync complete: {res.get('rows', 0)} rows written.")
    except Exception as e:
        logging.error(f"Calendar sync failed: {e}")



def sync_ctc_enrichment():
    """
    Scrapes pod.ai opportunities and enriches Offers/Applications with CTC data.
    """
    if not POD_AI_USERNAME or not POD_AI_PASSWORD:
        logging.warning("Pod.ai credentials not configured, skipping CTC enrichment.")
        return

    try:
        logging.info("Starting global CTC enrichment...")
        result = orchestrator.sync_global_opportunities(POD_AI_USERNAME, POD_AI_PASSWORD)
        logging.info(f"CTC enrichment complete: {result['portal_records']} records processed.")
        if result["errors"]:
            logging.error(f"CTC enrichment errors: {result['errors']}")
    except Exception as e:
        logging.error(f"CTC enrichment failed: {e}")


def main():
    logging.info("=" * 60)
    logging.info("AI Placement Tracker - Automated Agent Starting")
    logging.info("=" * 60)
    logging.info(f"  Email sync:      every {EMAIL_SYNC_INTERVAL // 3600} hours")
    logging.info(f"  Calendar sync:   every {CALENDAR_SYNC_INTERVAL // 3600} hours")
    logging.info(f"  CTC enrichment:  On new email records")
    logging.info("=" * 60)

    last_email_sync = 0
    last_calendar_sync = 0

    # Run email + calendar once immediately on startup
    first_run = True

    while True:
        now = time.time()

        # --- EMAIL SYNC & CTC ENRICHMENT ---
        if first_run or (now - last_email_sync >= EMAIL_SYNC_INTERVAL):
            try:
                logging.info("[EMAIL] Checking for new placement offer emails...")
                result = orchestrator.sync_offer_letters()

                if result["new_emails_found"] > 0:
                    logging.info(f"[EMAIL] Processed {result['new_emails_found']} emails, upserted {result['email_records']} records.")
                    
                    if result['email_records'] > 0:
                        try:
                            logging.info("[CTC] New email records found. Running global CTC enrichment from pod.ai...")
                            sync_ctc_enrichment()
                        except Exception as e:
                            logging.error(f"[CTC] Fatal error: {e}")
                else:
                    logging.info("[EMAIL] No new emails found.")

                if result["errors"]:
                    logging.error(f"[EMAIL] Errors: {result['errors']}")
            except Exception as e:
                logging.error(f"[EMAIL] Fatal error: {e}")
            last_email_sync = time.time()

        # --- CALENDAR SYNC ---
        if first_run or (now - last_calendar_sync >= CALENDAR_SYNC_INTERVAL):
            try:
                logging.info("[CALENDAR] Syncing college calendar...")
                sync_calendar_auto()
            except Exception as e:
                logging.error(f"[CALENDAR] Fatal error: {e}")
            last_calendar_sync = time.time()

        first_run = False

        # Force garbage collection to prevent memory creeping over time
        gc.collect()

        # Sleep in short intervals to stay responsive
        logging.info(f"[AGENT] Next check in 60s...")
        time.sleep(60)


if __name__ == "__main__":
    main()
