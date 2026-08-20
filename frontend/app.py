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
    POD_AI_USERNAME, POD_AI_PASSWORD, get_secret
)
from auth import get_user_profile, get_oauth_url, exchange_code_for_token, get_user_credentials

API_URL = get_secret("API_URL", default="http://localhost:8000/api")

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
    /* Premium Modern Font */
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Outfit', sans-serif;
    }
    
    /* Background & Main App */
    .stApp {
        background-color: #0f1115; /* Sleek dark background */
        background-image: radial-gradient(circle at top right, rgba(78, 205, 196, 0.05), transparent 40%),
                          radial-gradient(circle at bottom left, rgba(255, 107, 107, 0.05), transparent 40%);
    }

    /* Clean up the top padding and header */
    .block-container {
        padding-top: 2rem !important;
        max-width: 1200px;
    }
    
    /* Premium Metric Cards with Glassmorphism */
    [data-testid="stMetric"] {
        background: rgba(30, 30, 47, 0.6);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border-radius: 16px;
        padding: 1.5rem;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.2);
        border: 1px solid rgba(255, 255, 255, 0.05);
        transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
        position: relative;
        overflow: hidden;
    }
    [data-testid="stMetric"]:hover {
        transform: translateY(-5px);
        box-shadow: 0 12px 40px 0 rgba(0, 0, 0, 0.4);
        border: 1px solid rgba(78, 205, 196, 0.3);
    }
    /* Shine effect on hover */
    [data-testid="stMetric"]::before {
        content: '';
        position: absolute;
        top: 0; left: -100%;
        width: 50%; height: 100%;
        background: linear-gradient(to right, transparent, rgba(255,255,255,0.03), transparent);
        transform: skewX(-20deg);
        transition: 0.5s;
    }
    [data-testid="stMetric"]:hover::before {
        left: 150%;
    }
    [data-testid="stMetricLabel"] {
        color: #a0a0b8 !important;
        font-weight: 500 !important;
        font-size: 0.95rem !important;
    }
    [data-testid="stMetricValue"] {
        color: #fff !important;
        font-weight: 700 !important;
        font-size: 2.2rem !important;
        background: -webkit-linear-gradient(45deg, #4ECDC4, #556270);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    
    /* Elegant Primary Buttons */
    .stButton > button {
        background: linear-gradient(135deg, #6366f1 0%, #a855f7 100%);
        color: white;
        border: none;
        border-radius: 12px;
        padding: 0.5rem 1.5rem;
        font-weight: 600;
        letter-spacing: 0.5px;
        box-shadow: 0 4px 15px rgba(99, 102, 241, 0.4);
        transition: all 0.3s ease;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(99, 102, 241, 0.6);
        color: white;
        border: none;
    }
    .stButton > button:active {
        transform: translateY(1px);
    }
    
    /* Expander Styling */
    .streamlit-expanderHeader {
        background: rgba(30, 30, 47, 0.6) !important;
        border-radius: 12px !important;
        font-weight: 600;
        border: 1px solid rgba(255, 255, 255, 0.05) !important;
        backdrop-filter: blur(10px);
    }
    [data-testid="stExpander"] {
        border: none !important;
        background: transparent !important;
    }
    
    /* Modern Chat Interface */
    [data-testid="stChatMessage"] {
        background: rgba(26, 26, 36, 0.8);
        backdrop-filter: blur(10px);
        border-radius: 16px;
        padding: 1.2rem;
        margin-bottom: 1.2rem;
        border: 1px solid rgba(255, 255, 255, 0.05);
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        animation: slideUp 0.3s ease-out forwards;
    }
    /* Distinguish Assistant vs User */
    [data-testid="stChatMessage"]:nth-child(even) {
        border-left: 3px solid #6366f1;
    }
    [data-testid="stChatMessage"]:nth-child(odd) {
        border-left: 3px solid #4ECDC4;
    }
    
    /* Chat Input Box */
    [data-testid="stChatInput"] {
        border-radius: 20px !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        background: rgba(30, 30, 47, 0.8) !important;
    }
    [data-testid="stChatInput"]:focus-within {
        border-color: #6366f1 !important;
        box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.2) !important;
    }
    
    /* Tabs Styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: transparent;
        border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    }
    .stTabs [data-baseweb="tab"] {
        background-color: transparent;
        border-radius: 8px 8px 0 0;
        padding-top: 1rem;
        padding-bottom: 1rem;
        font-weight: 500;
        color: #a0a0b8;
    }
    .stTabs [aria-selected="true"] {
        color: #fff;
        border-bottom: 2px solid #6366f1;
    }
    
    /* Dataframe styling */
    [data-testid="stDataFrame"] {
        border-radius: 12px;
        overflow: hidden;
        border: 1px solid rgba(255, 255, 255, 0.05);
    }
    
    /* Headers Typography */
    h1, h2, h3 {
        color: #f8fafc;
        letter-spacing: -0.02em;
    }
    h1 {
        font-weight: 700;
        background: linear-gradient(135deg, #fff 0%, #a0a0b8 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    
    /* Sidebar */
    [data-testid="stSidebar"] {
        background-color: rgba(15, 17, 21, 0.98);
        border-right: 1px solid rgba(255, 255, 255, 0.05);
    }
    
    /* Slide up animation */
    @keyframes slideUp {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }
</style>
""", unsafe_allow_html=True)


# --- USER PROFILE ---
if 'roll_no' not in st.session_state or 'name' not in st.session_state:
    st.title("🎓 Welcome to Placement Tracker")
    st.write("Please authenticate with your IIITD Google account to securely load your dashboard.")

    # Check for OAuth callback code in URL
    if "code" in st.query_params:
        with st.spinner("Authenticating..."):
            if exchange_code_for_token(st.query_params["code"]):
                st.query_params.clear()
                # After exchange, fall through to show the confirm screen
            else:
                st.error("Authentication failed. Please try again.")

    # Check if we have a cached token
    creds = get_user_credentials()
    if creds and creds.valid:
        # Fetch profile to show WHO is cached — don't auto-login silently
        profile = get_user_profile()
        if profile:
            cached_email = profile.get("email", "")
            cached_name = profile.get("name", "")

            # Only auto-accept if it's an IIITD account
            is_iiitd = cached_email.endswith("@iiitd.ac.in")

            st.success(f"✅ Google account detected: **{cached_name}** ({cached_email})")

            col_confirm, col_switch = st.columns(2)
            with col_confirm:
                if st.button("✅ Continue as this account", use_container_width=True, type="primary"):
                    roll_no = "".join(filter(str.isdigit, cached_email))
                    st.session_state['name'] = cached_name
                    st.session_state['roll_no'] = roll_no
                    st.rerun()
            with col_switch:
                if st.button("🔄 Switch Account", use_container_width=True):
                    # Delete the cached token so next login goes through Google account chooser
                    import os
                    if os.path.exists("user_token.json"):
                        os.remove("user_token.json")
                    st.rerun()
        else:
            st.error("Could not fetch profile information. Please try logging in again.")
            import os
            if os.path.exists("user_token.json"):
                os.remove("user_token.json")
    else:
        # No cached credentials — show the Google login button
        import os as _os
        _redirect = _os.environ.get("GOOGLE_REDIRECT_URI") or _os.environ.get("RENDER_EXTERNAL_URL") or "http://localhost:8501 (fallback)"
        st.info(f"🔍 **Redirect URI:** `{_redirect}`  |  **RENDER_EXTERNAL_URL:** `{_os.environ.get('RENDER_EXTERNAL_URL', 'NOT SET')}`")
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
        if "I'm having trouble" in brief or "Rate Limit" in brief:
            st.error(f"⚠️ **AI Unavailable:** {brief}")
        else:
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
            if "I'm having trouble" in reply or "Rate Limit" in reply:
                st.error(f"⚠️ **AI Unavailable:** {reply}")
            else:
                st.markdown(reply)
            st.session_state.messages.append({"role": "assistant", "content": reply})

    chat_interface()

    st.divider()

    # --- AI RESUME MATCHER ---
    with st.expander("📄 AI Resume Matcher — Find Your Best Company Fits", expanded=False):
        st.markdown("Upload your resume and the AI will analyse it against companies currently recruiting on campus.")
        uploaded_resume = st.file_uploader("Upload Resume (PDF only)", type=["pdf"], key="resume_uploader")
        if uploaded_resume:
            if st.button("🔍 Find My Best Matches", use_container_width=True):
                with st.spinner("Analysing your resume against active companies... ⏳"):
                    try:
                        res = requests.post(
                            f"{API_URL}/recommend-companies",
                            files={"resume": (uploaded_resume.name, uploaded_resume.getvalue(), "application/pdf")}
                        )
                        if res.status_code == 200:
                            recommendation = res.json().get("recommendation", "No recommendations generated.")
                            st.session_state["resume_recommendation"] = recommendation
                        else:
                            st.error(f"Backend error: {res.json().get('detail', 'Unknown error')}")
                    except Exception as e:
                        st.error(f"Failed to connect to backend: {e}")

        if "resume_recommendation" in st.session_state:
            rec = st.session_state["resume_recommendation"]
            if "I'm having trouble" in rec or "Rate Limit" in rec:
                st.error(f"⚠️ **AI Unavailable:** {rec}")
            else:
                st.markdown(rec)

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
    
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("🔄 Sync Global Offers & CTC", use_container_width=True, type="primary"):
            with st.spinner("Step 1/2: Syncing offers from emails..."):
                try:
                    req = requests.post(f"{API_URL}/sync-email-offers")
                    if req.status_code == 200:
                        st.success("✅ Emails synced successfully!")
                    else:
                        st.error(f"Email sync failed: {req.text}")
                except Exception as e:
                    st.error(f"Email sync failed: {e}")
                    
            with st.spinner("Step 2/2: Starting CTC Enrichment from pod.ai..."):
                try:
                    ctc_req = requests.post(f"{API_URL}/sync-ctc-enrichment")
                    if ctc_req.status_code == 200:
                        st.success("✅ CTC Enrichment has started in the background! (This process takes a few minutes. Check back later to see the updated CTCs).")
                        st.cache_data.clear()
                    else:
                        st.error(f"CTC sync failed to start: {ctc_req.text}")
                except Exception as e:
                    st.error(f"CTC sync failed: {e}")
                    
    with col_btn2:
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
        # --- STATUS BADGE HELPER ---
        STATUS_COLORS = {
            "Interviewing": ("#6366f1", "🎯"),
            "Offered":      ("#22c55e", "🎉"),
            "Shortlisted":  ("#f59e0b", "⭐"),
            "Applied":      ("#3b82f6", "📝"),
            "Rejected":     ("#ef4444", "✖️"),
            "N/A":          ("#6b7280", "❓"),
        }

        def render_status_badge(status):
            color, icon = STATUS_COLORS.get(status, ("#6b7280", "❓"))
            return f'<span style="background:{color}22; color:{color}; border:1px solid {color}66; padding:3px 10px; border-radius:99px; font-size:0.8rem; font-weight:600">{icon} {status}</span>'

        def render_app_card(row):
            status = row.get('status', 'N/A')
            badge = render_status_badge(status)
            st.markdown(f"""
            <div style="background:rgba(30,30,47,0.6); border:1px solid rgba(255,255,255,0.06); border-radius:16px; padding:1.2rem 1.5rem; margin-bottom:1rem; backdrop-filter:blur(10px);">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <div style="font-size:1.1rem; font-weight:700; color:#f8fafc;">{row.get('company_name', 'Unknown')}</div>
                        <div style="color:#a0a0b8; font-size:0.9rem; margin-top:2px;">{row.get('offer_type', 'N/A')} &nbsp;•&nbsp; CTC: <b style='color:#4ECDC4'>{row.get('ctc', 'N/A')}</b></div>
                    </div>
                    <div>{badge}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        # --- THREE-FILTER TABS ---
        df_apps["status"] = df_apps["status"].fillna("N/A").astype(str).str.strip()

        # Classify based on substring to handle variations like 'Not Eligible', 'eligible', etc.
        mask_ineligible = df_apps["status"].str.contains("Not Eligible|Not-Eligible", case=False, na=False)
        mask_eligible = df_apps["status"].str.contains("Eligible", case=False, na=False) & ~mask_ineligible
        
        df_ineligible = df_apps[mask_ineligible]
        df_eligible = df_apps[mask_eligible]
        
        # Everything else falls into 'Applied' bucket (Registered, Shortlisted, Offered, N/A, etc.)
        df_applied = df_apps[~mask_eligible & ~mask_ineligible]

        f_tab1, f_tab2, f_tab3 = st.tabs([
            f"📝 Applied ({len(df_applied)})",
            f"✅ Eligible ({len(df_eligible)})",
            f"❌ Not Eligible ({len(df_ineligible)})",
        ])

        with f_tab1:
            if df_applied.empty:
                st.info("No applied companies. Click Sync to fetch your applications!")
            else:
                for _, row in df_applied.iterrows():
                    render_app_card(row)

        with f_tab2:
            if df_eligible.empty:
                st.info("No eligible companies found. Sync pod.ai to fetch your eligibility data.")
            else:
                for _, row in df_eligible.iterrows():
                    render_app_card(row)

        with f_tab3:
            if df_ineligible.empty:
                st.info("No ineligible companies found.")
            else:
                for _, row in df_ineligible.iterrows():
                    render_app_card(row)

