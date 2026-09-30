"""
AI-powered CV and Cover Letter generator using Google Gemini API (free tier).
Generates tailored documents for each job posting based on user profile.
"""
import json
import logging
import datetime
from pathlib import Path

from google import genai
from google.genai import types

from config import GEMINI_API_KEY, GENERATED_DOCS_DIR
from database import Job, Application, UserProfile, ActivityLog, get_session

logger = logging.getLogger(__name__)


def _get_client():
    """Get configured Gemini client."""
    if not GEMINI_API_KEY:
        raise ValueError(
            "GEMINI_API_KEY not set. Get a free key at https://aistudio.google.com/apikey"
        )
    return genai.Client(api_key=GEMINI_API_KEY)


FALLBACK_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-flash-latest",
    "gemini-3.8-flash",
]


def _call_gemini(client, prompt: str, config=None):
    """Call Gemini with automatic model fallback on temporary high demand / rate limits."""
    last_error = None
    for model_name in FALLBACK_MODELS:
        try:
            if config:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=config,
                )
            else:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
            return response
        except Exception as e:
            last_error = e
            logger.warning(f"Model {model_name} failed ({e}), trying next fallback model...")
            continue
    raise last_error


def _get_user_profile() -> dict:
    """Load user profile from database, auto-seeding if empty."""
    from database import init_db
    db = get_session()
    try:
        profile = db.query(UserProfile).first()
        if not profile:
            init_db()
            profile = db.query(UserProfile).first()
        if not profile:
            return {}
        return {
            "full_name": profile.full_name,
            "email": profile.email,
            "phone": profile.phone,
            "location": profile.location,
            "linkedin_url": profile.linkedin_url,
            "github_url": profile.github_url,
            "portfolio_url": profile.portfolio_url,
            "summary": profile.summary,
            "skills": json.loads(profile.skills) if profile.skills else [],
            "experience": json.loads(profile.experience) if profile.experience else [],
            "education": json.loads(profile.education) if profile.education else [],
            "certifications": json.loads(profile.certifications) if profile.certifications else [],
        }
    finally:
        db.close()


def _load_base_cv() -> str:
    """Load the base CV text if available."""
    from cv_parser import parse_cv
    db = get_session()
    try:
        profile = db.query(UserProfile).first()
        if profile and profile.base_cv_path:
            cv_path = Path(profile.base_cv_path)
            if cv_path.exists():
                try:
                    return parse_cv(str(cv_path))
                except Exception as e:
                    logger.warning(f"Failed to parse base CV: {e}")
        # Also check current directory for SafarmurodAshurovCV.pdf or any pdf
        for candidate in ["SafarmurodAshurovCV.pdf", "my_cv.pdf", "cv.pdf"]:
            if Path(candidate).exists():
                try:
                    return parse_cv(candidate)
                except Exception:
                    pass
        return ""
    finally:
        db.close()


def generate_cv(job: Job, style: str = "professional") -> str:
    """
    Generate a tailored CV/resume for a specific job posting.

    Args:
        job: The Job object with title, company, description.
        style: CV style - 'professional', 'modern', 'minimal', 'technical'.

    Returns:
        Generated CV content as markdown string.
    """
    profile = _get_user_profile()
    base_cv = _load_base_cv()

    if not profile and not base_cv:
        raise ValueError("No user profile or base CV found. Please set up your profile first.")

    client = _get_client()

    prompt = f"""You are an expert CV/resume writer specializing in tech and software engineering roles.
Generate a highly tailored, ATS-optimized CV for the following job posting.

=== JOB DETAILS ===
Title: {job.title}
Company: {job.company}
Location: {job.location}
Description: {job.description[:3000] if job.description else 'Not available'}

=== CANDIDATE PROFILE ===
{json.dumps(profile, indent=2) if profile else 'See base CV below'}

=== BASE CV (if available) ===
{base_cv[:3000] if base_cv else 'Not provided - generate from profile data'}

=== INSTRUCTIONS ===
1. Tailor the CV specifically to this job posting
2. Highlight relevant skills and experience that match the job requirements
3. Use strong action verbs and quantified achievements
4. Keep it to 1-2 pages worth of content
5. Use a {style} format
6. Include relevant keywords from the job description for ATS optimization
7. Format in clean Markdown with proper sections:
   - Header (name, contact info)
   - Professional Summary (2-3 sentences, tailored)
   - Technical Skills (categorized, matching job requirements)
   - Work Experience (reverse chronological, with bullet points)
   - Education
   - Certifications/Projects (if relevant)
8. Do NOT fabricate experience or skills the candidate doesn't have
9. DO reframe and emphasize existing experience to match the job

Output ONLY the CV content in Markdown format, nothing else."""

    try:
        response = _call_gemini(
            client,
            prompt,
            config=types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=4000,
            ),
        )
        cv_content = response.text.strip()
        logger.info(f"Generated CV for {job.title} @ {job.company}")
        return cv_content

    except Exception as e:
        logger.error(f"CV generation failed: {e}")
        raise


def generate_cover_letter(job: Job, tone: str = "professional") -> str:
    """
    Generate a tailored cover letter for a specific job posting.

    Args:
        job: The Job object.
        tone: Letter tone - 'professional', 'enthusiastic', 'concise', 'creative'.

    Returns:
        Generated cover letter as markdown string.
    """
    profile = _get_user_profile()
    base_cv = _load_base_cv()

    if not profile and not base_cv:
        raise ValueError("No user profile or base CV found. Please set up your profile first.")

    client = _get_client()

    prompt = f"""You are an expert cover letter writer for tech and software engineering roles.
Write a compelling, personalized cover letter for the following job.

=== JOB DETAILS ===
Title: {job.title}
Company: {job.company}
Location: {job.location}
Description: {job.description[:3000] if job.description else 'Not available'}

=== CANDIDATE PROFILE ===
{json.dumps(profile, indent=2) if profile else 'See base CV below'}

=== BASE CV ===
{base_cv[:2000] if base_cv else 'Not provided'}

=== INSTRUCTIONS ===
1. Tone: {tone}
2. Length: 250-400 words (concise but impactful)
3. Structure:
   - Opening: Hook that shows genuine interest in the specific role/company
   - Body: 2-3 paragraphs connecting your experience to their needs
   - Closing: Clear call to action
4. Show you've researched the company (reference their mission/products if possible from the job description)
5. Highlight 2-3 specific achievements that directly relate to the job requirements
6. Do NOT use generic phrases like "I am writing to express my interest..."
7. Do NOT fabricate experience
8. Include the candidate's name and contact info at the top
9. Use today's date: {datetime.date.today().strftime('%B %d, %Y')}
10. Address to "Hiring Manager" if no specific name is available

Output ONLY the cover letter in Markdown format, nothing else."""

    try:
        response = _call_gemini(
            client,
            prompt,
            config=types.GenerateContentConfig(
                temperature=0.8,
                max_output_tokens=2000,
            ),
        )
        letter_content = response.text.strip()
        logger.info(f"Generated cover letter for {job.title} @ {job.company}")
        return letter_content

    except Exception as e:
        logger.error(f"Cover letter generation failed: {e}")
        raise


def generate_email(job: Job, email_type: str = "follow_up") -> dict:
    """
    Generate a follow-up or networking email for a job application.

    Args:
        job: The Job object.
        email_type: 'follow_up', 'networking', 'thank_you'.

    Returns:
        Dict with 'subject' and 'body' keys.
    """
    profile = _get_user_profile()
    client = _get_client()

    type_instructions = {
        "follow_up": "Write a professional follow-up email checking on application status. Keep it brief and polite. Sent 1 week after applying.",
        "networking": "Write a networking email to connect with someone at the company. Ask for an informational conversation, not a job directly.",
        "thank_you": "Write a thank-you email after an interview. Reference specific conversation points (use placeholders like [TOPIC DISCUSSED]).",
    }

    prompt = f"""Generate a professional email for a job application.

Job: {job.title} at {job.company}
Email Type: {email_type}
Candidate: {profile.get('full_name', 'Candidate')}

Instructions: {type_instructions.get(email_type, type_instructions['follow_up'])}

Requirements:
- Subject line should be clear and professional
- Body should be 100-200 words
- Include proper greeting and sign-off
- Use the candidate's name in the sign-off

Output as JSON with keys "subject" and "body". Output ONLY valid JSON, nothing else."""

    try:
        response = _call_gemini(
            client,
            prompt,
            config=types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=1000,
                response_mime_type="application/json",
            ),
        )

        result = json.loads(response.text)
        logger.info(f"Generated {email_type} email for {job.title} @ {job.company}")
        return result

    except Exception as e:
        logger.error(f"Email generation failed: {e}")
        raise


def generate_and_save(job_id: int) -> Application:
    """
    Generate CV + cover letter for a job and save to database + files.

    Args:
        job_id: The database ID of the job.

    Returns:
        The created/updated Application object.
    """
    db = get_session()
    try:
        job = db.query(Job).get(job_id)
        if not job:
            raise ValueError(f"Job #{job_id} not found")

        # Create or get application
        app = db.query(Application).filter_by(job_id=job_id).first()
        if not app:
            app = Application(job_id=job_id, status="pending")
            db.add(app)
            db.flush()

        job.status = "generating"
        db.commit()

        # Generate CV
        cv_content = generate_cv(job)
        cv_filename = f"cv_{job.platform}_{job.id}_{job.company[:20].replace(' ', '_')}.md"
        cv_path = GENERATED_DOCS_DIR / cv_filename
        cv_path.write_text(cv_content, encoding="utf-8")

        app.cv_content = cv_content
        app.cv_path = str(cv_path)
        app.status = "cv_generated"
        db.commit()

        # Generate Cover Letter
        letter_content = generate_cover_letter(job)
        letter_filename = f"letter_{job.platform}_{job.id}_{job.company[:20].replace(' ', '_')}.md"
        letter_path = GENERATED_DOCS_DIR / letter_filename
        letter_path.write_text(letter_content, encoding="utf-8")

        app.cover_letter_content = letter_content
        app.cover_letter_path = str(letter_path)
        app.status = "ready"
        job.status = "queued"
        db.commit()

        db.add(ActivityLog(
            action="Documents generated",
            details=f"CV and cover letter for {job.title} @ {job.company}",
            level="success"
        ))
        db.commit()

        logger.info(f"Generated and saved documents for Job #{job_id}")
        return app

    except Exception as e:
        db.rollback()
        if app:
            app.status = "failed"
            app.error_message = str(e)
        if job:
            job.status = "failed"
        db.commit()
        logger.error(f"Document generation failed for Job #{job_id}: {e}")
        raise
    finally:
        db.close()


def rank_jobs(query: str, top_n: int = 20) -> list[int]:
    """
    Use Gemini to rank/score jobs against user profile for best matches.
    Returns list of job IDs sorted by relevance.
    """
    db = get_session()
    try:
        profile = _get_user_profile()
        base_cv = _load_base_cv()
        jobs = db.query(Job).filter(Job.status == "new").limit(50).all()

        if not jobs:
            return []

        # Build a summary of jobs for batch scoring
        job_summaries = []
        for j in jobs:
            job_summaries.append({
                "id": j.id,
                "title": j.title,
                "company": j.company,
                "location": j.location,
                "description": (j.description or "")[:500],
            })

        prompt = f"""You are an expert tech recruiter and job matching specialist.
Score each job from 0 to 100 based on the candidate's exact profile and level:

=== CANDIDATE PROFILE & LEVEL ===
- Stage: Undergraduate Student / Junior / Entry-Level Developer (0-2 years experience).
- Target Roles: Junior Software Engineer, Junior Full Stack Developer, Junior Frontend Developer, Junior Backend Developer, or Software / AI Intern (Paid).
- Location Rules:
  * Remote positions: EXCELLENT match.
  * Hybrid or On-site: ONLY in Budapest, Hungary. If hybrid/onsite in other cities/countries, score 0.
- Seniority Rules:
  * If the job title or description is for Senior, Lead, Staff, Principal, Architect, Director, Manager, or requires 4+ years of experience: SCORE 0 (DISQUALIFIED).
  * If the internship is unpaid/volunteer: SCORE 0 (DISQUALIFIED).
  * Target sweet spot: Junior, Entry-Level, Associate, Graduate, Intern (Paid), or Software Engineer I.

=== CANDIDATE DETAILS ===
{json.dumps(profile, indent=2) if profile else base_cv[:2000]}
Search query: {query}

=== JOBS TO SCORE ===
{json.dumps(job_summaries, indent=2)}

Scoring Guide:
- 85-100: Junior / Entry / Intern role matching tech stack (Python, .NET, JS/React, AI, SQL) and location (Remote or Budapest).
- 50-84: Generic entry/junior tech role with partial stack overlap.
- 0: Senior / Lead / Staff / Architect / Unpaid intern / Non-Budapest physical location.

Output ONLY a JSON array of objects with "id" and "score" keys, sorted by score descending.
Example: [{{"id": 1, "score": 92}}, {{"id": 3, "score": 81}}]"""

        response = _call_gemini(
            client,
            prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=2000,
                response_mime_type="application/json",
            ),
        )

        scores = json.loads(response.text)

        # Update scores in database
        for entry in scores:
            job = db.query(Job).get(entry["id"])
            if job:
                job.match_score = entry["score"]
        db.commit()

        # Return top N job IDs
        sorted_ids = [s["id"] for s in scores[:top_n]]
        return sorted_ids

    except Exception as e:
        logger.error(f"Job ranking failed: {e}")
        return [j.id for j in jobs[:top_n]]  # fallback: return unranked
    finally:
        db.close()
