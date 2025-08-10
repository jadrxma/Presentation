import os
import tempfile
import textwrap
import json
from datetime import datetime

import streamlit as st
from openai import OpenAI
from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

# ReportLab imports for PDF creation
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors

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

# Optional Jinja2 environment (unused but kept)
env = Environment(loader=FileSystemLoader("."), autoescape=select_autoescape())

# ---------------------------------------
# ReportLab PDF creation function
# ---------------------------------------
def create_pdf(title, slides, pdf_path):
    c = canvas.Canvas(pdf_path, pagesize=A4)
    width, height = A4

    # Title page
    c.setFont("Helvetica-Bold", 24)
    c.drawCentredString(width / 2, height - 2 * inch, title)
    c.setFont("Helvetica", 12)
    c.drawCentredString(width / 2, height - 2.5 * inch, "Generated Presentation")
    c.showPage()

    # Slide pages
    for slide in slides:
        c.setFont("Helvetica-Bold", 18)
        c.setFillColor(colors.darkblue)
        c.drawString(1 * inch, height - 1.2 * inch, slide.get("title", "Untitled Slide"))

        c.setFont("Helvetica", 12)
        c.setFillColor(colors.black)

        y = height - 1.8 * inch
        bullets = slide.get("bullets", [])
        for bullet in bullets:
            wrapped = textwrap.wrap(f"• {bullet}", width=90)
            for line in wrapped:
                c.drawString(1 * inch, y, line)
                y -= 14
            y -= 4

        c.showPage()

    c.save()

# ---------------------------------------
# PDF rendering with WeasyPrint
# ---------------------------------------
def html_to_pdf_weasyprint(html: str, pdf_path: str):
    HTML(string=html).write_pdf(pdf_path)

# ---------------------------------------
# OpenAI HTML generator (presentation-focused)
# ---------------------------------------
def generate_html_with_openai(format_instructions: str, content_instructions: str) -> str:
    if not client:
        return "<!doctype html><html><head><meta charset='utf-8'><title>Missing API Key</title></head><body><h1>Missing OPENAI_API_KEY</h1></body></html>"

    system_prompt = (
        "You are an expert in HTML/CSS presentation design. Return a COMPLETE, self-contained HTML5 document "
        "that looks like a polished slide deck:\n"
        "- First slide: full-screen hero with large centered title, subtitle, and date.\n"
        "- Alternating background colors for slides.\n"
        "- Large bold headings (2.5rem+), system sans-serif font.\n"
        "- Grid layouts or cards for metrics.\n"
        "- Inline SVG icons where relevant.\n"
        "- Use CSS variables in :root for --accent, --accent2, --bg, --text.\n"
        "- Each slide prints as its own PDF page (use page-break-after: always; except last slide).\n"
        "- No external assets, fonts, or scripts.\n"
        "Return only the HTML."
    )

    user_prompt = f"""
Desired presentation format:
{format_instructions}

Content to include:
{content_instructions}
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

    try:
        parts = []
        for out in getattr(resp, "output", []) or []:
            if getattr(out, "type", None) == "output_text":
                parts.append(getattr(out, "text", ""))
        return "\n".join(parts).strip()
    except Exception:
        return "<!doctype html><html><head><meta charset='utf-8'><title>Error</title></head><body><h1>Failed to parse OpenAI response</h1></body></html>"

# ---------------------------------------
# UI
# ---------------------------------------
left, right = st.columns([1, 1])

with left:
    st.subheader("1) Choose a format (presentation style)")
    default_format = """A 4-slide deck:
- Title slide: logo placeholder, title, subtitle, date.
- Executive summary slide: 3 key bullet insights.
- Metrics slide: two-column KPI cards (Visitors, Conversions, Conversion Rate, Top Campaign).
- Top campaigns slide: bullet list + small inline bar chart.
Footer: contact info + page number."""
    format_instructions = st.text_area("Format instructions", value=default_format, height=200)

    st.subheader("2) Describe the content to include")
    default_content = "Generate a weekly marketing performance presentation for 'Acme Co' covering website traffic, conversions, conversion rate, and top campaigns for the last 7 days. Include actionable insights."
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
            pass  # No emulate_media for WeasyPrint — it uses print media by default

        # --- Export using WeasyPrint ---
        if st.button("Export to PDF (WeasyPrint)"):
            with st.spinner("Rendering PDF..."):
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmpf:
                        tmp_path = tmpf.name
                    html_to_pdf_weasyprint(html_state, tmp_path)

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
                    try:
                        if os.path.exists(tmp_path):
                            os.remove(tmp_path)
                    except Exception:
                        pass

        # --- Optional: Export using ReportLab from JSON slide data ---
        st.markdown("---")
        st.subheader("Optional: Enter slide data for ReportLab PDF export")
        slide_data_raw = st.text_area(
            "Enter slides as JSON list, e.g.:\n"
            "[{'title': 'Slide 1', 'bullets': ['Point 1', 'Point 2']}, {'title': 'Slide 2', 'bullets': ['Point A']}]", 
            height=150
        )

        slides_for_pdf = []
        if slide_data_raw.strip():
            try:
                slides_for_pdf = json.loads(slide_data_raw)
            except Exception as e:
                st.error(f"Invalid JSON for slides: {e}")

        if st.button("Export to PDF (ReportLab)"):
            if not slides_for_pdf:
                st.error("Please provide slide data in JSON format for ReportLab PDF export.")
            else:
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmpf:
                        tmp_path = tmpf.name
                    create_pdf(file_name.replace(".pdf", ""), slides_for_pdf, tmp_path)

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
                    try:
                        if os.path.exists(tmp_path):
                            os.remove(tmp_path)
                    except Exception:
                        pass

    else:
        st.info("Generate HTML to see a preview and export to PDF.")
