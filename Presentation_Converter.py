import asyncio
import os
import streamlit as st
from datetime import datetime
from typing import Optional

# OpenAI 1.x SDK
from openai import OpenAI

# HTML templating (optional)
from jinja2 import Environment, FileSystemLoader, select_autoescape

# Playwright for HTML->PDF
from playwright.async_api import async_playwright

# ---------------------------------------
# Configuration
# ---------------------------------------
st.set_page_config(page_title="HTML → PDF Generator", page_icon="🧾", layout="wide")

OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
if not OPENAI_API_KEY:
    st.warning("Set OPENAI_API_KEY in your environment to enable HTML generation.")

client = OpenAI(api_key=OPENAI_API_KEY)

# Optional Jinja2 environment
env = Environment(
    loader=FileSystemLoader("."),
    autoescape=select_autoescape()
)

# ---------------------------------------
# Helpers
# ---------------------------------------
async def html_to_pdf_playwright(html: str, pdf_path: str, emulate_media: str = "screen"):
    """
    Render HTML to PDF using Playwright/Chromium headless.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.set_content(html, wait_until="load")
        if emulate_media:
            await page.emulate_media(media=emulate_media)
        # Generate PDF
        await page.pdf(path=pdf_path, format="A4", print_background=True)
        await browser.close()

def generate_html_with_openai(format_instructions: str, content_instructions: str) -> str:
    """
    Ask the model to produce valid, self-contained HTML5 (inline CSS where possible).
    Uses OpenAI 1.x Responses API and returns response.output_text.
    """
    system_prompt = (
        "You are an expert HTML designer. Return a COMPLETE, self-contained HTML5 document for every request. Include: <!doctype html>, <html>, <head> with <meta charset='utf-8'> and <meta name='viewport' content='width=device-width, initial-scale=1'>, a meaningful <title>, and a single <style> tag for all CSS. Define CSS variables in :root for --accent and --bg and use var(--accent)/var(--bg) across headings, links, badges, callouts, buttons, and accents. Use only system fonts and inline SVG if needed; do not load external assets (no web fonts, scripts, or remote images). Structure content with semantic HTML, concise paragraphs, and clear sections; prefer lists for dense info. Make it responsive up to ~1200px and visually modern (cards, spacing, contrast). Ensure print/PDF readiness: include @page margins, break-inside: avoid on cards/sections, and @media print rules so it prints cleanly with backgrounds. Return only HTML."
    )
    user_prompt = f"""
Desired format/structure:
{format_instructions}

Content requirements:
{content_instructions}

Constraints:
- Use semantic HTML and minimal, clean CSS.
- Include a title in <head>.
- Use system fonts.
- Ensure printable margins and sensible page breaks for PDF (CSS page breaks).
    """

    resp = client.responses.create(
        model="gpt-4o-2024-08-06",
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
    )

    # Prefer the convenience property if available per docs
    # Fallback to scanning `output` if necessary.
    text = getattr(resp, "output_text", None)
    if text:
        return text.strip()

    # Fallback: iterate outputs to collect output_text chunks
    try:
        parts = []
        for out in getattr(resp, "output", []) or []:
            if getattr(out, "type", None) == "message":
                for c in getattr(out, "content", []) or []:
                    if getattr(c, "type", None) == "output_text":
                        parts.append(getattr(c, "text", ""))
            elif getattr(out, "type", None) == "output_text":
                parts.append(getattr(out, "text", ""))
        return "\n".join([p for p in parts if p]).strip()
    except Exception:
        return ""

# ---------------------------------------
# UI
# ---------------------------------------
st.title("🧾 Generate HTML artifacts and export to PDF")

left, right = st.columns([1, 1])

with left:
    st.subheader("1) Choose a format")
    default_format = """A one-page report:
- Header with logo placeholder, report title, and date.
- Executive summary section.
- Two-column section for key metrics and bullet insights.
- Footer with contact info and page number."""
    format_instructions = st.text_area("Format instructions", value=default_format, height=180)

    st.subheader("2) Describe the content to include")
    default_content = "Generate a weekly marketing performance report for 'Acme Co' covering website traffic, conversions, and top campaigns for the last 7 days."
    content_instructions = st.text_area("Content instructions", value=default_content, height=180)

    generate_btn = st.button("Generate HTML with OpenAI", type="primary")

with right:
    st.subheader("Preview and Export")

    html_state = st.session_state.get("generated_html", "")

    if generate_btn:
        if not OPENAI_API_KEY:
            st.error("Missing OPENAI_API_KEY environment variable.")
        else:
            with st.spinner("Generating HTML..."):
                html_state = generate_html_with_openai(format_instructions, content_instructions)
                st.session_state["generated_html"] = html_state

    if html_state:
        st.markdown("Preview (sanitized):")

        # Recent Streamlit versions include st.html; if not available, fall back to components.html.
        try:
            st.html(html_state, width="stretch")
        except Exception:
            from streamlit.components.v1 import html as st_html
            st_html(html_state, height=600, scrolling=True)

        col1, col2 = st.columns(2)
        with col1:
            file_name = st.text_input("PDF file name", value=f"report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf")
        with col2:
            emulate_media = st.selectbox("PDF CSS media", ["screen", "print"], index=0)

        if st.button("Export to PDF (Playwright)"):
            with st.spinner("Rendering PDF..."):
                pdf_path = file_name
                asyncio.run(html_to_pdf_playwright(html_state, pdf_path, emulate_media=emulate_media))
                with open(pdf_path, "rb") as f:
                    st.success("PDF generated.")
                    st.download_button("Download PDF", data=f.read(), file_name=file_name, mime="application/pdf")
    else:
        st.info("Generate HTML to see a preview and export to PDF.")
