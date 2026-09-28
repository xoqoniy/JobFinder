#!/usr/bin/env python3
"""
JobFinder — Autonomous Job Application System
Main entry point. Starts the dashboard and optionally the engine.

Usage:
    python run.py                    # Start dashboard only
    python run.py --auto             # Start dashboard + autonomous engine
    python run.py --scrape-only      # Run one scrape cycle and exit
    python run.py --setup            # Interactive first-time setup
"""
import argparse
import sys
import json
import os
import shutil
from pathlib import Path

# Ensure the project root is in the Python path
sys.path.insert(0, str(Path(__file__).parent))


def setup():
    """Interactive first-time setup wizard."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm

    console = Console()

    console.print(Panel.fit(
        "[bold cyan]🚀 JobFinder — First Time Setup[/bold cyan]\n\n"
        "This wizard will help you configure JobFinder.\n"
        "You can always change settings later via the dashboard.",
        border_style="cyan"
    ))

    # Create .env from template
    env_path = Path(".env")
    if not env_path.exists():
        template = Path(".env.example")
        if template.exists():
            shutil.copy(template, env_path)
            console.print("✅ Created .env from template")

    # Gemini API Key
    console.print("\n[bold]Step 1: Google Gemini API Key (Free)[/bold]")
    console.print("Get yours at: [link]https://aistudio.google.com/apikey[/link]")
    api_key = Prompt.ask("Enter your Gemini API key", default="skip")

    if api_key != "skip":
        _update_env("GEMINI_API_KEY", api_key)
        console.print("✅ API key saved")

    # LinkedIn
    console.print("\n[bold]Step 2: LinkedIn Credentials (Optional)[/bold]")
    if Confirm.ask("Configure LinkedIn automation?", default=False):
        li_email = Prompt.ask("LinkedIn email")
        li_pass = Prompt.ask("LinkedIn password", password=True)
        _update_env("LINKEDIN_EMAIL", li_email)
        _update_env("LINKEDIN_PASSWORD", li_pass)
        console.print("✅ LinkedIn credentials saved")

    # Email
    console.print("\n[bold]Step 3: Gmail for Follow-ups (Optional)[/bold]")
    console.print("Create an App Password: [link]https://myaccount.google.com/apppasswords[/link]")
    if Confirm.ask("Configure email sending?", default=False):
        email = Prompt.ask("Gmail address")
        app_pass = Prompt.ask("App password", password=True)
        _update_env("EMAIL_ADDRESS", email)
        _update_env("EMAIL_APP_PASSWORD", app_pass)
        console.print("✅ Email configured")

    # Safety settings
    console.print("\n[bold]Step 4: Safety Settings[/bold]")
    dry_run = Confirm.ask("Enable Dry Run mode? (no real applications)", default=True)
    review_mode = Confirm.ask("Enable Review mode? (manually approve each app)", default=True)
    _update_env("DRY_RUN", str(dry_run).lower())
    _update_env("REVIEW_MODE", str(review_mode).lower())

    # Initialize database
    from database import init_db
    init_db()
    console.print("✅ Database initialized")

    # Install Playwright browsers
    console.print("\n[bold]Step 5: Installing browser for automation...[/bold]")
    os.system("playwright install chromium")

    console.print(Panel.fit(
        "[bold green]✅ Setup Complete![/bold green]\n\n"
        "Next steps:\n"
        "1. Drop your CV into the [bold]my_cv/[/bold] folder\n"
        "2. Run [bold]python run.py[/bold] to start the dashboard\n"
        "3. Open [link]http://localhost:5000[/link]\n"
        "4. Fill in your Profile\n"
        "5. Configure Search settings\n"
        "6. Click Start Engine!",
        border_style="green"
    ))


def _update_env(key: str, value: str):
    """Update a key in the .env file."""
    env_path = Path(".env")
    if not env_path.exists():
        env_path.write_text("")

    lines = env_path.read_text().splitlines()
    found = False

    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            found = True
            break

    if not found:
        lines.append(f"{key}={value}")

    env_path.write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description="JobFinder — Autonomous Job Application System")
    parser.add_argument("--auto", action="store_true", help="Start engine in autonomous mode")
    parser.add_argument("--scrape-only", action="store_true", help="Run one scrape cycle and exit")
    parser.add_argument("--setup", action="store_true", help="Run first-time setup wizard")
    parser.add_argument("--port", type=int, default=5000, help="Dashboard port (default: 5000)")
    args = parser.parse_args()

    if args.setup:
        setup()
        return

    # Initialize database
    from database import init_db
    init_db()

    if args.scrape_only:
        # Just run scrapers and exit
        import logging
        logging.basicConfig(level=logging.INFO)
        from engine import engine
        results = engine.scrape_now()
        print(json.dumps(results, indent=2))
        return

    if args.auto:
        # Start engine in autonomous mode
        from engine import engine
        engine.start()

    # Start the dashboard
    os.environ["DASHBOARD_PORT"] = str(args.port)

    # Import app after setting env
    from dashboard.app import app
    app.run(host="0.0.0.0", port=args.port, debug=False)


if __name__ == "__main__":
    main()
