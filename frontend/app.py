import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime
import requests

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from config import (
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI,
    POD_AI_USERNAME, POD_AI_PASSWORD
)
from auth import get_user_profile, get_oauth_url, exchange_code_for_token, get_user_credentials

API_URL = st.secrets.get("API_URL", "http://localhost:8000/api")

# --- CACHED DATA FETCHERS ---
# This prevents the app from re-fetching from the network on every button click
@st.cache_data(ttl=300, show_spinner=False)
def fetch_daily_brief(roll_no):
    try:
        res = requests.get(f"{API_URL}/daily-brief/{roll_no}")
        return res.json().get("brief", "Could not generate brief.")
    except Exception as e:
        return f"Failed to load daily brief: {e}"

@st.cache_data(ttl=300, show_spinner=False)
def fetch_calendar():
    try:
        req = requests.get(f"{API_URL}/calendar")
        return pd.DataFrame(req.json().get("data", []))
    except Exception as e:
        st.error(f"Failed to fetch calendar from API: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def fetch_analytics():
    try:
        req = requests.get(f"{API_URL}/analytics")
        return req.json()
    except Exception as e:
        st.error(f"Failed to fetch analytics from API: {e}")
        return {}

@st.cache_data(ttl=300, show_spinner=False)
def fetch_offers():
    try:
        req = requests.get(f"{API_URL}/offers")
        return pd.DataFrame(req.json().get("data", []))
    except Exception as e:
        st.error(f"Failed to fetch offers from API: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def fetch_applications(roll_no):
    try:
        req = requests.get(f"{API_URL}/applications/{roll_no}")
        return pd.DataFrame(req.json().get("data", []))
    except Exception as e:
        st.error(f"Failed to fetch applications from API: {e}")
        return pd.DataFrame()


# --- PAGE CONFIG ---
st.set_page_config(page_title="AI Placement Tracker", page_icon="🎓", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
<style>
    /* Modern minimalist font */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    /* Clean up the top padding and header */
    .block-container {
        padding-top: 2rem !important;
    }
    
    /* Style metrics to look like cards */
    [data-testid="stMetric"] {
        background-color: #1E1E2F;
        border-radius: 12px;
        padding: 1.2rem;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        border: 1px solid #2D2D44;
        transition: transform 0.2s;
    }
    [data-testid="stMetric"]:hover {
        transform: translateY(-2px);
    }
    [data-testid="stMetricValue"] {
        color: #4ECDC4 !important;
        font-weight: 700 !important;
    }
    
    /* Beautiful gradients for primary buttons */
    .stButton > button {
        background: linear-gradient(135deg, #FF6B6B 0%, #FF8E53 100%);
        color: white;
        border: none;
        border-radius: 8px;
        font-weight: 600;
        transition: opacity 0.2s;
    }
    .stButton > button:hover {
        opacity: 0.9;
        color: white;
        border: none;
    }
    
    /* Style the daily brief expander to look premium */
    .streamlit-expanderHeader {
        background-color: #1E1E2F;
        border-radius: 8px;
        font-weight: 600;
    }
    
    /* Chat message styling */
    [data-testid="stChatMessage"] {
        background-color: #1a1a24;
        border-radius: 10px;
        padding: 1rem;
        margin-bottom: 1rem;
        border: 1px solid #2D2D44;
    }
</style>
""", unsafe_allow_html=True)


# --- USER PROFILE ---
# Since you are the only user running this locally, we can skip OAuth completely!
if 'roll_no' not in st.session_state or 'name' not in st.session_state:
    st.title("🎓 Welcome to Placement Tracker")
    st.write("Please authenticate with your IIITD Google account to securely load your dashboard.")
    
    # Check for OAuth callback code in URL
    if "code" in st.query_params:
        with st.spinner("Authenticating..."):
            if exchange_code_for_token(st.query_params["code"]):
                st.query_params.clear()
            else:
                st.error("Authentication failed. Please try again.")
                
    # If we have valid credentials, fetch profile
    creds = get_user_credentials()
    if creds and creds.valid:
        with st.spinner("Loading profile..."):
            profile = get_user_profile()
            if profile:
                st.session_state['name'] = profile.get("name", "Unknown")
                email = profile.get("email", "")
                
                # Extract roll number from email (e.g., utkarsh23571@iiitd.ac.in -> 23571)
                roll_no = "".join(filter(str.isdigit, email))
                st.session_state['roll_no'] = roll_no
                st.rerun()
            else:
                st.error("Could not fetch profile information.")
    else:
        # Show login button
        st.link_button("Login with Google", get_oauth_url(), type="primary")
                
    st.write("---")
    st.write("If Google login fails, you can manually enter your details below (for testing only):")
    with st.form("profile_form"):
        name_input = st.text_input("Full Name")
        roll_input = st.text_input("Roll Number")
        if st.form_submit_button("Enter Dashboard Manually"):
            if name_input and roll_input:
                st.session_state['name'] = name_input
                st.session_state['roll_no'] = roll_input
                st.rerun()
            else:
                st.error("Both fields are required.")
    st.stop()

name = st.session_state['name']



roll_no = st.session_state['roll_no']

# --- SIDEBAR ---
with st.sidebar:
    st.title("🎓 Placement Tracker")
    st.markdown(f"**Name:** {name}")
    st.markdown(f"**Roll No:** {roll_no}")
    st.divider()
    
    # Simple logout button clearing session state
    if st.button("Logout"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

# --- MAIN APP ---
tab1, tab2, tab3, tab4 = st.tabs(["🤖 Copilot", "📅 Dashboard", "📊 Analytics", "🏢 Company Hub & Applications"])

with tab1:
    st.header("🤖 AI Placement Copilot")
    
    with st.expander("📝 Your Daily Placement Brief", expanded=True):
        brief = fetch_daily_brief(roll_no)
        st.markdown(brief)
                
    st.divider()
    
    # st.fragment isolates the chat so typing doesn't reload the whole page
    @st.fragment
    def chat_interface():
        st.info("Ask me anything about your placement schedule or applications!")
        
        if "messages" not in st.session_state:
            st.session_state.messages = []
            
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                
        if prompt := st.chat_input("What should I prepare for today?"):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
                
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    try:
                        res = requests.post(
                            f"{API_URL}/chat", 
                            json={"message": prompt, "student_id": roll_no}
                        )
                        reply = res.json().get("reply", "Sorry, I couldn't process that.")
                    except Exception as e:
                        reply = f"Error connecting to backend: {e}"
                    st.markdown(reply)
            st.session_state.messages.append({"role": "assistant", "content": reply})

    chat_interface()

with tab2:
    st.header("Campus Placement Calendar")
    
    col_c, col_d = st.columns([3, 1])
    with col_c:
        st.write("Official schedule for upcoming PPTs, Tests, and Interviews.")
    with col_d:
        if st.button("🔄 Sync College Calendar", use_container_width=True):
            with st.spinner("Syncing calendar (Check browser if login needed)..."):
                try:
                    req = requests.post(f"{API_URL}/sync-calendar")
                    res = req.json()
                    if "error" in res:
                        st.error(res["error"])
                    else:
                        st.success(f"Successfully synced {res.get('rows', 0)} rows!")
                        st.rerun()
                except Exception as e:
                    st.error(f"Sync failed: {e}")
    
    df_cal = fetch_calendar()
    
    if df_cal.empty:
        st.info("No calendar data available.")
    else:
        # Strip whitespace from column names (sheet has trailing spaces like 'Date ', 'Company ')
        df_cal.columns = df_cal.columns.str.strip()
        
        # Today's Highlights
        st.subheader("Today's Events")
        today_dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        if 'Date' in df_cal.columns:
            # Clean up date column values: strip whitespace
            df_cal['Date'] = df_cal['Date'].astype(str).str.strip()
            
            # Parse dates trying multiple formats
            parsed = pd.to_datetime(df_cal['Date'], format='%d-%m-%Y', errors='coerce')
            # Try alternate format if some failed
            mask_na = parsed.isna()
            if mask_na.any():
                parsed[mask_na] = pd.to_datetime(df_cal.loc[mask_na, 'Date'], format='%d/%m/%Y', errors='coerce')
            df_cal['parsed_date'] = parsed
            
            # Today's events
            today_events = df_cal[df_cal['parsed_date'] == today_dt]
            if not today_events.empty:
                for _, row in today_events.iterrows():
                    st.error(f"🚨 **{row.get('Company', 'Unknown')}** - {row.get('Process', '')} at {row.get('Test Start Time', '')} / {row.get('PPT Start Time', '')}")
            else:
                st.success("No events scheduled for today.")
        
            st.divider()
        
            # Filter: only show today and future events
            df_cal_future = df_cal[df_cal['parsed_date'] >= today_dt].drop(columns=['parsed_date'])
            st.dataframe(df_cal_future, width='stretch')
        else:
            st.divider()
            st.dataframe(df_cal, width='stretch')

with tab3:
    st.header("Placement Analytics")
    
    col_btn1, col_btn2, col_btn3 = st.columns(3)
    with col_btn1:
        if st.button("📧 Sync Offers from Email", use_container_width=True, type="primary"):
            with st.spinner("Syncing offer letters from Gmail..."):
                try:
                    req = requests.post(f"{API_URL}/sync-email-offers")
                    if req.status_code == 200:
                        res = req.json()
                        st.success(f"Email sync done! {res.get('new_emails_found', 0)} emails → {res.get('email_records', 0)} records.")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error(f"Sync failed: {req.text}")
                except Exception as e:
                    st.error(f"Sync failed: {e}")

    with col_btn2:
        if st.button("🌐 Enrich CTC from pod.ai", use_container_width=True):
            try:
                req = requests.post(f"{API_URL}/sync-ctc-enrichment", timeout=15)
                if req.status_code == 200:
                    job = req.json()
                    job_id = job.get("job_id")
                    st.info(f"⏳ CTC enrichment running in background (job `{job_id}`). Checking every 10s...")

                    # Poll for up to 5 minutes
                    import time as _time
                    for _ in range(30):
                        _time.sleep(10)
                        try:
                            status_req = requests.get(f"{API_URL}/sync-ctc-enrichment/status?job_id={job_id}", timeout=10)
                            status = status_req.json()
                            if status.get("status") == "done":
                                result = status.get("result", {})
                                st.success(f"✅ CTC enrichment done! {result.get('portal_records', 0)} records enriched in {status.get('elapsed_seconds', '?')}s.")
                                st.cache_data.clear()
                                st.rerun()
                                break
                            elif status.get("status") == "error":
                                st.error(f"Enrichment failed: {status.get('result', {}).get('error', 'Unknown error')}")
                                break
                        except Exception:
                            pass
                    else:
                        st.warning("Job still running after 5 min — check logs. Data will update on next cache refresh.")
                else:
                    st.error(f"Enrichment failed to start: {req.text}")
            except Exception as e:
                st.error(f"Enrichment failed: {e}")


    with col_btn3:
        if st.button("🗑️ Clear Sheet Data & Reset Cron", use_container_width=True):
            with st.spinner("Clearing sheets and resetting cron to 1st July..."):
                try:
                    req = requests.post(f"{API_URL}/clear-offers")
                    if req.status_code == 200:
                        st.success("Successfully cleared sheets and reset cron start date!")
                        st.rerun()
                    else:
                        st.error(f"Failed to clear sheets: {req.text}")
                except Exception as e:
                    st.error(f"Failed to clear sheets: {e}")
                    
    analytics_data = fetch_analytics()
    
    col1, col2 = st.columns(2)
    col1.metric("Total Offers Issued", analytics_data.get("total_offers", 0))
    col2.metric("Companies Hiring", analytics_data.get("companies_hiring", 0))
    
    st.divider()
    
    offers_by_role = analytics_data.get("offers_by_role", {})
    if offers_by_role:
        st.subheader("Offer Types")
        role_df = pd.DataFrame(list(offers_by_role.items()), columns=["offer_type", "count"])
        role_chart = alt.Chart(role_df).mark_arc().encode(
            theta="count",
            color="offer_type",
            tooltip=["offer_type", "count"]
        ).properties(height=300)
        st.altair_chart(role_chart, use_container_width=True)
        
    st.divider()
    st.subheader("All Global Offers")
    df_offers = fetch_offers()
    if df_offers.empty:
        st.info("No offers recorded yet.")
    else:
        st.dataframe(df_offers, use_container_width=True)

with tab4:
    st.header("🏢 Company Hub & Applications")
    
    # Company Knowledge Base Search
    st.subheader("Company Insights")
    search_company = st.text_input("Search for a company's historical placement pattern (e.g., Adobe, Microsoft)")
    if search_company:
        try:
            res = requests.get(f"{API_URL}/company/{search_company}")
            company_data = res.json().get("data")
            if company_data:
                st.success(f"Found insights for {search_company.title()}")
                col_i1, col_i2 = st.columns(2)
                col_i1.metric("Interview Rounds", company_data.get("rounds", "N/A"))
                st.write("**OA Pattern:**", company_data.get("oa_pattern", ""))
                st.write("**Frequent Topics:**", ", ".join(company_data.get("frequent_topics", [])))
                st.info(f"**Preparation Tips:** {company_data.get('preparation_tips', '')}")
            else:
                st.warning(f"No historical insights found for {search_company} in the knowledge base.")
        except Exception as e:
            st.error(f"Failed to fetch company insights: {e}")
            
    st.divider()
    st.subheader("My Applications")
    
    # Load cached personal applications from API
    df_apps = fetch_applications(roll_no)
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        if not df_apps.empty:
            st.caption(f"Found {len(df_apps)} synced applications.")
        else:
            st.caption("No applications found in cache.")
            
    with col2:
        if st.button("🔄 Sync pod.ai Data", use_container_width=True):
            if POD_AI_USERNAME and POD_AI_PASSWORD:
                with st.spinner("Scraping pod.ai... This may take a minute."):
                    try:
                        req = requests.post(f"{API_URL}/sync-applications", json={
                            "pod_ai_username": POD_AI_USERNAME,
                            "pod_ai_password": POD_AI_PASSWORD,
                            "student_name": name,
                            "student_id": roll_no
                        })
                        res = req.json()
                        if res.get("errors"):
                            st.error("Errors occurred during sync:")
                            for err in res["errors"]:
                                st.error(err)
                        else:
                            st.success(f"Successfully scraped and cached {res.get('portal_records', 0)} applications!")
                    except Exception as e:
                        st.error(f"Sync failed: {e}")
            else:
                st.session_state['show_sync_modal'] = True
            
    if st.session_state.get('show_sync_modal', False):
        st.warning("Playwright Scraping Required")
        st.write("To sync your latest applications, please enter your pod.ai credentials. These are used live and never stored.")
        with st.form("sync_form"):
            pod_email = st.text_input("pod.ai Email", value="")
            pod_pwd = st.text_input("pod.ai Password", type="password")
            
            if st.form_submit_button("Run Sync"):
                if pod_email and pod_pwd:
                    with st.spinner("Scraping pod.ai... This may take a minute."):
                        try:
                            req = requests.post(f"{API_URL}/sync-applications", json={
                                "pod_ai_username": pod_email,
                                "pod_ai_password": pod_pwd,
                                "student_name": name,
                                "student_id": roll_no
                            })
                            res = req.json()
                            if res.get("errors"):
                                st.error("Errors occurred during sync:")
                                for err in res["errors"]:
                                    st.error(err)
                            else:
                                st.success(f"Successfully scraped and cached {res.get('portal_records', 0)} applications!")
                        except Exception as e:
                            st.error(f"Sync failed: {e}")
                    st.session_state['show_sync_modal'] = False
                    st.rerun()
                else:
                    st.error("Credentials required.")

    st.divider()
    
    if df_apps.empty:
        st.info("No applications to show. Click Sync to fetch them!")
    else:
        # Timeline View
        for idx, row in df_apps.iterrows():
            with st.container():
                col_a, col_b = st.columns([3, 1])
                with col_a:
                    st.markdown(f"#### {row['company_name']}")
                    st.markdown(f"**{row['offer_type']}**")
                with col_b:
                    st.metric("CTC", row['ctc'])
                    
                st.info(f"Status: **{row.get('status', 'N/A')}**")
                st.divider()
