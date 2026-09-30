"""
Main orchestrator that ties together scraping, generation, and application.
Can run as a scheduled autonomous job or be triggered from the dashboard.
"""
import time
import json
import logging
import datetime
import threading
from pathlib import Path

from config import MAX_APPLICATIONS_PER_HOUR, DRY_RUN, REVIEW_MODE
from database import (
    Job, Application, SearchConfig, ActivityLog, UserProfile,
    get_session, init_db
)
from scrapers import scrape_all
from generator import generate_and_save, rank_jobs
from applicator import ApplicationBot
from emailer import send_follow_ups

logger = logging.getLogger(__name__)


class JobFinderEngine:
    """
    The main autonomous engine that orchestrates the entire job finding
    and application pipeline.
    """

    def __init__(self):
        self.bot: ApplicationBot = None
        self.is_running = False
        self._thread: threading.Thread = None
        self._stop_event = threading.Event()
        self.stats = {
            "jobs_scraped": 0,
            "documents_generated": 0,
            "applications_submitted": 0,
            "applications_failed": 0,
            "follow_ups_sent": 0,
            "started_at": None,
            "last_action": None,
        }

    def start(self, run_once: bool = False):
        """Start the autonomous engine in a background thread."""
        if self.is_running:
            logger.warning("Engine is already running")
            return

        init_db()
        self._stop_event.clear()
        self.is_running = True
        self.stats["started_at"] = datetime.datetime.utcnow().isoformat()

        if run_once:
            self._run_pipeline()
        else:
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            logger.info("🚀 JobFinder engine started in background")

    def stop(self):
        """Stop the autonomous engine."""
        logger.info("Stopping JobFinder engine...")
        self._stop_event.set()
        self.is_running = False

        if self.bot:
            try:
                self.bot.stop()
            except Exception:
                pass
            self.bot = None

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)

        logger.info("JobFinder engine stopped")

    def get_status(self) -> dict:
        """Get current engine status and stats."""
        db = get_session()
        try:
            total_jobs = db.query(Job).count()
            new_jobs = db.query(Job).filter_by(status="new").count()
            applied_jobs = db.query(Job).filter_by(status="applied").count()
            failed_jobs = db.query(Job).filter_by(status="failed").count()
            review_jobs = db.query(Job).filter_by(status="review").count()

            total_apps = db.query(Application).count()
            submitted_apps = db.query(Application).filter_by(status="submitted").count()
            ready_apps = db.query(Application).filter_by(status="ready").count()

            return {
                "is_running": self.is_running,
                "dry_run": DRY_RUN,
                "review_mode": REVIEW_MODE,
                "stats": self.stats,
                "jobs": {
                    "total": total_jobs,
                    "new": new_jobs,
                    "applied": applied_jobs,
                    "failed": failed_jobs,
                    "review": review_jobs,
                },
                "applications": {
                    "total": total_apps,
                    "submitted": submitted_apps,
                    "ready": ready_apps,
                },
                "max_per_hour": MAX_APPLICATIONS_PER_HOUR,
            }
        finally:
            db.close()

    def _run_loop(self):
        """Main loop for continuous autonomous operation."""
        while not self._stop_event.is_set():
            try:
                self._run_pipeline()
            except Exception as e:
                logger.error(f"Pipeline error: {e}")
                db = get_session()
                db.add(ActivityLog(
                    action="Pipeline error",
                    details=str(e),
                    level="error"
                ))
                db.commit()
                db.close()

            # Wait before next cycle (30 minutes)
            logger.info("Waiting 30 minutes before next cycle...")
            for _ in range(1800):  # 30 min in 1-second intervals
                if self._stop_event.is_set():
                    return
                time.sleep(1)

    def _run_pipeline(self):
        """Execute one complete pipeline cycle."""
        logger.info("=" * 60)
        logger.info("Starting pipeline cycle")
        logger.info("=" * 60)

        db = get_session()

        try:
            # 1. Get active search configs
            configs = db.query(SearchConfig).filter_by(is_active=True).all()
            if not configs:
                # Use default config
                configs = [type("Config", (), {
                    "job_title": "Software Engineer",
                    "location": "Remote",
                    "platforms": "linkedin,indeed,remoteok",
                    "remote_only": True,
                    "experience_level": "mid",
                    "keywords": "",
                    "exclude_keywords": "",
                })()]

            # 2. Scrape jobs
            for config in configs:
                if self._stop_event.is_set():
                    return

                platforms = config.platforms.split(",") if isinstance(config.platforms, str) else ["linkedin", "indeed", "remoteok"]

                logger.info(f"Scraping for: {config.job_title} in {config.location}")
                results = scrape_all(
                    query=config.job_title,
                    location=config.location,
                    platforms=platforms,
                    remote_only=getattr(config, "remote_only", False),
                    experience_level=getattr(config, "experience_level", ""),
                )

                for platform, data in results.items():
                    self.stats["jobs_scraped"] += data.get("saved", 0)

                self.stats["last_action"] = "Scraping complete"

            # 3. Rank jobs by relevance
            logger.info("Ranking jobs by relevance...")
            query = configs[0].job_title if configs else "Software Engineer"
            top_job_ids = rank_jobs(query, top_n=20)
            self.stats["last_action"] = "Job ranking complete"

            # 4. Generate documents for top matches
            generated = 0
            for job_id in top_job_ids:
                if self._stop_event.is_set():
                    return

                job = db.query(Job).get(job_id)
                if not job or job.status not in ["new", "queued", "failed"]:
                    continue

                # Skip if already has an application that succeeded
                existing = db.query(Application).filter_by(job_id=job_id).first()
                if existing and existing.status in ["submitted", "ready"]:
                    continue

                try:
                    logger.info(f"Generating docs for: {job.title} @ {job.company}")
                    generate_and_save(job_id)
                    generated += 1
                    self.stats["documents_generated"] += 1

                    if generated >= 5:  # Batch limit per cycle
                        break

                    time.sleep(5)  # Rate limit for Gemini API

                except Exception as e:
                    logger.error(f"Generation failed for Job #{job_id}: {e}")
                    continue

            self.stats["last_action"] = f"Generated {generated} document sets"

            # 5. Apply to jobs (if not in review mode)
            if not REVIEW_MODE:
                self._apply_to_ready_jobs()

            # 6. Send follow-up emails
            follow_ups = send_follow_ups(days_after=7)
            self.stats["follow_ups_sent"] += follow_ups
            self.stats["last_action"] = "Pipeline cycle complete"

            logger.info("=" * 60)
            logger.info(f"Pipeline cycle complete. Stats: {json.dumps(self.stats, indent=2)}")
            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            raise
        finally:
            db.close()

    def _apply_to_ready_jobs(self):
        """Apply to all jobs that are ready (have generated docs)."""
        db = get_session()
        applied_this_hour = 0

        try:
            ready_apps = db.query(Application).filter_by(status="ready").all()

            if not ready_apps:
                logger.info("No applications ready to submit")
                return

            # Start browser if needed
            if not self.bot:
                self.bot = ApplicationBot()
                self.bot.start()

            for app in ready_apps:
                if self._stop_event.is_set():
                    break

                if applied_this_hour >= MAX_APPLICATIONS_PER_HOUR:
                    logger.info(f"Rate limit reached ({MAX_APPLICATIONS_PER_HOUR}/hour)")
                    break

                job = db.query(Job).get(app.job_id)
                if not job:
                    continue

                logger.info(f"Applying to: {job.title} @ {job.company} ({job.platform})")

                try:
                    success = self.bot.apply_to_job(job.id)
                    if success:
                        applied_this_hour += 1
                        self.stats["applications_submitted"] += 1
                    else:
                        self.stats["applications_failed"] += 1
                except Exception as e:
                    logger.error(f"Application error: {e}")
                    self.stats["applications_failed"] += 1

                # Delay between applications
                time.sleep(random.uniform(30, 90))

        except Exception as e:
            logger.error(f"Application loop error: {e}")
        finally:
            db.close()

    def apply_single(self, job_id: int) -> bool:
        """Manually trigger application for a single job."""
        if not self.bot:
            self.bot = ApplicationBot()
            self.bot.start()

        try:
            return self.bot.apply_to_job(job_id)
        except Exception as e:
            logger.error(f"Single application error: {e}")
            return False

    def scrape_now(self, query: str = None, location: str = None) -> dict:
        """Manually trigger a scraping run."""
        db = get_session()
        try:
            if not query:
                config = db.query(SearchConfig).filter_by(is_active=True).first()
                query = config.job_title if config else "Software Engineer"
                location = location or (config.location if config else "Remote")

            platforms = ["linkedin", "indeed", "remoteok"]
            results = scrape_all(query, location or "", platforms)

            for platform, data in results.items():
                self.stats["jobs_scraped"] += data.get("saved", 0)

            return results
        finally:
            db.close()


# Singleton engine instance
engine = JobFinderEngine()


# Import needed for _apply_to_ready_jobs
import random
