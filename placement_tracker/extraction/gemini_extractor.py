import json
from google import genai
from google.genai import types
from placement_tracker.config import GEMINI_API_KEY
from placement_tracker.schema import PlacementRecord

# Initialize Gemini Client if key is provided (otherwise initialized locally)
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
    
BATCH_EMAIL_PROMPT = """
You are a university placement data extraction assistant.
Below are emails from a university placement cell, each separated by ---EMAIL_BREAK---.
Each email is preceded by its SUBJECT line and DATE metadata.
Extract ALL student placement records from ALL emails and return a SINGLE flat JSON array.

Each element must match this schema exactly:
{schema}

Rules:
- company_name: Extract from the Subject line first (e.g., Subject: "Microsoft | Shortlist" → "Microsoft", Subject: "Scry Offers" → "Scry"). Only look in the body if the subject has no company name.
- The HTML table in the body contains Roll No and Full Name columns. Map Roll No → student_id, Full Name → student_name.
- status: Infer from the subject/body:
    Subject/body contains "shortlist for the interview" or "interview shortlist" → "Interviewing"
    Contains "offers" or "selected" or "offered" → "Offered"
    Contains "shortlisted" (but NOT interview) → "Shortlisted"
    Contains "rejected" → "Rejected"
    Otherwise → "Applied"
- offer_type:
    Contains "PPO" or "Pre-Placement Offer" → "PPO"
    Contains "Full Time" or "FTE" or "full-time" → "FT"
    Contains "Internship" → "Intern"
    Contains both internship and full-time → "Intern+FT"
    Otherwise → "N/A"
- ctc: Extract CTC/salary/package. Convert INR to LPA (e.g., INR 22,00,000 = "22 LPA"). Monthly stipend → "50K/month". If absent → "N/A".
- IMPORTANT: If the email has no HTML table with student Roll Numbers, it is NOT a placement record email. Return [] for that email — do NOT create rows with Unknown values.
- Return one JSON object per student row in the table.
- Never hallucinate. Use "N/A" for genuinely missing fields.

EMAILS:
{emails_block}
"""

EMAIL_PROMPT = """
You are a university placement data extraction assistant.
Below is a single email from a university placement cell.
Its SUBJECT line and DATE are provided at the top, followed by the HTML body.
Extract ALL student placement records from it.

Return ONLY a valid JSON array. Each element must match this schema exactly:
{schema}

Rules:
- company_name: Extract from the Subject line first (e.g., "Microsoft | Shortlist" → "Microsoft"). Only look in the body if the subject has no company name.
- The HTML table in the body contains Roll No and Full Name columns. Map Roll No → student_id, Full Name → student_name.
- status: Infer from the subject/body:
    Subject/body contains "shortlist for the interview" or "interview shortlist" → "Interviewing"
    Contains "offers" or "selected" or "offered" → "Offered"
    Contains "shortlisted" (but NOT interview) → "Shortlisted"
    Contains "rejected" → "Rejected"
    Otherwise → "Applied"
- offer_type:
    Contains "PPO" or "Pre-Placement Offer" → "PPO"
    Contains "Full Time" or "FTE" or "full-time" → "FT"
    Contains "Internship" → "Intern"
    Contains both internship and full-time → "Intern+FT"
    Otherwise → "N/A"
- ctc: Extract CTC/salary. Convert INR to LPA. Stipend → "50K/month". If absent → "N/A".
- IMPORTANT: If the email body has no HTML table with student Roll Numbers, this is NOT a placement record email. Return [].
- Return one JSON object per student row in the table.
- Never hallucinate. Use "N/A" for genuinely missing fields.

EMAIL:
{email_block}
"""

PORTAL_PROMPT = """
You are a university placement data extraction assistant.
The following is raw text scraped from a student's placement portal (either applications or opportunities).

The text contains one or many job/opportunity cards. The exact format varies, but they usually contain the Company Name, Job Title, CTC/Stipend details, and Job Type/Status.

Extract ALL job/opportunity cards and return a JSON array where each element matches this schema:
{schema}

Rules:
- company_name: Extract the name of the company hiring.
- offer_type: Look for Job type tags:
    "Internship + Full-Time" or "Internship+ Full time" → "Intern+FT"
    "Full-Time" or "Full time" → "FT"
    "Internship" only → "Intern"
    If unclear → "N/A"
- ctc: Extract CTC or Stipend. Convert INR figures to LPA (e.g., INR 1,00,000 = 1 LPA; INR 22,00,000 = "22 LPA"). For stipends, write "50K/month". If absent → "N/A"
- status: Extract application status if available (e.g., "Registered" → "Applied", "Shortlisted", "Offered"). If not an applications page, set to "N/A".
- student_name: set to "dummy" (will be overwritten by the caller)
- student_id: set to "dummy" (will be overwritten by the caller)
- Never hallucinate. Use "N/A" for any missing field.
- Return [] if no cards or opportunities can be found.

RAW PAGE TEXT:
{raw_card_text}
"""

def extract_batch_from_emails(emails: list[dict]) -> list[dict]:
    """
    Sends ALL emails to Gemini in a SINGLE call and returns a list of PlacementRecord objects.
    emails: list of {'raw_html': str, 'subject': str, 'date': str, 'uid': str}
    """
    if not client:
        raise ValueError("GEMINI_API_KEY is not set.")
    if not emails:
        return []

    schema_json = PlacementRecord.schema_json()
    
    # Build a combined block — now includes Subject line for company name extraction
    parts = []
    for i, e in enumerate(emails):
        subject = e.get('subject', 'No Subject')
        date = e.get('date', 'N/A')
        body = e.get('raw_html', '')
        parts.append(f"<!-- EMAIL {i+1} | SUBJECT: {subject} | DATE: {date} -->\n{body}")
    emails_block = "\n---EMAIL_BREAK---\n".join(parts)
    
    prompt = BATCH_EMAIL_PROMPT.format(schema=schema_json, emails_block=emails_block)
    
    try:
        response = client.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            )
        )
        data = json.loads(response.text)
        if not isinstance(data, list):
            data = [data] if data else []

        records = []
        for item in data:
            try:
                # Skip rows that still have placeholder Unknown/empty values for key fields
                if item.get("company_name", "Unknown") == "Unknown" and item.get("student_id", "") == "":
                    continue
                if "offer_date" in item and "email_date" not in item:
                    item["email_date"] = item.pop("offer_date")
                records.append(PlacementRecord(**item))
            except Exception as e:
                print(f"Validation error in batch item: {e}")
        return records
    except Exception as e:
        print(f"Error in batch email extraction: {e}")
        return []


def extract_from_email(raw_html: str, subject: str = "") -> list[PlacementRecord]:
    """Extracts a list of PlacementRecord from email HTML + subject using Gemini."""
    if not client:
        raise ValueError("GEMINI_API_KEY is not set.")
        
    schema_json = PlacementRecord.schema_json()
    email_block = f"SUBJECT: {subject}\n\nBODY:\n{raw_html}"
    prompt = EMAIL_PROMPT.format(schema=schema_json, email_block=email_block)
    
    try:
        response = client.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            )
        )
        data = json.loads(response.text)
        
        if not isinstance(data, list):
            data = [data]
            
        records = []
        for item in data:
            try:
                if item.get("company_name", "Unknown") == "Unknown" and item.get("student_id", "") == "":
                    continue
                records.append(PlacementRecord(**item))
            except Exception as e:
                print(f"Validation error for item in email: {e}")
                
        return records
    except Exception as e:
        print(f"Error extracting from email: {e}")
        return []

def extract_from_portal(raw_card_text: str, student_name: str, student_id: str) -> list[PlacementRecord]:
    """Extracts PlacementRecord(s) from pod.ai card/page text using Gemini. Returns a list."""
    if not client:
        raise ValueError("GEMINI_API_KEY is not set.")
        
    schema_json = PlacementRecord.schema_json()
    prompt = PORTAL_PROMPT.format(schema=schema_json, raw_card_text=raw_card_text)
    
    try:
        response = client.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            )
        )
        data = json.loads(response.text)
        
        # Normalise: always a list
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            return []

        records = []
        for item in data:
            try:
                # Override student info with what we know
                item["student_name"] = student_name
                item["student_id"] = student_id
                # Rename offer_date -> email_date if model used old field name
                if "offer_date" in item and "email_date" not in item:
                    item["email_date"] = item.pop("offer_date")
                records.append(PlacementRecord(**item))
            except Exception as e:
                print(f"Validation error for portal item: {e}")
        return records
    except Exception as e:
        print(f"Error extracting from portal card: {e}")
        return []
