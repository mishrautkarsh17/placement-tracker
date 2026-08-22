import logging
from placement_tracker.ingestion import gmail_reader, portal_scraper
from placement_tracker.extraction import gemini_extractor
from placement_tracker.storage import sheets_client

import os
import json
import time
from datetime import datetime, timedelta

STATE_FILE = ".sync_state.json"

def sync_offer_letters() -> dict:
    """
    Runs periodically to fetch recent emails using a date-based sync.
    Called by the background email watcher thread.
    """
    results = {"email_records": 0, "new_emails_found": 0, "errors": []}
    # 1. Read last sync date from Google Sheets
    last_sync_date_str = sheets_client.read_last_sync_time()
    
    # Default to 01-Jul-2026 if no state exists
    if not last_sync_date_str:
        last_sync_date_str = "01-Jul-2026 00:00:00"
        
    last_processed_time = datetime(2026, 7, 1)
    try:
        from dateutil import parser
        parsed_date = parser.parse(last_sync_date_str)
        last_processed_time = parsed_date
        imap_date_str = parsed_date.strftime("%d-%b-%Y")
    except Exception:
        # Fallback if parsing fails or dateutil not installed
        try:
            # Try exact format first
            parsed_date = datetime.strptime(last_sync_date_str, "%d-%b-%Y %H:%M:%S")
            last_processed_time = parsed_date
            imap_date_str = parsed_date.strftime("%d-%b-%Y")
        except Exception:
            try:
                # Try to handle common YYYY-MM-DD
                if "-" in last_sync_date_str and len(last_sync_date_str) >= 10:
                    parsed_date = datetime.strptime(last_sync_date_str[:10], "%Y-%m-%d")
                    last_processed_time = parsed_date
                    imap_date_str = parsed_date.strftime("%d-%b-%Y")
                else:
                    imap_date_str = "01-Jul-2026"
            except Exception:
                imap_date_str = "01-Jul-2026"

    logging.info(f"Syncing emails since {imap_date_str}")

    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
                if "last_email_time" in state:
                    state_time = datetime.fromisoformat(state["last_email_time"])
                    if state_time > last_processed_time:
                        last_processed_time = state_time
        except Exception as e:
            logging.error(f"Error reading state file: {e}")
    
    try:
        fetched_emails = gmail_reader.fetch_recent_offers(imap_date_str)
        
        # Filter out emails we've already processed
        recent_emails = []
        for e in fetched_emails:
            d_str = e.get("date")
            if d_str and d_str != "N/A":
                try:
                    d_obj = datetime.strptime(d_str, "%Y-%m-%d %H:%M:%S")
                    if d_obj > last_processed_time:
                        recent_emails.append(e)
                except ValueError:
                    # If date parsing fails, keep it just in case
                    recent_emails.append(e)
            else:
                recent_emails.append(e)
                
        results["new_emails_found"] = len(recent_emails)

        if recent_emails:
            BATCH_SIZE = 10  # Increased batch size to save on API requests (RPM) since we now parse text
            batches = [recent_emails[i:i+BATCH_SIZE] for i in range(0, len(recent_emails), BATCH_SIZE)]
            logging.info(f"Processing {len(recent_emails)} emails in {len(batches)} batch(es) of up to {BATCH_SIZE}...")
            
            all_success = True
            for batch_num, batch in enumerate(batches, 1):
                # Delay between batches to avoid Gemini rate limits
                if batch_num > 1:
                    logging.info(f"Waiting 20s before next batch to avoid rate limits...")
                    time.sleep(20)
                    
                logging.info(f"Batch {batch_num}/{len(batches)}: sending {len(batch)} emails to Gemini...")
                try:
                    batch_records = gemini_extractor.extract_batch_from_emails(batch)
                    if batch_records:
                        sheets_client.upsert_offers(batch_records)
                        results["email_records"] += len(batch_records)
                        
                        # Save state incrementally based on this batch's emails
                        try:
                            # Parse dates to find the latest in this batch
                            latest_date = None
                            for email in batch:
                                d_str = email.get("date")
                                if d_str and d_str != "N/A":
                                    try:
                                        d_obj = datetime.strptime(d_str, "%Y-%m-%d %H:%M:%S")
                                        if not latest_date or d_obj > latest_date:
                                            latest_date = d_obj
                                    except ValueError:
                                        pass
                            
                            if latest_date:
                                # Update sheet coarse date with exact time
                                new_sync_date = latest_date.strftime("%d-%b-%Y %H:%M:%S")
                                sheets_client.write_last_sync_time(new_sync_date)
                                
                                # Update exact time in state file
                                if latest_date > last_processed_time:
                                    last_processed_time = latest_date
                                    with open(STATE_FILE, "w") as f:
                                        json.dump({"last_email_time": last_processed_time.isoformat()}, f)
                                        
                                logging.info(f"State advanced incrementally to {new_sync_date}")
                        except Exception as e:
                            logging.error(f"Could not write incremental state file: {e}")
                            
                        logging.info(f"Batch {batch_num} done: upserted {len(batch_records)} records.")
                    else:
                        logging.warning(f"Batch {batch_num} returned no records.")
                        all_success = False
                except Exception as e:
                    err_msg = f"Batch {batch_num} failed: {e}"
                    logging.error(err_msg)
                    results["errors"].append(err_msg)
                    all_success = False

            # Only advance sheet state if ALL batches succeeded
            if results["email_records"] > 0:
                sync_timestamp = datetime.now().strftime("%d-%b-%Y %H:%M:%S")
                sheets_client.write_last_sync_time(sync_timestamp)
        
        # --- STEP 2: Detect interview shortlists directly from email tables ---
        try:
            shortlisted = gmail_reader.fetch_shortlisted_students(imap_date_str)
            if shortlisted:
                logging.info(f"Updating 'Interviewing' status for {len(shortlisted)} shortlisted entries.")
                sheets_client.update_interview_status(shortlisted)
                results["shortlist_updates"] = len(shortlisted)
        except Exception as e:
            logging.error(f"Failed to fetch shortlist emails: {e}")
            results["errors"].append(f"Shortlist detection failed: {e}")
            
    except Exception as e:
        results["errors"].append(f"Failed to fetch emails: {e}")
        
    return results

def sync_job_applications(pod_ai_username: str, pod_ai_password: str, progress_callback=None, student_name="dummy", student_id="dummy") -> dict:
    """
    Runs ON-DEMAND when the user clicks 'Refresh Applications' in Streamlit.
    Scrapes pod.ai, extracts structured data, upserts into the Sheet.
    """
    results = {"portal_records": 0, "errors": []}
    
    try:
        scraped_data = portal_scraper.scrape(pod_ai_username, pod_ai_password)
        
        if scraped_data:
            if progress_callback:
                progress_callback(1, 1)
                
            try:
                # Batch all cards into a single API call to avoid quota limits
                bulk_text = "\n--- NEXT CARD ---\n".join([c["raw_card_text"] for c in scraped_data])
                records = gemini_extractor.extract_from_portal(
                    bulk_text,
                    student_name=student_name,
                    student_id=student_id
                )
                if records:
                    sheets_client.upsert_applications(records)
                    sheets_client.enrich_offers_with_ctc(records)
                    results["portal_records"] += len(records)
            except Exception as e:
                err_msg = f"Error processing portal card: {e}"
                logging.error(err_msg)
                results["errors"].append(err_msg)
    except Exception as e:
        results["errors"].append(f"Failed to scrape portal: {e}")
        
    return results

def sync_global_opportunities(pod_ai_username: str, pod_ai_password: str) -> dict:
    """
    Runs ON-DEMAND to scrape the broader Opportunities page and backfill the Offers sheet with CTCs.
    Scrapes multiple views to maximize company coverage.
    """
    results = {"portal_records": 0, "errors": []}
    
    urls_to_scrape = [
        # Filtered opportunities (eligible)
        "https://iiitd.pod.ai/d/HjFzVC/opportunities/?eligibilityType=1&eligibilityType=2",
        # ALL opportunities (no filter) to catch companies not in the filtered view
        "https://iiitd.pod.ai/d/HjFzVC/opportunities/",
        # Applications page (user's own applications have CTC data too)
        None,  # None = default applications page
    ]
    
    all_scraped = []
    for url in urls_to_scrape:
        try:
            label = url if url else "Applications page"
            logging.info(f"Scraping: {label}")
            data = portal_scraper.scrape(pod_ai_username, pod_ai_password, target_url=url)
            logging.info(f"Got {len(data)} cards from {label}")
            all_scraped.extend(data)
        except Exception as e:
            err_msg = f"Failed to scrape {url}: {e}"
            logging.error(err_msg)
            results["errors"].append(err_msg)
    
    # Deduplicate cards by text content
    seen_texts = set()
    unique_scraped = []
    for card in all_scraped:
        text_key = card["raw_card_text"][:200]  # Use first 200 chars as key
        if text_key not in seen_texts:
            seen_texts.add(text_key)
            unique_scraped.append(card)
    
    logging.info(f"Total unique cards after dedup: {len(unique_scraped)} (from {len(all_scraped)} raw)")
    
    if unique_scraped:
        BATCH_SIZE = 20
        batches = [unique_scraped[i:i+BATCH_SIZE] for i in range(0, len(unique_scraped), BATCH_SIZE)]
        logging.info(f"Processing {len(unique_scraped)} opportunities in {len(batches)} batch(es) of {BATCH_SIZE}...")
        
        for batch_num, batch in enumerate(batches, 1):
            if batch_num > 1:
                logging.info(f"Waiting 20s before next opportunity batch to avoid rate limits...")
                time.sleep(20)
                
            try:
                bulk_text = "\n--- NEXT CARD ---\n".join([c["raw_card_text"] for c in batch])
                records = gemini_extractor.extract_from_portal(
                    bulk_text,
                    student_name="Global Sync",
                    student_id="N/A"
                )
                if records:
                    sheets_client.enrich_offers_with_ctc(records)
                    results["portal_records"] += len(records)
            except Exception as e:
                err_msg = f"Error processing opportunities batch {batch_num}: {e}"
                logging.error(err_msg)
                results["errors"].append(err_msg)
    
    return results
