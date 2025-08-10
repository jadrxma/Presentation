# Presentation_Converter.py
import asyncio
import os
import tempfile
from datetime import datetime
from typing import Optional

import streamlit as st

# OpenAI 1.x SDK
from openai import OpenAI

# HTML templating (optional, not required but kept)
from jinja2 import Environment, FileSystemLoader, select_autoescape

# Playwright for HTML->PDF
from playwright.async_api import async_playwright

# For safely running async loop inside Streamlit
try:
    import nest_asyncio
    NEST_ASYNCIO_AVAILABLE = True
except Exception:
    NEST_ASYNCIO_AVAILABLE = False

# ---------------------------------------
# Streamlit page config
# ---------------------------------------
st.set_page_config(page_title="HTML → Presentation PDF Generator", page_icon="🧾", layout="wide")
st.title("🧾 Generate presentation-style HTML and export to PDF")

# ---------------------------------------
# OpenAI client
# ---------------------------------------
OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY") if hasattr(st, "secrets") else os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    st.warning("Set OPENAI_API_KEY in Streamlit secrets or as an environment variable to enable HTML generation.")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# Optional Jinja2 environment (unused but available)
env = Environment(loader=FileSystemLoader("."), autoescape=select_autoescape())

# ---------------------------------------
# Async Playwright renderer
# ---------------------------------------
async def html_to_pdf_playwright(html: str, pdf_path: str, emulate_media: str = "screen"):
    """
    Render HTML to PDF using Playwright/Chromium headless.
    """
    # Launch browser, set content, and save PDF
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.set_content(html, wait_until="load")
        if emulate_media:
            await page.emulate_media(media=emulate_media)
        # Generate PDF — rely on Playwright defaults and CSS @page rules from HTML
        await page.pdf(path=pdf_path, format="A4", print_background=True)
        await browser.close()

def render_pdf_sync(html: str, pdf_path: str, emulate_media: str = "screen"):
    """
    Always create a fresh asyncio loop for Playwright to avoid missing-loop errors in Streamlit.
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        # No loop in this thread → create one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        import nest_asyncio
        nest_asyncio.apply()
        return loop.run_until_complete(html_to_pdf_playwright(html, pdf_path, emulate_media))
    else:
        return loop.run_until_complete(html_to_pdf_playwright(html, pdf_path, emulate_media))


# ---------------------------------------
# OpenAI HTML generator (presentation-focused)
# ---------------------------------------
def generate_html_with_openai(format_instructions: str, content_instructions: str) -> str:
    """
    Ask the model to produce a modern presentation-style single-file HTML suitable for PDF export.
    """
    if not client:
        return "<!doctype html><html><head><meta charset='utf-8'><title>Missing API Key</title></head><body><h1>Missing OPENAI_API_KEY</h1><p>Set the key to generate HTML.</p></body></html>"

    system_prompt = (
       "You are an expert in HTML/CSS presentation design. Return a COMPLETE, self-contained HTML5 document "
    "that looks like a polished slide deck. Use these style rules:\n"
    "- First slide: full-screen hero style with large centered title, subtitle, and date.\n"
    "- Subsequent slides: alternating background colors for contrast.\n"
    "- Large headings (2.5rem+), bold typography, clean sans-serif system font.\n"
    "- Generous padding and spacing; centered or grid-based layout.\n"
    "- Use CSS variables in :root for --accent, --accent2, --bg, --text.\n"
    "- Cards for key metrics with big numbers and labels.\n"
    "- Inline SVG icons for sections and metrics (minimal style, no external files).\n"
    "- Ensure each slide prints on its own PDF page (@page breaks, break-after: page).\n"
    "Return only HTML, no explanations."
    )

    user_prompt = f"""
Desired presentation layout and format:
{format_instructions}

Content requirements:
{content_instructions}

Constraints:
- Use semantic HTML and minimal, clean CSS in a single <style> block.
- Each slide/section should be a distinct block that will print as its own page.
- Use system fonts only and avoid external scripts/assets.
- Keep the HTML self-contained.
    """

    resp = client.responses.create(
        model="gpt-4o-2024-08-06",
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.35,
        max_output_tokens=3000,
    )

    text = getattr(resp, "output_text", None)
    if text:
        return text.strip()

    # Fallback parsing
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
        return "<!doctype html><html><head><meta charset='utf-8'><title>Error</title></head><body><h1>Failed to parse OpenAI response</h1></body></html>"

# ---------------------------------------
# UI
# ---------------------------------------
left, right = st.columns([1, 1])

with left:
    st.subheader("1) Choose a format (presentation style)")
    default_format = """A 4-slide one-page-per-slide presentation:
- Title slide: logo placeholder, title, subtitle, date.
- Executive summary slide: 3 short bullet insights.
- Metrics slide: two-column cards with KPIs (Visitors, Conversions, Conversion Rate, Top Campaign).
- Top campaigns slide: bullets + small inline SVG bar to visualize top 3 campaigns.
Footer: contact details and page number on each slide."""
    format_instructions = st.text_area("Format instructions", value=default_format, height=200)

    st.subheader("2) Describe the content to include")
    default_content = "Generate a weekly marketing performance presentation for 'Acme Co' covering website traffic, conversions, conversion rate, and top campaigns for the last 7 days. Include short action-oriented insights."
    content_instructions = st.text_area("Content instructions", value=default_content, height=200)

    generate_btn = st.button("Generate HTML with OpenAI", type="primary")

with right:
    st.subheader("Preview and Export")
    html_state = st.session_state.get("generated_html", "")

    if generate_btn:
        if not OPENAI_API_KEY:
            st.error("Missing OPENAI_API_KEY environment variable.")
        else:
            with st.spinner("Generating presentation HTML..."):
                html_state = generate_html_with_openai(format_instructions, content_instructions)
                st.session_state["generated_html"] = html_state

    if html_state:
        st.markdown("Preview (sanitized):")
        # Attempt to render HTML preview; Streamlit may sanitize some CSS
        try:
            st.html(html_state, width="100%")
        except Exception:
            from streamlit.components.v1 import html as st_html
            st_html(html_state, height=700, scrolling=True)

        col1, col2 = st.columns(2)
        with col1:
            suggested_name = f"presentation_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
            file_name = st.text_input("PDF file name", value=suggested_name)
        with col2:
            emulate_media = st.selectbox("PDF CSS media", ["screen", "print"], index=0)

        if st.button("Export to PDF (Playwright)"):
            if not OPENAI_API_KEY:
                st.error("Cannot export: missing OPENAI_API_KEY (Playwright still runs locally but generation needs API key).")
            else:
                with st.spinner("Rendering PDF..."):
                    # Use a safe temporary file path
                    try:
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmpf:
                            tmp_path = tmpf.name
                        # Render
                        render_pdf_sync(html_state, tmp_path, emulate_media=emulate_media)

                        # Read bytes and offer download
                        with open(tmp_path, "rb") as f:
                            pdf_bytes = f.read()

                        st.success("PDF generated.")
                        st.download_button(
                            "Download PDF",
                            data=pdf_bytes,
                            file_name=file_name,
                            mime="application/pdf"
                        )
                    except Exception as e:
                        st.error(f"Failed to render PDF: {e}")
                    finally:
                        # Attempt cleanup of temp file
                        try:
                            if os.path.exists(tmp_path):
                                os.remove(tmp_path)
                        except Exception:
                            pass
    else:
        st.info("Generate HTML to see a preview and export to PDF.")

# End of file

