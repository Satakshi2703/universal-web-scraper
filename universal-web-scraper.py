import os
import sys
import json
import asyncio
import pandas as pd
import streamlit as st
import google.generativeai as genai
from datetime import datetime
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from langchain.text_splitter import RecursiveCharacterTextSplitter
from streamlit_tags import st_tags
from io import BytesIO

# Ensure Windows compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Configure Gemini API
genai.configure(api_key="AIzaSyAPiMqqMyUNXBL_GEWePLQE5jBvvV_HFHc")

# Streamlit UI
st.set_page_config(page_title="Universal Web Scraper", layout="wide")
st.title("🕷 Universal Web Scraper")

with st.sidebar:
    st.title("🔧 Scraper Settings")
    model_name = st.selectbox("Select Model", ["gemini-1.5-flash"], index=0)
    url = st.text_input("Enter URL")
    chunk_size = st.slider("Chunk Size", 5000, 25000, 5000)
    chunk_overlap = st.slider("Chunk Overlap", 100, 2000, 2000)
    fields = st_tags(
        label="Enter Fields to Extract",
        text="Press enter to add more",
        value=[],
        maxtags=10
    )
    scrape_button = st.button("🚀 Start Scraping")

# Initialize session state for storing extracted data
if "extracted_data" not in st.session_state:
    st.session_state.extracted_data = None

def fetch_html(url):
    """Fetch HTML using Playwright and extract image URLs."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.goto(url, wait_until="load", timeout=60000)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(5000)
        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, "html.parser")
    
    # Extracting image URLs
    image_urls = [img["src"] for img in soup.find_all("img") if img.get("src")]

    return html, image_urls

def convert_html_to_text(html_content):
    """Extract visible text from HTML."""
    soup = BeautifulSoup(html_content, "html.parser")
    for script in soup(["script", "style"]):
        script.decompose()
    return soup.get_text(separator="\n", strip=True)

def get_text_chunks(content, chunk_size, chunk_overlap):
    """Break text into chunks."""
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return text_splitter.split_text(content)

def fix_json_response(response_text):
    """Fix and validate JSON response from Gemini."""
    try:
        response_text = response_text.strip()
        if not response_text.startswith("{"):
            response_text = "{" + response_text.split("{", 1)[-1]
        if not response_text.endswith("}"):
            response_text = response_text.rsplit("}", 1)[0] + "}"
        return json.loads(response_text)
    except json.JSONDecodeError:
        return None

def extract_data_with_gemini(markdown_chunks, fields, image_urls):
    """Extract structured data using Gemini, including images if requested."""
    extracted_data = {"listings": []}
    model = genai.GenerativeModel("gemini-1.5-flash")

    for chunk in markdown_chunks:
        json_part = ', '.join([f'"{field}": "value"' for field in fields])
        
        if "image_url" in fields:
            json_part += ', "image_url": "some_image_url"'

        prompt = f"""
        Extract the following fields from the provided text:
        - {', '.join(fields)}
        
        If "image_url" is requested, use the available image URLs:
        {image_urls}

        Return a valid JSON response:
        {{ "listings": [{{ {json_part} }}] }}

        Text Content:
        {chunk}
        """

        response = model.generate_content(prompt)
        cleaned_data = fix_json_response(response.text)
        
        if cleaned_data and "listings" in cleaned_data:
            for entry in cleaned_data["listings"]:
                if "image_url" in entry and image_urls:
                    entry["image_url"] = image_urls.pop(0)  # Assign available image URLs
            extracted_data["listings"].extend(cleaned_data["listings"])

    return extracted_data

def save_results(validated_listings):
    """Save extracted data as JSON, CSV, and Excel."""
    df = pd.DataFrame(validated_listings)

    json_data = json.dumps(validated_listings, indent=4, ensure_ascii=False)
    csv_data = df.to_csv(index=False).encode()
    excel_buffer = BytesIO()
    df.to_excel(excel_buffer, index=False, engine="openpyxl")
    excel_buffer.seek(0)

    return json_data, csv_data, excel_buffer

# Scraping Process
if scrape_button and url and fields:
    with st.spinner("⏳ Scraping in progress..."):
        html_content, image_urls = fetch_html(url)

    if html_content:
        text_content = convert_html_to_text(html_content)
        text_chunks = get_text_chunks(text_content, chunk_size, chunk_overlap)
        extracted_data = extract_data_with_gemini(text_chunks, fields, image_urls)

        if extracted_data and "listings" in extracted_data:
            st.session_state.extracted_data = extracted_data["listings"]

# Display Extracted Data
if st.session_state.extracted_data:
    df = pd.DataFrame(st.session_state.extracted_data)
    st.dataframe(df)

    # Prepare files for download
    json_data, csv_data, excel_buffer = save_results(st.session_state.extracted_data)

    st.download_button("📥 Download JSON", json_data, file_name="scraped_data.json", mime="application/json")
    st.download_button("📥 Download CSV", csv_data, file_name="scraped_data.csv", mime="text/csv")
    from io import BytesIO

    excel_buffer = BytesIO()
    df.to_excel(excel_buffer, index=False, engine="openpyxl")
    excel_buffer.seek(0)

    st.download_button("📥 Download Excel", excel_buffer, file_name="scraped_data.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
else:
    st.warning("No data available. Please start scraping.")