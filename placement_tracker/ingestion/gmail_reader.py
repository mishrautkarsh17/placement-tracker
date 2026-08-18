import imaplib
import email
from email.header import decode_header
import logging
from bs4 import BeautifulSoup
from placement_tracker.config import GMAIL_USER, GMAIL_APP_PASSWORD

def get_email_body_html(msg) -> str:
    """Extract HTML body from the email message."""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if "text/html" in content_type:
                try:
                    return part.get_payload(decode=True).decode()
                except UnicodeDecodeError:
                    return part.get_payload(decode=True).decode('latin-1')
    else:
        content_type = msg.get_content_type()
        if "text/html" in content_type:
            try:
                return msg.get_payload(decode=True).decode()
            except UnicodeDecodeError:
                return msg.get_payload(decode=True).decode('latin-1')
    return ""

def fetch_recent_offers(since_date_str: str) -> list[dict]:
    """
    Connects to Gmail and fetches emails from placement cell since a specific date.
    Returns a list of dictionaries with raw HTML.
    """
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        logging.error("Gmail credentials not configured.")
        return []
        
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        mail.select("inbox")
        
        # Search for emails from the placement cell since the given date
        search_criteria = f'(FROM "placement@iiitd.ac.in" SINCE "{since_date_str}")'
        status, messages = mail.search(None, search_criteria)
        
        if status != 'OK' or not messages[0]:
            logging.info("No recent emails found.")
            return []
            
        email_uids = messages[0].split()
        results = []
        logging.info(f"Found {len(email_uids)} recent emails. Fetching...")
        
        for email_uid in email_uids:
            try:
                # Fetch the email body
                res, msg_data = mail.fetch(email_uid, '(RFC822)')
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        
                        subject, encoding = decode_header(msg["Subject"])[0]
                        if isinstance(subject, bytes):
                            subject = subject.decode(encoding if encoding else "utf-8")
                            
                        from email.utils import parsedate_to_datetime
                        date_str = msg.get("Date", "")
                        try:
                            parsed_date = parsedate_to_datetime(date_str).strftime("%Y-%m-%d %H:%M:%S")
                        except Exception:
                            parsed_date = "N/A"
                            
                        raw_html = get_email_body_html(msg)
                        if not raw_html:
                            # Try getting plain text if html is missing
                            if msg.is_multipart():
                                for part in msg.walk():
                                    if part.get_content_type() == "text/plain":
                                        raw_html = part.get_payload(decode=True).decode(errors='ignore')
                            else:
                                raw_html = msg.get_payload(decode=True).decode(errors='ignore')
                                
                        results.append({
                            "raw_html": raw_html,
                            "subject": subject,
                            "uid": email_uid.decode(),
                            "date": parsed_date
                        })
                        
                # We no longer mark emails as seen (\\Seen) to not mess with the user's inbox
            except Exception as e:
                logging.error(f"Error processing email UID {email_uid}: {e}")
                
        mail.logout()
        return results
        
    except Exception as e:
        logging.error(f"IMAP connection error: {e}")
        return []

def fetch_historical_offers(subject_keyword: str) -> list[dict]:
    """
    Connects to Gmail and fetches ALL emails (Seen or Unseen) from placement cell
    that match a specific subject keyword.
    """
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        logging.error("Gmail credentials not configured.")
        return []
        
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        mail.select("inbox")
        
        # Search for emails from the placement cell matching the subject
        search_criteria = f'(FROM "placement@iiitd.ac.in" SUBJECT "{subject_keyword}")'
        status, messages = mail.search(None, search_criteria)
        
        if status != 'OK' or not messages[0]:
            logging.info("No historical emails found matching the criteria.")
            return []
            
        email_uids = messages[0].split()
        results = []
        logging.info(f"Found {len(email_uids)} historical emails. Fetching...")
        
        for email_uid in email_uids:
            try:
                res, msg_data = mail.fetch(email_uid, '(RFC822)')
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        
                        subject, encoding = decode_header(msg["Subject"])[0]
                        if isinstance(subject, bytes):
                            subject = subject.decode(encoding if encoding else "utf-8")
                            
                        from email.utils import parsedate_to_datetime
                        date_str = msg.get("Date", "")
                        try:
                            parsed_date = parsedate_to_datetime(date_str).strftime("%Y-%m-%d %H:%M:%S")
                        except Exception:
                            parsed_date = "N/A"
                            
                        raw_html = get_email_body_html(msg)
                        if not raw_html:
                            if msg.is_multipart():
                                for part in msg.walk():
                                    if part.get_content_type() == "text/plain":
                                        raw_html = part.get_payload(decode=True).decode(errors='ignore')
                            else:
                                raw_html = msg.get_payload(decode=True).decode(errors='ignore')
                                
                        results.append({
                            "raw_html": raw_html,
                            "subject": subject,
                            "uid": email_uid.decode(),
                            "date": parsed_date
                        })
            except Exception as e:
                logging.error(f"Error processing historical email UID {email_uid}: {e}")
                
        mail.logout()
        return results
        
    except Exception as e:
        logging.error(f"IMAP connection error: {e}")
        return []


def fetch_shortlisted_students(since_date_str: str) -> list[dict]:
    """
    Fetches emails from the placement cell that contain interview shortlists.
    Parses the HTML table of Roll No + Full Name and returns a list of:
    {'company': str, 'roll_no': str, 'name': str, 'date': str}
    """
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        logging.error("Gmail credentials not configured.")
        return []

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        mail.select("inbox")

        search_criteria = f'(FROM "placement@iiitd.ac.in" SINCE "{since_date_str}")'
        status, messages = mail.search(None, search_criteria)

        if status != "OK" or not messages[0]:
            logging.info("No shortlist emails found.")
            return []

        email_uids = messages[0].split()
        results = []

        for email_uid in email_uids:
            try:
                res, msg_data = mail.fetch(email_uid, "(RFC822)")
                for response_part in msg_data:
                    if not isinstance(response_part, tuple):
                        continue
                    msg = email.message_from_bytes(response_part[1])

                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding if encoding else "utf-8")

                    body_text = get_email_body_html(msg)
                    body_lower = body_text.lower()
                    subject_lower = subject.lower()

                    # Only process emails that look like interview shortlists
                    is_shortlist = (
                        "shortlist" in subject_lower
                        or "interview" in subject_lower
                        or "shortlist for the interview" in body_lower
                    )
                    if not is_shortlist:
                        continue

                    # Extract company from subject line
                    company = "Unknown"
                    for separator in ["|", "-", "–", ":"]:
                        if separator in subject:
                            company = subject.split(separator)[0].strip()
                            break
                    if company == "Unknown":
                        company = subject.strip()

                    from email.utils import parsedate_to_datetime
                    date_str = msg.get("Date", "")
                    try:
                        parsed_date = parsedate_to_datetime(date_str).strftime("%Y-%m-%d")
                    except Exception:
                        parsed_date = "N/A"

                    # Parse HTML table rows for Roll No + Full Name
                    soup = BeautifulSoup(body_text, "html.parser")
                    for row in soup.find_all("tr"):
                        cells = row.find_all("td")
                        if len(cells) >= 2:
                            roll_no = cells[0].get_text(strip=True)
                            full_name = cells[1].get_text(strip=True)
                            # Skip header rows
                            if roll_no.lower() in ("roll no", "roll number", "rollno", ""):
                                continue
                            results.append({
                                "company": company,
                                "roll_no": roll_no,
                                "name": full_name,
                                "date": parsed_date,
                            })

            except Exception as e:
                logging.error(f"Error processing shortlist email UID {email_uid}: {e}")

        mail.logout()
        logging.info(f"Found {len(results)} shortlisted student entries from emails.")
        return results

    except Exception as e:
        logging.error(f"IMAP connection error in fetch_shortlisted_students: {e}")
        return []
