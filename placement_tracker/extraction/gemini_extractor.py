import json
from google import genai
from google.genai import types
from placement_tracker.config import GEMINI_API_KEY
from placement_tracker.schema import PlacementRecord

# Initialize Gemini Client if key is provided (otherwise initialized locally)
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
    
BATCH_EMAIL_PROMPT = """
You are a university placement data extraction assistant.
Below are HTML bodies from MULTIPLE placement announcement emails, separated by the delimiter ---EMAIL_BREAK---.
Extract ALL student placement records from ALL emails and return a SINGLE flat JSON array.

Each element must match this schema exactly:
{schema}

Rules:
- The company name appears in the email body as a heading (e.g., "Scry offers" → company_name = "Scry").
- The HTML table contains Roll No and Full Name. Map them to student_id and student_name.
- offer_type: Look for clues in the email.
    If the email mentions "PPO" or "Pre-Placement Offer" → "PPO"
    If it mentions "Full Time" or "FTE" or "full-time" → "FT"
    If it mentions "Internship" → "Intern"
    If it mentions both internship and full-time → "Intern+FT"
    Otherwise → "N/A"
- ctc: Look for CTC, salary, or package information in the email body.
    Convert INR figures to LPA (e.g., INR 22,00,000 = "22 LPA").
    If a monthly stipend, write e.g. "50K/month".
    If no salary/CTC info is found → "N/A"
- Return one JSON object per student row in the table.
- Return [] if no placement records can be found.
- Never hallucinate values. If uncertain, use "N/A".

EMAILS:
{emails_block}
"""

EMAIL_PROMPT = """
You are a university placement data extraction assistant.
The following is the HTML body of an email sent by a placement cell.
Extract ALL student placement records from it.

Return ONLY a valid JSON array. Each element must match this schema exactly:
{schema}

Rules:
- The company name appears in the email body as a heading (e.g., "Scry offers" → company_name = "Scry").
- Infer status from context: "offers" or "selected" → "Offered", "shortlisted" → "Shortlisted",
  "interview" → "Interviewing", "rejected" → "Rejected", otherwise → "Applied".
- The HTML table contains Roll No and Full Name. Map them to student_id and student_name.
- offer_type: Look for clues in the email.
    If the email mentions "PPO" or "Pre-Placement Offer" → "PPO"
    If it mentions "Full Time" or "FTE" or "full-time" → "FT"
    If it mentions "Internship" → "Intern"
    If it mentions both internship and full-time → "Intern+FT"
    Otherwise → "N/A"
- ctc: Look for CTC, salary, or package information in the email body.
    Convert INR figures to LPA (e.g., INR 22,00,000 = "22 LPA").
    If a monthly stipend, write e.g. "50K/month".
    If no salary/CTC info is found → "N/A"
- The email_date will be injected by the caller, so set email_date = "N/A".
- Return one JSON object per student row in the table.
- Return [] if no placement records can be found.
- Never hallucinate values. If uncertain, use "N/A".

EMAIL HTML:
{raw_html}
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
    Sends ALL emails to Gemini in a SINGLE call and returns a list of
    dicts: {'records': [PlacementRecord...], 'date': str}.
    emails: list of {'raw_html': str, 'date': str, 'uid': str}
    """
    if not client:
        raise ValueError("GEMINI_API_KEY is not set.")
    if not emails:
        return []

    schema_json = PlacementRecord.schema_json()
    
    # Build a combined block with per-email separators
    # Each section is: ---EMAIL_BREAK--- followed by metadata comment then the HTML
    parts = []
    for i, e in enumerate(emails):
        parts.append(f"<!-- EMAIL {i+1} | DATE: {e.get('date', 'N/A')} -->\n{e.get('raw_html', '')}")
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
                # Rename offer_date → email_date if model used old field name
                if "offer_date" in item and "email_date" not in item:
                    item["email_date"] = item.pop("offer_date")
                records.append(PlacementRecord(**item))
            except Exception as e:
                print(f"Validation error in batch item: {e}")
        return records
    except Exception as e:
        print(f"Error in batch email extraction: {e}")
        return []


def extract_from_email(raw_html: str) -> list[PlacementRecord]:
    """Extracts a list of PlacementRecord from email HTML using Gemini."""
    if not client:
        raise ValueError("GEMINI_API_KEY is not set.")
        
    schema_json = PlacementRecord.schema_json()
    prompt = EMAIL_PROMPT.format(schema=schema_json, raw_html=raw_html)
    
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
            # If the model returns a single dict instead of a list, wrap it
            data = [data]
            
        records = []
        for item in data:
            try:
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
