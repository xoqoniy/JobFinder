# 🚀 JobFinder — Autonomous Job Application System

An AI-powered tool that finds, tailors, and applies to jobs across LinkedIn, Indeed, Glassdoor, and RemoteOK — all running on your Windows 11 laptop for **free**.

## ✨ Features

- **🔍 Multi-Platform Job Scraping** — LinkedIn, Indeed, Glassdoor, RemoteOK
- **🤖 AI-Powered CV & Cover Letter Generation** — Google Gemini API (free tier)
- **📝 Browser-Based Auto-Apply** — Playwright-based form filling with human-like behavior
- **✉️ Email Automation** — Follow-up emails via Gmail SMTP
- **📊 Beautiful Dashboard** — Dark-mode web UI to control everything
- **🔒 Safety First** — Dry-run mode, review mode, rate limiting, CAPTCHA detection
- **📸 Audit Trail** — Screenshots of every automation step
- **🆓 100% Free** — No paid APIs, no cloud costs

## 🚀 Quick Start

### 1. Install Python dependencies

```powershell
cd D:\JobFinder
pip install -r requirements.txt
```

### 2. Install browser for automation

```powershell
playwright install chromium
```

### 3. Run the setup wizard

```powershell
python run.py --setup
```

This will walk you through:
- Setting up your free Gemini API key
- Configuring LinkedIn credentials (optional)
- Setting up Gmail for follow-ups (optional)
- Choosing safety settings

### 4. Start the dashboard

```powershell
python run.py
```

Open **http://localhost:5000** in your browser.

### 5. Set up your profile

1. Go to **Profile** → fill in your details
2. Upload your existing CV (PDF, DOCX, or TXT)
3. Go to **Search Config** → define what jobs to look for

### 6. Start finding jobs!

- Click **"Scrape Jobs Now"** on the dashboard
- Review found jobs in the **Jobs** tab
- Click **"Generate CV"** on any job to create tailored documents
- Review the generated CV & cover letter
- Click **"Apply"** when ready (or enable auto-apply)

## ⚙️ Running Modes

```powershell
# Dashboard only (manual control)
python run.py

# Dashboard + autonomous engine
python run.py --auto

# Just scrape jobs (no dashboard)
python run.py --scrape-only

# First-time setup
python run.py --setup

# Custom port
python run.py --port 8080
```

## 🔒 Safety Features

| Feature | Default | Description |
|---------|---------|-------------|
| **Dry Run** | ✅ ON | Simulates applications without actually submitting |
| **Review Mode** | ✅ ON | Requires manual approval before each application |
| **Rate Limiting** | 10/hour | Max applications per hour |
| **CAPTCHA Pause** | Auto | Pauses and notifies you when CAPTCHA detected |
| **Screenshots** | Auto | Every step is captured for audit trail |

Change these in your `.env` file:

```env
DRY_RUN=true          # Set to false for real applications
REVIEW_MODE=true      # Set to false for fully autonomous
MAX_APPLICATIONS_PER_HOUR=10
HEADLESS_BROWSER=false # Set to true to hide the browser
```

## 🔑 API Keys & Credentials

### Google Gemini API (Required, Free)
1. Go to [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Create a new API key
3. Add to `.env`: `GEMINI_API_KEY=your_key_here`

Free tier: 15 requests/minute, 1M tokens/day — more than enough.

### Gmail App Password (Optional, for emails)
1. Enable 2FA on your Google account
2. Go to [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Create an app password for "Mail"
4. Add to `.env`:
   ```
   EMAIL_ADDRESS=your@gmail.com
   EMAIL_APP_PASSWORD=your_app_password
   ```

### LinkedIn Credentials (Optional, for auto-apply)
```
LINKEDIN_EMAIL=your_linkedin_email
LINKEDIN_PASSWORD=your_linkedin_password
```

## 📁 Project Structure

```
JobFinder/
├── run.py              # Main entry point & setup wizard
├── config.py           # Configuration & environment loading
├── database.py         # SQLAlchemy models & DB init
├── scrapers.py         # Multi-platform job scrapers
├── generator.py        # AI-powered CV & letter generation
├── applicator.py       # Playwright browser automation
├── emailer.py          # Email sending & follow-ups
├── engine.py           # Main orchestration engine
├── cv_parser.py        # CV file parsing utility
├── requirements.txt    # Python dependencies
├── .env.example        # Environment template
├── dashboard/
│   ├── app.py          # Flask web application
│   ├── templates/      # HTML templates
│   └── static/         # CSS & assets
├── my_cv/              # Drop your CV here
├── generated_docs/     # AI-generated CVs & letters
├── screenshots/        # Automation audit trail
└── browser_data/       # Persistent browser sessions
```

## ⚠️ Important Disclaimers

1. **Terms of Service**: Automating LinkedIn/Indeed may violate their TOS. Use at your own risk. Accounts could be flagged or suspended.
2. **CAPTCHAs**: The tool detects CAPTCHAs and pauses for manual solving. Fully automated CAPTCHA bypass is not included.
3. **Responsibility**: You are responsible for all applications submitted. Always review generated documents before enabling auto-apply.
4. **Rate Limiting**: The tool includes built-in rate limiting to minimize detection risk. Don't increase limits beyond recommended values.

## 🆓 Free Cloud Deployment (Optional)

If you want to run this 24/7 without keeping your laptop on:

### PythonAnywhere (Free tier)
1. Create account at [pythonanywhere.com](https://www.pythonanywhere.com)
2. Upload the project files
3. Set up a web app pointing to `dashboard/app.py`
4. Note: Free tier doesn't support Playwright (browser automation)

### Google Cloud Free Tier
1. Get always-free `e2-micro` VM
2. Install Python + dependencies
3. Run with `python run.py --auto`

### GitHub Codespaces
1. Fork this repo
2. Open in Codespaces (60 hrs/month free)
3. Run `python run.py`

## License

MIT — use freely, apply responsibly.
