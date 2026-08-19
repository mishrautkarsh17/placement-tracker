import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import streamlit as st
import logging

from placement_tracker.config import (
    GOOGLE_SHEET_ID, 
    COLLEGE_CALENDAR_SHEET_ID,
    CALENDAR_SHEET_TAB, 
    OFFERS_SHEET_TAB, 
    MTECH_OFFERS_SHEET_TAB,
    APPLICATIONS_SHEET_TAB,
    PRIVATE_SHEET_ID
)
from placement_tracker.schema import PlacementRecord
from placement_tracker.auth import get_user_credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def _get_client():
    """Internal function to get the gspread client. Works in Streamlit and GitHub Actions."""
    if not GOOGLE_SHEET_ID:
        raise ValueError("GOOGLE_SHEET_ID is not set.")
    
    creds = None
    
    # 1. Try Streamlit secrets
    try:
        if st.secrets and "gcp_service_account" in st.secrets:
            creds = Credentials.from_service_account_info(
                st.secrets["gcp_service_account"].to_dict(),
                scopes=SCOPES
            )
    except Exception:
        pass
    
    # 2. Try GOOGLE_APPLICATION_CREDENTIALS file (set by sync_runner.py)
    if not creds:
        import os
        sa_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if sa_path and os.path.exists(sa_path):
            try:
                creds = Credentials.from_service_account_file(sa_path, scopes=SCOPES)
            except Exception:
                pass
    
    # 3. Try GCP_SERVICE_ACCOUNT_JSON env var directly
    if not creds:
        import os, json
        sa_json = os.environ.get("GCP_SERVICE_ACCOUNT_JSON")
        if sa_json:
            try:
                creds = Credentials.from_service_account_info(json.loads(sa_json), scopes=SCOPES)
            except Exception:
                pass
    
    if creds:
        return gspread.authorize(creds)
    
    logging.error("Could not load Google Service Account credentials from any source.")
    return None

def _get_user_client():
    creds = get_user_credentials()
    if creds:
        return gspread.authorize(creds)
    return None

def _get_worksheet(tab_name: str, sheet_id: str = None):
    """Internal function to get a specific worksheet."""
    try:
        if not sheet_id:
            if tab_name == APPLICATIONS_SHEET_TAB:
                sheet_id = PRIVATE_SHEET_ID
            else:
                sheet_id = GOOGLE_SHEET_ID
                
        # Use service account for all sheets
        client = _get_client()
        if not client:
            return None
                
        sheet = client.open_by_key(sheet_id)
        
        # Case insensitive search
        for ws in sheet.worksheets():
            if ws.title.lower() == tab_name.lower():
                return ws
                
        logging.info(f"Worksheet '{tab_name}' not found, creating it...")
        return sheet.add_worksheet(title=tab_name, rows=1000, cols=10)
    except Exception as e:
        logging.error(f"Error opening/creating worksheet '{tab_name}': {e}")
        return None

# --- CALENDAR DATA ---

def read_calendar() -> pd.DataFrame:
    """Reads the global placement calendar (read-only for the app)."""
    worksheet = _get_worksheet(CALENDAR_SHEET_TAB)
    if not worksheet:
        return pd.DataFrame()
        
    try:
        # Fetch all values
        all_values = worksheet.get_all_values()
        
        if not all_values:
            return pd.DataFrame()
            
        header_idx = 0
        # Dynamically find the actual header row (skip junk/padding rows)
        for i, row in enumerate(all_values):
            clean_row = [str(c).strip().lower() for c in row]
            if any(h in clean_row for h in ["date", "company", "company name", "process"]):
                header_idx = i
                break
                
        if len(all_values) > header_idx:
            headers = all_values[header_idx]
            
            # Ensure no duplicate column names (Pandas/Arrow hates duplicates like '')
            seen = {}
            unique_headers = []
            for h in headers:
                if h in seen:
                    seen[h] += 1
                    unique_headers.append(f"{h}_{seen[h]}")
                else:
                    seen[h] = 0
                    unique_headers.append(h)
                    
            data = all_values[header_idx+1:] if len(all_values) > header_idx + 1 else []
            df = pd.DataFrame(data, columns=unique_headers)
            
            # Clean up empty rows
            df = df.dropna(how='all')
            if not df.empty and df.shape[1] > 0:
                df = df[df.iloc[:, 0].astype(str).str.strip() != ""]
            return df
        return pd.DataFrame()
    except Exception as e:
        logging.error(f"Error reading calendar: {e}")
        return pd.DataFrame()

def sync_college_calendar():
    """Reads college calendar using User OAuth and writes to local Google Sheet."""
    if not COLLEGE_CALENDAR_SHEET_ID:
        return {"error": "COLLEGE_CALENDAR_SHEET_ID is not configured."}
        
    creds = get_user_credentials()
    if not creds:
        return {"error": "User OAuth authentication failed or was cancelled."}
        
    # Read the college sheet
    try:
        user_client = gspread.authorize(creds)
        college_sheet = user_client.open_by_key(COLLEGE_CALENDAR_SHEET_ID)
        college_ws = college_sheet.get_worksheet(0) # First tab
        
        all_values = college_ws.get_all_values()
        
        if not all_values:
            return {"error": "College calendar is empty."}
            
        # Write to our local sheet
        local_ws = _get_worksheet(CALENDAR_SHEET_TAB)
        if not local_ws:
            return {"error": "Could not access local Calendar sheet."}
            
        # We replace the entire content of the local Calendar tab
        local_ws.clear()
        
        # Batch update
        local_ws.update(values=all_values, range_name="A1")
        
        return {"success": True, "rows": len(all_values)}
    except Exception as e:
        logging.error(f"Error syncing college calendar: {e}")
        return {"error": str(e)}

# --- OFFERS DATA ---

OFFERS_HEADERS = ["student_name", "student_id", "company_name", "offer_type", "ctc"]
APPLICATIONS_HEADERS = ["student_name", "student_id", "company_name", "offer_type", "ctc", "status"]

def _ensure_headers(worksheet, headers: list):
    """Ensures row 1 of the worksheet has the correct headers. Fixes if needed."""
    try:
        row1 = worksheet.row_values(1)
        if row1 != headers:
            worksheet.update(values=[headers], range_name="A1")
            logging.info(f"Fixed headers in '{worksheet.title}'")
    except Exception as e:
        logging.error(f"Could not verify/fix headers: {e}")

def _get_all_offers(tab_name=OFFERS_SHEET_TAB) -> tuple[list[dict], dict[str, int]]:
    """Returns raw records and a dedup_map (key -> row_index) for the specified offers tab."""
    worksheet = _get_worksheet(tab_name)
    if not worksheet:
        return [], {}

    _ensure_headers(worksheet, OFFERS_HEADERS)
    try:
        records = worksheet.get_all_records(expected_headers=OFFERS_HEADERS)
    except Exception as e:
        logging.error(f"Error getting records for {tab_name}: {e}")
        records = []
    dedup_map = {}
    for idx, rec in enumerate(records):
        row_idx = idx + 2
        student_id = str(rec.get("student_id", "")).strip().lower()
        company = str(rec.get("company_name", "")).strip().lower()
        if student_id and student_id not in ("", "0", "none"):
            key = f"{student_id}::{company}"
        else:
            student_name = str(rec.get("student_name", "")).strip().lower()
            key = f"{student_name}::{company}"
        dedup_map[key] = row_idx
    return records, dedup_map

def read_offers() -> pd.DataFrame:
    """Reads all offers into a DataFrame."""
    records, _ = _get_all_offers()
    df = pd.DataFrame(records)
    if not df.empty:
        df = df.astype(str)
    return df

def _upsert_offers_to_tab(records: list[PlacementRecord], tab_name: str):
    """Internal function to upsert records into a specific offers tab."""
    if not records:
        return
        
    worksheet = _get_worksheet(tab_name)
    if not worksheet:
        return
        
    existing_records, dedup_map = _get_all_offers(tab_name)
    
    # Build lookup to merge and preserve existing non-N/A values
    existing_map = {}
    for r in existing_records:
        sid = str(r.get("student_id", "")).strip().lower()
        comp = str(r.get("company_name", "")).strip().lower()
        if sid and sid not in ("", "0", "none"):
            k = f"{sid}::{comp}"
        else:
            sname = str(r.get("student_name", "")).strip().lower()
            k = f"{sname}::{comp}"
        existing_map[k] = r
    
    new_rows = []
    updates = []
    
    for record in records:
        key = record.dedup_key
        row_data = record.to_sheet_row()[:5]  # Exclude status for Offers sheet
        
        if key in dedup_map:
            row_idx = dedup_map[key]
            
            # Merge: don't overwrite valid CTC/offer_type with N/A
            if key in existing_map:
                existing = existing_map[key]
                # row_data[3] = offer_type, row_data[4] = ctc
                existing_offer = existing.get("offer_type", "")
                if row_data[3] == "PPO":
                    pass # Always trust PPO from email
                elif existing_offer not in ("N/A", ""):
                    row_data[3] = existing_offer # Keep existing (likely from Pod.ai)

                if row_data[4] in ("N/A", "") and existing.get("ctc", "") not in ("N/A", ""):
                    row_data[4] = existing.get("ctc", "")
            
            updates.append({
                'range': f"A{row_idx}:{chr(65+len(row_data)-1)}{row_idx}",
                'values': [row_data]
            })
        else:
            new_rows.append(row_data)
            
    if updates:
        worksheet.batch_update(updates)
    if new_rows:
        # Write headers if empty
        if len(dedup_map) == 0:
            worksheet.insert_row(OFFERS_HEADERS, index=1)
        # Append new rows at the bottom
        worksheet.append_rows(new_rows, insert_data_option='INSERT_ROWS', table_range="A1")

def upsert_offers(records: list[PlacementRecord]):
    """Upserts a list of PlacementRecord into Offers or MTech offers based on student ID."""
    btech_records = []
    mtech_records = []
    
    for rec in records:
        sid = str(rec.student_id).strip().upper()
        if sid.startswith("MT"):
            mtech_records.append(rec)
        else:
            btech_records.append(rec)
            
    if btech_records:
        _upsert_offers_to_tab(btech_records, OFFERS_SHEET_TAB)
    if mtech_records:
        _upsert_offers_to_tab(mtech_records, MTECH_OFFERS_SHEET_TAB)

def enrich_offers_with_ctc(applications: list[PlacementRecord]):
    """
    Reads the Offers, MTech Offers, and Applications tabs and updates the 'ctc' and 'offer_type' columns
    if we found valid data for that company in the passed records.
    """
    enrichment_map = {}
    for app in applications:
        comp = str(app.company_name).strip().lower()
        if app.ctc and app.ctc != "N/A":
            enrichment_map[comp] = {"ctc": app.ctc, "offer_type": app.offer_type}

    if not enrichment_map:
        return

    import re
    
    def _normalize(name: str) -> str:
        """Normalize company name for fuzzy matching: lowercase, strip spaces/punctuation."""
        return re.sub(r'[^a-z0-9]', '', name.lower())
    
    def _company_matches(sheet_name: str, scraped_name: str) -> bool:
        """Check if two company names refer to the same company."""
        if not sheet_name or not scraped_name:
            return False
        
        s = sheet_name.strip().lower()
        e = scraped_name.strip().lower()
        
        # Exact match
        if s == e:
            return True
        
        # Normalized match (strips spaces, punctuation: "Policy Bazaar" == "Policybazaar")
        s_norm = _normalize(s)
        e_norm = _normalize(e)
        if len(s_norm) >= 2 and len(e_norm) >= 2:
            if s_norm == e_norm:
                return True
            # One is contained in the other (normalized)
            if len(s_norm) >= 3 and len(e_norm) >= 3:
                if s_norm in e_norm or e_norm in s_norm:
                    return True
        
        return False

    def _apply_enrichment(worksheet, records):
        if not records or not worksheet:
            return
        updates = []
        headers = worksheet.row_values(1)
        for idx, row in enumerate(records):
            row_idx = idx + 2
            comp = str(row.get("company_name", "")).strip().lower()
            
            best_match = None
            for e_comp, e_data in enrichment_map.items():
                if _company_matches(comp, e_comp):
                    best_match = e_data
                    break

            if best_match:
                current_ctc = str(row.get("ctc", ""))
                current_offer = str(row.get("offer_type", ""))
                
                new_ctc = best_match["ctc"]
                new_offer = best_match["offer_type"]
                
                needs_update = False
                if new_ctc and new_ctc != "N/A" and new_ctc != current_ctc:
                    needs_update = True
                    row["ctc"] = new_ctc
                if new_offer and new_offer != "N/A" and new_offer != current_offer:
                    if current_offer != "PPO":
                        needs_update = True
                        row["offer_type"] = new_offer
                    
                if needs_update:
                    row_data = [row.get(h, "") for h in headers]
                    updates.append({
                        'range': f"A{row_idx}:{chr(65+len(headers)-1)}{row_idx}",
                        'values': [row_data]
                    })
        if updates:
            worksheet.batch_update(updates)
            logging.info(f"Enriched {len(updates)} rows with CTC in {worksheet.title}")

    # Enrich Offers Sheets
    for tab_name in [OFFERS_SHEET_TAB, MTECH_OFFERS_SHEET_TAB]:
        ws = _get_worksheet(tab_name)
        if ws:
            records, _ = _get_all_offers(tab_name)
            _apply_enrichment(ws, records)

    # Enrich Applications Sheet
    app_ws = _get_worksheet(APPLICATIONS_SHEET_TAB)
    if app_ws:
        app_records, _ = _get_all_applications()
        _apply_enrichment(app_ws, app_records)

# --- APPLICATIONS DATA ---

def _get_all_applications() -> tuple[list[dict], dict[str, int]]:
    """Returns raw records and a dedup_map (key -> row_index) for Applications tab."""
    worksheet = _get_worksheet(APPLICATIONS_SHEET_TAB)
    if not worksheet:
        return [], {}
        
    try:
        _ensure_headers(worksheet, APPLICATIONS_HEADERS)
        records = worksheet.get_all_records(expected_headers=APPLICATIONS_HEADERS)
    except Exception as e:
        logging.error(f"Error getting records for applications: {e}")
        # Could be empty sheet
        records = []
        
    dedup_map = {}
    for idx, rec in enumerate(records):
        row_idx = idx + 2 
        student_id = str(rec.get("student_id", "")).strip()
        company = str(rec.get("company_name", "")).strip().lower()
        key = f"{student_id}::{company}"
        dedup_map[key] = row_idx
        
    return records, dedup_map

def read_applications(student_id: str) -> pd.DataFrame:
    """Reads applications filtered for a specific student."""
    records, _ = _get_all_applications()
    df = pd.DataFrame(records)
    if not df.empty:
        df = df.astype(str)
        if "student_id" in df.columns:
            return df[df["student_id"] == str(student_id)]
    return df

def upsert_applications(records: list[PlacementRecord]):
    """Upserts a list of PlacementRecord into the Applications tab."""
    if not records:
        return
        
    worksheet = _get_worksheet(APPLICATIONS_SHEET_TAB)
    if not worksheet:
        return
        
    existing_records, dedup_map = _get_all_applications()
    
    # Create lookup map to merge N/A values so we don't destroy existing valid data
    existing_map = {}
    for r in existing_records:
        sid = str(r.get("student_id", "")).strip().lower()
        comp = str(r.get("company_name", "")).strip().lower()
        k = f"{sid}::{comp}" if sid else f"{str(r.get('student_name', '')).strip().lower()}::{comp}"
        existing_map[k] = r
    
    new_rows = []
    updates = []
    
    for record in records:
        key = record.dedup_key
        row_data = record.to_sheet_row()
        
        if key in dedup_map:
            row_idx = dedup_map[key]
            
            # Merge with existing data to prevent overwriting valid CTC/Offer Type with N/A
            if key in existing_map:
                existing = existing_map[key]
                if row_data[3] in ("N/A", "") and existing.get("offer_type", "") not in ("N/A", ""):
                    row_data[3] = existing.get("offer_type", "")
                if row_data[4] in ("N/A", "") and existing.get("ctc", "") not in ("N/A", ""):
                    row_data[4] = existing.get("ctc", "")
                    
            updates.append({
                'range': f"A{row_idx}:{chr(65+len(row_data)-1)}{row_idx}",
                'values': [row_data]
            })
        else:
            new_rows.append(row_data)
            
    if updates:
        worksheet.batch_update(updates)
    if new_rows:
        if len(dedup_map) == 0:
            worksheet.insert_row(APPLICATIONS_HEADERS, index=1)
        # Append new rows at the bottom
        worksheet.append_rows(new_rows, insert_data_option='INSERT_ROWS', table_range="A1")


def write_last_sync_time(timestamp: str):
    """
    Writes a 'Last Updated' label and timestamp to cells J1:J2
    in the Offers sheet, outside the main data table.
    """
    for tab_name in [OFFERS_SHEET_TAB, MTECH_OFFERS_SHEET_TAB]:
        worksheet = _get_worksheet(tab_name)
        if not worksheet:
            continue
        try:
            worksheet.update(values=[["Last Updated"], [timestamp]], range_name="J1")
        except Exception as e:
            logging.error(f"Error writing last sync time to {tab_name}: {e}")

def read_last_sync_time() -> str:
    """Reads the last sync timestamp from cell J2 of the Offers sheet."""
    worksheet = _get_worksheet(OFFERS_SHEET_TAB)
    if not worksheet:
        return None
    try:
        val = worksheet.acell("J2").value
        if val and len(val) > 4:
            return val
    except Exception as e:
        logging.error(f"Error reading last sync time: {e}")
    return None

def update_interview_status(shortlisted: list[dict]):
    """
    Given a list of {'company': str, 'roll_no': str} dicts parsed from
    placement shortlist emails, sets status = 'Interviewing' in the 
    Applications sheet for matching student + company combinations.
    Also adds new rows if the student+company combo doesn't exist yet.
    """
    if not shortlisted:
        return

    worksheet = _get_worksheet(APPLICATIONS_SHEET_TAB)
    if not worksheet:
        return

    existing_records, dedup_map = _get_all_applications()

    updates = []
    new_rows = []

    for entry in shortlisted:
        roll_no = str(entry.get("roll_no", "")).strip()
        company = str(entry.get("company", "")).strip().lower()
        name = str(entry.get("name", "")).strip()
        date = str(entry.get("date", "")).strip()

        if not roll_no or not company:
            continue

        key = f"{roll_no.lower()}::{company}"
        if key in dedup_map:
            row_idx = dedup_map[key]
            # Update only the status column (col F = index 6)
            updates.append({
                "range": f"F{row_idx}",
                "values": [["Interviewing"]]
            })
            logging.info(f"Marking {roll_no} at {company} as Interviewing (row {row_idx})")
        else:
            # Add a new row for this shortlist entry
            new_rows.append([name, roll_no, entry.get("company", ""), "N/A", "N/A", "Interviewing"])
            logging.info(f"Adding new Interviewing row for {roll_no} at {company}")

    if updates:
        worksheet.batch_update(updates)
        logging.info(f"Updated {len(updates)} rows to Interviewing status.")
    if new_rows:
        if not existing_records:
            worksheet.insert_row(APPLICATIONS_HEADERS, index=1)
        worksheet.append_rows(new_rows, insert_data_option='INSERT_ROWS', table_range="A1")
        logging.info(f"Inserted {len(new_rows)} new Interviewing rows.")

def clear_all_offers():
    """Clears all data from Offers and MTech Offers tabs, and resets the sync state."""
    for tab_name in [OFFERS_SHEET_TAB, MTECH_OFFERS_SHEET_TAB]:
        ws = _get_worksheet(tab_name)
        if ws:
            try:
                # Keep headers (row 1), clear from row 2 downwards
                ws.batch_clear(["A2:Z1000"])
            except Exception as e:
                logging.error(f"Error clearing tab {tab_name}: {e}")
                
    # Reset last sync time to 1st July 2026
    write_last_sync_time("01-Jul-2026 00:00:00")
    
    # Also delete the local sync state file if it exists
    import os
    state_file = os.path.join(os.path.dirname(__file__), '..', '..', '.sync_state.json')
    if os.path.exists(state_file):
        try:
            os.remove(state_file)
        except Exception:
            pass
    return {"success": True, "message": "Offers cleared and sync reset to 1st July 2026"}
