import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import logging
import argparse
from placement_tracker.ingestion import gmail_reader
from placement_tracker.extraction import gemini_extractor
from placement_tracker.storage import sheets_client

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def sync_historical_data(subject_keyword: str):
    logging.info(f"Starting historical sync for emails with subject containing: '{subject_keyword}'")
    
    historical_emails = gmail_reader.fetch_historical_offers(subject_keyword)
    if not historical_emails:
        logging.info("No emails to process.")
        return
        
    total_records = 0
    
    for i, email_data in enumerate(historical_emails):
        logging.info(f"Processing email {i+1}/{len(historical_emails)}: {email_data['subject']}")
        try:
            records = gemini_extractor.extract_from_email(email_data["raw_html"])
            if records:
                sheets_client.upsert_offers(records)
                total_records += len(records)
                logging.info(f" -> Upserted {len(records)} records.")
            else:
                logging.info(" -> No placement records found in this email.")
        except Exception as e:
            logging.error(f"Error processing email {email_data.get('uid')}: {e}")
            
    logging.info(f"Historical sync complete! Total records inserted/updated: {total_records}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync historical placement offers from Gmail.")
    parser.add_argument("--subject", type=str, required=True, help="Subject keyword to search for (e.g., 'Selected for Full Time')")
    args = parser.parse_args()
    
    sync_historical_data(args.subject)
