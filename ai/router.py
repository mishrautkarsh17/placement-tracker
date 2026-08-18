from google import genai
from google.genai import types
import os
import json
import logging
from ai.prompts import SYSTEM_PROMPT

def get_gemini_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        try:
            import streamlit as st
            api_key = st.secrets.get("GEMINI_API_KEY")
        except Exception:
            pass
    
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in environment or secrets.")
        
    return genai.Client(api_key=api_key)

def route_query(user_message: str) -> dict:
    """
    Very simple heuristic router for MVP.
    Returns a dict with 'intent' and optional 'parameters'.
    Intents: DATA_QUERY, REASONING
    """
    msg_lower = user_message.lower()
    
    # Heuristics for deterministic searches
    if "show" in msg_lower and "companies" in msg_lower:
        return {"intent": "DATA_QUERY", "type": "companies_search"}
        
    if "above" in msg_lower and "lpa" in msg_lower:
        return {"intent": "DATA_QUERY", "type": "ctc_search"}
        
    # Default to reasoning
    return {"intent": "REASONING"}

def generate_copilot_response(user_message: str, context_data: dict) -> str:
    """Calls Gemini with the context data to answer the user's question."""
    try:
        client = get_gemini_client()
        
        # Format context data nicely
        context_str = json.dumps(context_data, indent=2)
        
        full_prompt = f"{SYSTEM_PROMPT}\n\nContext Data:\n{context_str}\n\nUser Question: {user_message}"
        
        response = client.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=full_prompt,
        )
        return response.text
    except Exception as e:
        logging.error(f"Gemini generation error: {e}")
        return "I'm having trouble connecting to my AI brain right now. Please try again later."


def generate_resume_recommendation(resume_text: str, active_companies: list[dict]) -> str:
    """
    Analyses the student's resume text against the list of active companies
    and returns a ranked list of best-fit companies with preparation tips.
    """
    try:
        client = get_gemini_client()

        companies_str = json.dumps(active_companies, indent=2)

        prompt = f"""You are an expert university placement advisor and career counselor.
A student has shared their resume and you have a list of companies currently recruiting on campus.

Analyse the student's skills, projects, and experience from the resume.
Then compare them against the companies currently hiring and provide personalised recommendations.

Format your response in clean Markdown like this:

### 🏆 Top Company Matches for You

For each top match (up to 5), use this format:
#### [Rank]. [Company Name] — [Match Score]%
**Why you're a great fit:** [2-3 sentences explaining which specific skills/projects from the resume match this company's typical requirements]
**Key prep areas:** [Bullet list of 3-4 specific topics to focus on]
**Estimated CTC:** [If available from context, otherwise omit]

---

### 📚 General Preparation Advice
[2-3 sentences of personalised advice based on gaps you observe]

---

STUDENT RESUME:
{resume_text}

ACTIVE COMPANIES ON CAMPUS:
{companies_str}
"""
        response = client.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=prompt,
        )
        return response.text
    except Exception as e:
        logging.error(f"Gemini resume recommendation error: {e}")
        return "I'm having trouble analysing your resume right now. Please try again later."
