"""
Browser-based application bot using Playwright.
Automates form filling and job applications on LinkedIn, Indeed, etc.
Includes CAPTCHA detection and human-like interaction patterns.
"""
import time
import random
import json
import logging
import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext

from config import (
    LINKEDIN_EMAIL, LINKEDIN_PASSWORD, INDEED_EMAIL, INDEED_PASSWORD,
    HEADLESS_BROWSER, BROWSER_DATA_DIR, SCREENSHOTS_DIR,
    MIN_DELAY_BETWEEN_ACTIONS, MAX_DELAY_BETWEEN_ACTIONS,
    PAGE_LOAD_TIMEOUT, DRY_RUN
)
from database import Job, Application, ActivityLog, UserProfile, get_session

logger = logging.getLogger(__name__)


class CaptchaDetected(Exception):
    """Raised when a CAPTCHA is detected on the page."""
    pass


class ApplicationBot:
    """
    Manages browser automation for job applications.
    Uses persistent browser context to maintain login sessions.
    """

    def __init__(self, headless: bool = None):
        self.headless = headless if headless is not None else HEADLESS_BROWSER
        self.playwright = None
        self.browser: Browser = None
        self.context: BrowserContext = None
        self.page: Page = None
        self._screenshot_count = 0

    def start(self):
        """Launch browser with persistent context."""
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-sandbox",
            ]
        )
        self.context = self.browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            storage_state=self._get_storage_state_path(),
        )
        self.context.set_default_timeout(PAGE_LOAD_TIMEOUT)
        self.page = self.context.new_page()

        # Stealth: remove webdriver flag
        self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            window.chrome = { runtime: {} };
        """)

        logger.info("Browser started")

    def stop(self):
        """Close browser and save state."""
        if self.context:
            try:
                storage_path = self._get_storage_state_path()
                self.context.storage_state(path=str(storage_path))
            except Exception:
                pass
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        logger.info("Browser stopped")

    def _get_storage_state_path(self) -> str:
        """Get path for browser storage state (cookies, localStorage)."""
        path = BROWSER_DATA_DIR / "storage_state.json"
        if path.exists():
            return str(path)
        return None  # No existing state

    def _human_delay(self, min_s=None, max_s=None):
        """Random delay to mimic human behavior."""
        min_s = min_s or MIN_DELAY_BETWEEN_ACTIONS
        max_s = max_s or MAX_DELAY_BETWEEN_ACTIONS
        time.sleep(random.uniform(min_s, max_s))

    def _human_type(self, selector: str, text: str):
        """Type text with human-like delays between keystrokes."""
        element = self.page.locator(selector)
        element.click()
        time.sleep(random.uniform(0.1, 0.3))
        for char in text:
            element.press(char if len(char) == 1 else char)
            time.sleep(random.uniform(0.02, 0.12))

    def _take_screenshot(self, label: str = "") -> str:
        """Take a screenshot for audit trail."""
        self._screenshot_count += 1
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"step_{self._screenshot_count:03d}_{label}_{ts}.png"
        path = SCREENSHOTS_DIR / filename
        self.page.screenshot(path=str(path), full_page=False)
        logger.info(f"Screenshot saved: {filename}")
        return str(path)

    def _check_captcha(self):
        """Detect common CAPTCHA challenges."""
        captcha_indicators = [
            "iframe[src*='captcha']",
            "iframe[src*='recaptcha']",
            "iframe[src*='hcaptcha']",
            "#captcha",
            ".g-recaptcha",
            "[data-captcha]",
            "iframe[title*='challenge']",
            "div[class*='captcha']",
        ]
        for selector in captcha_indicators:
            try:
                if self.page.locator(selector).count() > 0:
                    screenshot = self._take_screenshot("captcha_detected")
                    raise CaptchaDetected(
                        f"CAPTCHA detected! Screenshot: {screenshot}. "
                        "Please solve it manually in the browser window."
                    )
            except CaptchaDetected:
                raise
            except Exception:
                continue

    def _wait_for_captcha_resolution(self, timeout_seconds: int = 300):
        """
        Wait for user to manually solve CAPTCHA.
        Shows a notification and polls until CAPTCHA is gone or timeout.
        """
        logger.warning("⚠️  CAPTCHA detected! Please solve it in the browser window.")
        logger.warning(f"   Waiting up to {timeout_seconds}s for manual resolution...")

        start = time.time()
        while time.time() - start < timeout_seconds:
            time.sleep(5)
            try:
                self._check_captcha()
                logger.info("✅ CAPTCHA resolved! Continuing...")
                return True
            except CaptchaDetected:
                remaining = int(timeout_seconds - (time.time() - start))
                if remaining % 30 == 0:
                    logger.warning(f"   Still waiting... {remaining}s remaining")
                continue

        logger.error("❌ CAPTCHA timeout. Skipping this application.")
        return False

    # ─────────────────────────────────────────
    # LinkedIn Application
    # ─────────────────────────────────────────

    def linkedin_login(self):
        """Log into LinkedIn."""
        if not LINKEDIN_EMAIL or not LINKEDIN_PASSWORD:
            raise ValueError("LinkedIn credentials not configured in .env")

        self.page.goto("https://www.linkedin.com/login")
        self._human_delay(1, 3)

        # Check if already logged in
        if "feed" in self.page.url:
            logger.info("Already logged into LinkedIn")
            return

        self._check_captcha()

        self._human_type("#username", LINKEDIN_EMAIL)
        self._human_delay(0.5, 1.5)
        self._human_type("#password", LINKEDIN_PASSWORD)
        self._human_delay(0.5, 1.5)

        self.page.click("button[type='submit']")
        self._human_delay(3, 5)

        self._take_screenshot("linkedin_login")

        try:
            self._check_captcha()
        except CaptchaDetected:
            self._wait_for_captcha_resolution()

        # Verify login
        if "feed" in self.page.url or "mynetwork" in self.page.url:
            logger.info("LinkedIn login successful")
            # Save cookies
            storage_path = BROWSER_DATA_DIR / "storage_state.json"
            self.context.storage_state(path=str(storage_path))
        else:
            self._take_screenshot("linkedin_login_issue")
            logger.warning(f"LinkedIn login may have issues. Current URL: {self.page.url}")

    def linkedin_easy_apply(self, job: Job, application: Application) -> bool:
        """
        Apply to a LinkedIn Easy Apply job.
        Returns True if successful, False otherwise.
        """
        screenshots = []
        db = get_session()

        try:
            # Navigate to job page
            self.page.goto(job.url)
            self._human_delay(2, 4)
            screenshots.append(self._take_screenshot("job_page"))

            self._check_captcha()

            # Look for Easy Apply button
            easy_apply_btn = self.page.locator(
                "button.jobs-apply-button, "
                "button[aria-label*='Easy Apply'], "
                "button:has-text('Easy Apply')"
            )

            if easy_apply_btn.count() == 0:
                logger.warning(f"No Easy Apply button found for {job.title}")
                return False

            if DRY_RUN:
                logger.info(f"[DRY RUN] Would click Easy Apply for: {job.title}")
                screenshots.append(self._take_screenshot("dry_run_would_apply"))
                application.screenshot_paths = json.dumps(screenshots)
                application.status = "ready"
                db.merge(application)
                db.commit()
                return True

            easy_apply_btn.first.click()
            self._human_delay(2, 4)
            screenshots.append(self._take_screenshot("easy_apply_modal"))

            # Handle multi-step application form
            max_steps = 10
            for step in range(max_steps):
                self._check_captcha()

                # Fill in contact info if needed
                self._fill_linkedin_form_fields()
                self._human_delay(1, 2)

                # Check for "Submit application" button
                submit_btn = self.page.locator(
                    "button[aria-label*='Submit application'], "
                    "button:has-text('Submit application')"
                )
                if submit_btn.count() > 0:
                    screenshots.append(self._take_screenshot(f"step_{step}_submit"))
                    submit_btn.first.click()
                    self._human_delay(2, 4)
                    screenshots.append(self._take_screenshot("submitted"))

                    # Update records
                    application.status = "submitted"
                    application.applied_at = datetime.datetime.utcnow()
                    application.screenshot_paths = json.dumps(screenshots)
                    job.status = "applied"
                    db.merge(application)
                    db.merge(job)
                    db.add(ActivityLog(
                        action="Applied via LinkedIn Easy Apply",
                        details=f"{job.title} @ {job.company}",
                        level="success"
                    ))
                    db.commit()
                    logger.info(f"✅ Applied to {job.title} @ {job.company}")
                    return True

                # Click "Next" button if present
                next_btn = self.page.locator(
                    "button[aria-label*='Continue'], "
                    "button[aria-label*='Next'], "
                    "button:has-text('Next'), "
                    "button:has-text('Review')"
                )
                if next_btn.count() > 0:
                    screenshots.append(self._take_screenshot(f"step_{step}"))
                    next_btn.first.click()
                    self._human_delay(1, 3)
                else:
                    break

            logger.warning(f"Could not complete LinkedIn application for {job.title}")
            application.status = "failed"
            application.error_message = "Could not find Submit button after all steps"
            application.screenshot_paths = json.dumps(screenshots)
            db.merge(application)
            db.commit()
            return False

        except CaptchaDetected as e:
            logger.warning(f"CAPTCHA during LinkedIn application: {e}")
            resolved = self._wait_for_captcha_resolution()
            if resolved:
                return self.linkedin_easy_apply(job, application)
            application.status = "failed"
            application.error_message = "CAPTCHA not resolved"
            db.merge(application)
            db.commit()
            return False

        except Exception as e:
            logger.error(f"LinkedIn application error: {e}")
            screenshots.append(self._take_screenshot("error"))
            application.status = "failed"
            application.error_message = str(e)
            application.screenshot_paths = json.dumps(screenshots)
            db.merge(application)
            db.commit()
            return False

        finally:
            db.close()

    def _fill_linkedin_form_fields(self):
        """Attempt to fill common LinkedIn Easy Apply form fields."""
        db = get_session()
        try:
            profile = db.query(UserProfile).first()
            if not profile:
                return

            # Phone number
            phone_input = self.page.locator("input[id*='phone'], input[name*='phone']")
            if phone_input.count() > 0 and not phone_input.first.input_value():
                phone_input.first.fill(profile.phone or "")

            # Email
            email_input = self.page.locator(
                "input[id*='email'][type='email'], input[name*='email']"
            )
            if email_input.count() > 0 and not email_input.first.input_value():
                email_input.first.fill(profile.email or "")

            # City/Location
            city_input = self.page.locator("input[id*='city'], input[name*='city']")
            if city_input.count() > 0 and not city_input.first.input_value():
                city_input.first.fill(profile.location or "")

        except Exception as e:
            logger.debug(f"Form fill helper: {e}")
        finally:
            db.close()

    # ─────────────────────────────────────────
    # Indeed Application
    # ─────────────────────────────────────────

    def indeed_login(self):
        """Log into Indeed."""
        if not INDEED_EMAIL or not INDEED_PASSWORD:
            raise ValueError("Indeed credentials not configured in .env")

        self.page.goto("https://secure.indeed.com/auth")
        self._human_delay(2, 4)

        if "myjobs" in self.page.url or "jobs" in self.page.url:
            logger.info("Already logged into Indeed")
            return

        self._check_captcha()

        # Indeed uses email-first then password
        email_input = self.page.locator("input[type='email'], #ifl-InputFormField-3")
        if email_input.count() > 0:
            email_input.first.fill(INDEED_EMAIL)
            self._human_delay(0.5, 1.5)

            submit_btn = self.page.locator("button[type='submit']")
            if submit_btn.count() > 0:
                submit_btn.first.click()
                self._human_delay(2, 4)

        self._check_captcha()

        password_input = self.page.locator("input[type='password']")
        if password_input.count() > 0:
            password_input.first.fill(INDEED_PASSWORD)
            self._human_delay(0.5, 1.5)

            submit_btn = self.page.locator("button[type='submit']")
            if submit_btn.count() > 0:
                submit_btn.first.click()
                self._human_delay(3, 5)

        self._take_screenshot("indeed_login")

        try:
            self._check_captcha()
        except CaptchaDetected:
            self._wait_for_captcha_resolution()

        # Save cookies
        storage_path = BROWSER_DATA_DIR / "storage_state.json"
        self.context.storage_state(path=str(storage_path))
        logger.info("Indeed login completed")

    def indeed_apply(self, job: Job, application: Application) -> bool:
        """Apply to an Indeed job listing."""
        screenshots = []
        db = get_session()

        try:
            self.page.goto(job.url)
            self._human_delay(2, 4)
            screenshots.append(self._take_screenshot("indeed_job_page"))

            self._check_captcha()

            # Look for Apply button
            apply_btn = self.page.locator(
                "button#indeedApplyButton, "
                "a.indeed-apply-button, "
                "button:has-text('Apply now'), "
                "a:has-text('Apply now')"
            )

            if apply_btn.count() == 0:
                # Check for external apply link
                ext_link = self.page.locator("a:has-text('Apply on company site')")
                if ext_link.count() > 0:
                    logger.info(f"External application for {job.title} - saving link")
                    application.status = "review"
                    application.error_message = "External application - requires manual review"
                    db.merge(application)
                    db.commit()
                    return False
                return False

            if DRY_RUN:
                logger.info(f"[DRY RUN] Would apply on Indeed for: {job.title}")
                application.status = "ready"
                application.screenshot_paths = json.dumps(screenshots)
                db.merge(application)
                db.commit()
                return True

            apply_btn.first.click()
            self._human_delay(3, 5)
            screenshots.append(self._take_screenshot("indeed_apply_form"))

            # Handle Indeed's multi-step form
            max_steps = 8
            for step in range(max_steps):
                self._check_captcha()
                self._human_delay(1, 2)

                # Check for completion
                if "applied" in self.page.url.lower() or self.page.locator(
                    "div:has-text('Your application has been submitted')"
                ).count() > 0:
                    application.status = "submitted"
                    application.applied_at = datetime.datetime.utcnow()
                    application.screenshot_paths = json.dumps(screenshots)
                    job.status = "applied"
                    db.merge(application)
                    db.merge(job)
                    db.add(ActivityLog(
                        action="Applied via Indeed",
                        details=f"{job.title} @ {job.company}",
                        level="success"
                    ))
                    db.commit()
                    logger.info(f"✅ Applied to {job.title} @ {job.company} on Indeed")
                    return True

                # Continue/Submit buttons
                continue_btn = self.page.locator(
                    "button:has-text('Continue'), "
                    "button:has-text('Submit'), "
                    "button:has-text('Apply')"
                )
                if continue_btn.count() > 0:
                    screenshots.append(self._take_screenshot(f"indeed_step_{step}"))
                    continue_btn.first.click()
                    self._human_delay(2, 4)
                else:
                    break

            application.status = "failed"
            application.error_message = "Could not complete Indeed application flow"
            application.screenshot_paths = json.dumps(screenshots)
            db.merge(application)
            db.commit()
            return False

        except CaptchaDetected as e:
            logger.warning(f"CAPTCHA during Indeed application: {e}")
            resolved = self._wait_for_captcha_resolution()
            if resolved:
                return self.indeed_apply(job, application)
            application.status = "failed"
            application.error_message = "CAPTCHA not resolved"
            db.merge(application)
            db.commit()
            return False

        except Exception as e:
            logger.error(f"Indeed application error: {e}")
            screenshots.append(self._take_screenshot("indeed_error"))
            application.status = "failed"
            application.error_message = str(e)
            application.screenshot_paths = json.dumps(screenshots)
            db.merge(application)
            db.commit()
            return False

        finally:
            db.close()

    # ─────────────────────────────────────────
    # Generic Application Handler
    # ─────────────────────────────────────────

    def apply_to_job(self, job_id: int) -> bool:
        """
        Apply to a job based on its platform.
        Returns True if application was successful.
        """
        db = get_session()
        try:
            job = db.query(Job).get(job_id)
            if not job:
                logger.error(f"Job #{job_id} not found")
                return False

            application = db.query(Application).filter_by(job_id=job_id).first()
            if not application:
                logger.error(f"No application record for Job #{job_id}")
                return False

            if application.status == "submitted":
                logger.info(f"Job #{job_id} already applied")
                return True

            job.status = "applying"
            db.commit()

            if job.platform == "linkedin":
                self.linkedin_login()
                return self.linkedin_easy_apply(job, application)
            elif job.platform == "indeed":
                self.indeed_login()
                return self.indeed_apply(job, application)
            else:
                # For other platforms, just open the URL for manual application
                logger.info(f"Opening {job.platform} job for manual application: {job.url}")
                self.page.goto(job.url)
                self._take_screenshot(f"{job.platform}_manual")
                application.status = "review"
                application.error_message = f"Platform '{job.platform}' requires manual application"
                db.merge(application)
                db.commit()
                return False

        except Exception as e:
            logger.error(f"Application error for Job #{job_id}: {e}")
            return False
        finally:
            db.close()
