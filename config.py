"""
JobFinder - Autonomous Job Application System
Configuration and shared settings.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Paths
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "jobfinder.db"
SCREENSHOTS_DIR = BASE_DIR / "screenshots"
GENERATED_DOCS_DIR = BASE_DIR / "generated_docs"
BROWSER_DATA_DIR = BASE_DIR / "browser_data"
TEMPLATES_DIR = BASE_DIR / "dashboard" / "templates"
STATIC_DIR = BASE_DIR / "dashboard" / "static"
CV_DIR = BASE_DIR / "my_cv"

# Create directories
for d in [SCREENSHOTS_DIR, GENERATED_DOCS_DIR, BROWSER_DATA_DIR, CV_DIR]:
    d.mkdir(exist_ok=True)

# API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Email
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS", "")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD", "")

# Platform Credentials
LINKEDIN_EMAIL = os.getenv("LINKEDIN_EMAIL", "")
LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD", "")
INDEED_EMAIL = os.getenv("INDEED_EMAIL", "")
INDEED_PASSWORD = os.getenv("INDEED_PASSWORD", "")

# Application Settings
MAX_APPLICATIONS_PER_HOUR = int(os.getenv("MAX_APPLICATIONS_PER_HOUR", "10"))
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
REVIEW_MODE = os.getenv("REVIEW_MODE", "true").lower() == "true"
HEADLESS_BROWSER = os.getenv("HEADLESS_BROWSER", "false").lower() == "true"

# Job Search Defaults
DEFAULT_JOB_TITLE = os.getenv("JOB_TITLE", "Software Engineer")
DEFAULT_JOB_LOCATION = os.getenv("JOB_LOCATION", "Remote")
DEFAULT_EXPERIENCE_LEVEL = os.getenv("EXPERIENCE_LEVEL", "mid")

# Dashboard
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "5000"))
DASHBOARD_SECRET_KEY = os.getenv("DASHBOARD_SECRET_KEY", "dev-secret-key-change-me")

# Rate Limiting
MIN_DELAY_BETWEEN_ACTIONS = 3  # seconds
MAX_DELAY_BETWEEN_ACTIONS = 8  # seconds
PAGE_LOAD_TIMEOUT = 30000  # milliseconds
