import streamlit as st
import requests
import pandas as pd
import time
from datetime import datetime

# --- CONFIGURATION ---
BASE_URL = "[https://lda.senate.gov/api/v1/filings/](https://lda.senate.gov/api/v1/filings/)"

# Set page to wide mode for better table viewing
st.set_page_config(page_title="Senate LDA Dashboard", layout="wide")

st.title("🏛️ Senate Lobbying Disclosure Dashboard")
st.markdown("""
Search specifically for **Registrations & Quarterly Activity**.  
*Data sourced from the [Senate Lobbying Disclosure Act API](https://lda.senate.gov/api/).*
""")

# --- SIDEBAR INPUTS ---
st.sidebar.header("Search Parameters")

# 0. API Key Input (Prioritize User Input -> Fallback to Secrets)
api_key = st.sidebar.text_input("Senate API Key", type="password", help="Enter your key from lda.senate.gov")

if not api_key:
    # If text input is empty, try to load from secrets
    try:
        api_key = st.secrets.get("LDA_API_KEY")
    except (FileNotFoundError, KeyError):
        pass # No secrets found, user must input key

with st.sidebar.form("search_form"):
    st.info("Enter at least a Registrant OR Client Name.")
    
    # 1. Text Inputs
    registrant_input = st.text_input("Registrant Name", help="e.g. Microsoft, AARP")
    client_input = st.text_input("Client Name", help="e.g. Apple, Amazon")
    
    # 2. Filing Type
    filing_type_options = ["Q1", "Q2", "Q3", "Q4", "MM", "YY", "RR", "RA"]
    filing_types = st.multiselect("Report Type", options=filing_type_options, default=[])
    
    # 3. Amount Reported (Min/Max)
    st.subheader("Amount Reported")
    col1, col2 = st.columns(2)
    with col1:
        amount_min = st.number_input("Min ($)", min_value=0, step=5000, value=0)
    with col2:
        amount_max = st.number_input("Max ($)", min_value=0, step=5000, value=0)

    # 4. Filing Date (Date Posted)
    st.subheader("Date Posted")
    date_range = st.date_input(
        "Select Date Range",
        value=[],
        min_value=datetime(2000, 1, 1),
        max_value=datetime.today(),
        help="Select a Start and End date."
    )
    
    # 5. Page Limit
    max_pages = st.slider("Max Pages to Fetch (25 records/page)", 1, 20, 5)

    submitted = st.form_submit_button("🔍 Search Records")

# --- APP LOGIC ---

if submitted:
    # 0. CHECK API KEY
    if not api_key:
        st.error("⚠️ **Missing API Key:** Please enter a key in the sidebar or configure secrets.")
        st.stop()

    # 1. VALIDATION: Check mandatory fields
    if not registrant_input.strip() and not client_input.strip():
        st.error("⚠️ **Validation Error:** You must provide at least a **Registrant Name** or a **Client Name**.")
        st.stop()

    # 2. BUILD API PARAMETERS
    params = {}
    
    if registrant_input.strip():
        params['registrant_name'] = registrant_input.strip()
    
    if client_input.strip():
        params['client_name'] = client_input.strip()
        
    if filing_types:
        if len(filing_types) == 1:
            params['filing_type'] = filing_types[0]
            
    if amount_min > 0:
        params['filing_amount_reported_min'] = amount_min
    if amount_max > 0 and amount_max >= amount_min:
        params['filing_amount_reported_max'] = amount_max

    # Handle Date Range
    if len(date_range) == 2:
        start_date, end_date = date_range
        params['filing_dt_posted_after'] = start_date.strftime("%Y-%m-%d")
        params['filing_dt_posted_before'] = end_date.strftime("%Y-%m-%d")
    elif len(date_range) == 1:
        st.warning("⚠️ Please select both a Start and End date for the date filter to apply.")

    # 3. FETCH DATA
    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": "application/json"
    }

    all_filings = []
    next_url = BASE_URL
    page_count = 0
    
    status_text = st.empty()
    progress_bar = st.progress(0)

    session = requests.Session()
    session.headers.update(headers)

    try:
        with st.spinner('Fetching data from Senate API...'):
            while next_url and page_count < max_pages:
                if page_count == 0:
                    response = session.get(next_url, params=params)
                else:
                    response = session.get(next_url)

                if response.status_code != 200:
                    st.error(f"API Error {response.status_code}: {response.text}")
                    break

                data = response.json()
                results = data.get('results', [])
                all_filings.extend(results)
                
                next_url = data.get('next')
                page_count += 1
                
                status_text.text(f"Fetched {len(all_filings)} records... (Page {page_count}/{max_pages})")
                progress_bar.progress(page_count / max_pages)
                
                time.sleep(0.5)

    except Exception as e:
        st.error(f"An error occurred: {e}")

    progress_bar.empty()
    status_text.empty()

    if not all_filings:
        st.warning("No records found matching your criteria.")
    else:
        df = pd.json_normalize(all_filings)

        if 'income' in df.columns and 'expenses' in df.columns:
            df['Amount Reported'] = df['income'].fillna(df['expenses'])
        elif 'income' in df.columns:
            df['Amount Reported'] = df['income']
        elif 'expenses' in df.columns:
            df['Amount Reported'] = df['expenses']
        else:
            df['Amount Reported'] = 0

        column_map = {
            'registrant.name': 'Registrant Name',
            'client.name': 'Client Name',
            'filing_type': 'Report Type',
            'Amount Reported': 'Amount Reported',
            'filing_year': 'Filing Year',
            'dt_posted': 'Posted'
        }
        
        available_cols = [c for c in column_map.keys() if c in df.columns]
        df_clean = df[available_cols].rename(columns=column_map)

        if len(filing_types) > 1:
            df_clean = df_clean[df_clean['Report Type'].isin(filing_types)]

        st.success(f"Found {len(df_clean)} records.")
        
        st.dataframe(
            df_clean, 
            use_container_width=True,
            column_config={
                "Amount Reported": st.column_config.NumberColumn(
                    "Amount Reported",
                    format="$%d"
                ),
                "Posted": st.column_config.DatetimeColumn(
                    "Date Posted",
                    format="D MMM YYYY, h:mm a"
                )
            }
        )
        
        csv = df_clean.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download Data as CSV",
            data=csv,
            file_name='lda_search_results.csv',
            mime='text/csv',
        )


