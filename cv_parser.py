"""
Utility to parse existing CV files (PDF, DOCX, TXT) into structured text
that can be used by the AI generator.
"""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def parse_cv(file_path: str) -> str:
    """
    Parse a CV file and return its text content.
    Supports: .txt, .md, .pdf, .docx
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"CV file not found: {file_path}")

    ext = path.suffix.lower()

    if ext in [".txt", ".md"]:
        return path.read_text(encoding="utf-8")

    elif ext == ".pdf":
        return _parse_pdf(path)

    elif ext == ".docx":
        return _parse_docx(path)

    else:
        raise ValueError(f"Unsupported file format: {ext}. Use PDF, DOCX, TXT, or MD.")


def _parse_pdf(path: Path) -> str:
    """Extract text from PDF using pdfplumber."""
    try:
        import pdfplumber

        text_parts = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)

        return "\n\n".join(text_parts)

    except ImportError:
        logger.warning("pdfplumber not installed. Install with: pip install pdfplumber")
        return f"[PDF file at {path} - install pdfplumber to extract text]"


def _parse_docx(path: Path) -> str:
    """Extract text from DOCX using python-docx."""
    try:
        from docx import Document

        doc = Document(str(path))
        text_parts = []

        for para in doc.paragraphs:
            if para.text.strip():
                text_parts.append(para.text)

        # Also extract tables
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                if row_text:
                    text_parts.append(row_text)

        return "\n\n".join(text_parts)

    except ImportError:
        logger.warning("python-docx not installed. Install with: pip install python-docx")
        return f"[DOCX file at {path} - install python-docx to extract text]"


def extract_profile_from_cv(cv_text: str) -> dict:
    """
    Use Gemini to extract structured profile data from CV text.
    Returns a dict that can be stored in UserProfile.
    """
    from config import GEMINI_API_KEY

    if not GEMINI_API_KEY:
        return {"raw_text": cv_text}

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GEMINI_API_KEY)

        prompt = f"""Extract structured profile information from this CV/resume text.
Return a JSON object with these fields:
- full_name (string)
- email (string)
- phone (string)
- location (string)
- linkedin_url (string, if present)
- github_url (string, if present)
- portfolio_url (string, if present)
- summary (string - professional summary, 2-3 sentences)
- skills (array of strings)
- experience (array of objects with: title, company, location, start_date, end_date, description, achievements[])
- education (array of objects with: degree, school, year, gpa)
- certifications (array of strings)

CV Text:
{cv_text[:5000]}

Output ONLY valid JSON, nothing else."""

        models_to_try = [
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-flash-latest",
            "gemini-3.8-flash",
        ]

        last_err = None
        for model_name in models_to_try:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.3,
                        max_output_tokens=3000,
                        response_mime_type="application/json",
                    ),
                )
                return json.loads(response.text)
            except Exception as ex:
                last_err = ex
                continue

        raise last_err

    except Exception as e:
        logger.error(f"CV extraction failed: {e}")
        return {"raw_text": cv_text}
