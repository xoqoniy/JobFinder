"""
Flask Dashboard for JobFinder.
Provides a web UI to control, monitor, and review the autonomous job application system.
"""
import sys
import json
import logging
import datetime
import os
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import (
    Flask, render_template, request, redirect, url_for,
    jsonify, flash, send_file
)
from sqlalchemy import desc

from config import (
    DASHBOARD_PORT, DASHBOARD_SECRET_KEY, TEMPLATES_DIR, STATIC_DIR,
    GENERATED_DOCS_DIR, SCREENSHOTS_DIR, CV_DIR, DRY_RUN, REVIEW_MODE
)
from database import (
    Job, Application, UserProfile, SearchConfig, ActivityLog,
    EmailLog, get_session, init_db
)
from engine import engine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("jobfinder.log"),
    ]
)
logger = logging.getLogger(__name__)

app = Flask(
    __name__,
    template_folder=str(TEMPLATES_DIR),
    static_folder=str(STATIC_DIR),
)
app.secret_key = DASHBOARD_SECRET_KEY

# Initialize database
init_db()


# ─────────────────────────────────────────
# Dashboard Routes
# ─────────────────────────────────────────

@app.route("/")
def index():
    """Main dashboard page."""
    db = get_session()
    try:
        status = engine.get_status()
        recent_logs = db.query(ActivityLog).order_by(
            desc(ActivityLog.timestamp)
        ).limit(20).all()

        recent_applications = db.query(Application).join(Job).order_by(
            desc(Application.updated_at)
        ).limit(10).all()

        return render_template(
            "index.html",
            status=status,
            logs=recent_logs,
            applications=recent_applications,
        )
    finally:
        db.close()


@app.route("/jobs")
def jobs_list():
    """List all scraped jobs with filtering."""
    db = get_session()
    try:
        page = request.args.get("page", 1, type=int)
        per_page = 25
        status_filter = request.args.get("status", "all")
        platform_filter = request.args.get("platform", "all")
        search = request.args.get("search", "")

        query = db.query(Job)

        if status_filter != "all":
            query = query.filter(Job.status == status_filter)
        if platform_filter != "all":
            query = query.filter(Job.platform == platform_filter)
        if search:
            query = query.filter(
                Job.title.ilike(f"%{search}%") |
                Job.company.ilike(f"%{search}%")
            )

        total = query.count()
        jobs = query.order_by(desc(Job.match_score), desc(Job.scraped_at)).offset(
            (page - 1) * per_page
        ).limit(per_page).all()

        return render_template(
            "jobs.html",
            jobs=jobs,
            page=page,
            total=total,
            per_page=per_page,
            status_filter=status_filter,
            platform_filter=platform_filter,
            search=search,
        )
    finally:
        db.close()


@app.route("/jobs/<int:job_id>")
def job_detail(job_id):
    """View job details and application status."""
    db = get_session()
    try:
        job = db.query(Job).get(job_id)
        if not job:
            flash("Job not found", "error")
            return redirect(url_for("jobs_list"))

        application = db.query(Application).filter_by(job_id=job_id).first()
        return render_template("job_detail.html", job=job, application=application)
    finally:
        db.close()


@app.route("/jobs/<int:job_id>/generate", methods=["POST"])
def generate_docs(job_id):
    """Generate CV and cover letter for a job."""
    try:
        from generator import generate_and_save
        generate_and_save(job_id)
        flash("CV and cover letter generated successfully!", "success")
    except Exception as e:
        flash(f"Generation failed: {e}", "error")
    return redirect(url_for("job_detail", job_id=job_id))


@app.route("/jobs/<int:job_id>/apply", methods=["POST"])
def apply_job(job_id):
    """Apply to a job."""
    try:
        success = engine.apply_single(job_id)
        if success:
            flash("Application submitted successfully!", "success")
        else:
            flash("Application requires manual review. Check the job detail page.", "warning")
    except Exception as e:
        flash(f"Application failed: {e}", "error")
    return redirect(url_for("job_detail", job_id=job_id))


@app.route("/jobs/<int:job_id>/skip", methods=["POST"])
def skip_job(job_id):
    """Skip a job."""
    db = get_session()
    try:
        job = db.query(Job).get(job_id)
        if job:
            job.status = "skipped"
            db.commit()
            flash("Job skipped", "info")
    finally:
        db.close()
    return redirect(url_for("jobs_list"))


@app.route("/applications")
def applications_list():
    """List all applications."""
    db = get_session()
    try:
        applications = db.query(Application).join(Job).order_by(
            desc(Application.updated_at)
        ).all()
        return render_template("applications.html", applications=applications)
    finally:
        db.close()


@app.route("/applications/<int:app_id>/preview")
def preview_documents(app_id):
    """Preview generated CV and cover letter."""
    db = get_session()
    try:
        application = db.query(Application).get(app_id)
        if not application:
            flash("Application not found", "error")
            return redirect(url_for("applications_list"))

        job = db.query(Job).get(application.job_id)
        return render_template(
            "preview.html",
            application=application,
            job=job,
        )
    finally:
        db.close()


@app.route("/profile", methods=["GET", "POST"])
def profile():
    """Edit user profile."""
    db = get_session()
    try:
        profile = db.query(UserProfile).first()

        if request.method == "POST":
            if not profile:
                profile = UserProfile()
                db.add(profile)

            profile.full_name = request.form.get("full_name", "")
            profile.email = request.form.get("email", "")
            profile.phone = request.form.get("phone", "")
            profile.location = request.form.get("location", "")
            profile.linkedin_url = request.form.get("linkedin_url", "")
            profile.github_url = request.form.get("github_url", "")
            profile.portfolio_url = request.form.get("portfolio_url", "")
            profile.summary = request.form.get("summary", "")

            # Handle skills as JSON array
            skills_raw = request.form.get("skills", "")
            profile.skills = json.dumps([s.strip() for s in skills_raw.split(",") if s.strip()])

            # Handle experience as JSON
            experience_text = request.form.get("experience", "")
            if experience_text:
                try:
                    profile.experience = experience_text
                except Exception:
                    profile.experience = json.dumps([{"raw": experience_text}])

            education_text = request.form.get("education", "")
            if education_text:
                try:
                    profile.education = education_text
                except Exception:
                    profile.education = json.dumps([{"raw": education_text}])

            certs_raw = request.form.get("certifications", "")
            profile.certifications = json.dumps([c.strip() for c in certs_raw.split(",") if c.strip()])

            # Handle CV file upload
            if "cv_file" in request.files:
                cv_file = request.files["cv_file"]
                if cv_file.filename:
                    cv_path = CV_DIR / cv_file.filename
                    cv_file.save(str(cv_path))
                    profile.base_cv_path = str(cv_path)

            profile.updated_at = datetime.datetime.utcnow()
            db.commit()
            flash("Profile saved successfully!", "success")
            return redirect(url_for("profile"))

        return render_template("profile.html", profile=profile)
    finally:
        db.close()


@app.route("/search-configs", methods=["GET", "POST"])
def search_configs():
    """Manage job search configurations."""
    db = get_session()
    try:
        if request.method == "POST":
            config = SearchConfig(
                name=request.form.get("name", "Default Search"),
                job_title=request.form.get("job_title", "Software Engineer"),
                location=request.form.get("location", "Remote"),
                keywords=request.form.get("keywords", ""),
                exclude_keywords=request.form.get("exclude_keywords", ""),
                experience_level=request.form.get("experience_level", "mid"),
                job_type=request.form.get("job_type", ""),
                remote_only="remote_only" in request.form,
                platforms=request.form.get("platforms", "linkedin,indeed,remoteok"),
                is_active=True,
            )
            db.add(config)
            db.commit()
            flash("Search configuration saved!", "success")
            return redirect(url_for("search_configs"))

        configs = db.query(SearchConfig).all()
        return render_template("search_configs.html", configs=configs)
    finally:
        db.close()


@app.route("/search-configs/<int:config_id>/delete", methods=["POST"])
def delete_search_config(config_id):
    """Delete a search configuration."""
    db = get_session()
    try:
        config = db.query(SearchConfig).get(config_id)
        if config:
            db.delete(config)
            db.commit()
            flash("Search configuration deleted", "info")
    finally:
        db.close()
    return redirect(url_for("search_configs"))


@app.route("/search-configs/<int:config_id>/toggle", methods=["POST"])
def toggle_search_config(config_id):
    """Toggle a search config active/inactive."""
    db = get_session()
    try:
        config = db.query(SearchConfig).get(config_id)
        if config:
            config.is_active = not config.is_active
            db.commit()
    finally:
        db.close()
    return redirect(url_for("search_configs"))


# ─────────────────────────────────────────
# Engine Control API
# ─────────────────────────────────────────

@app.route("/api/engine/start", methods=["POST"])
def api_start_engine():
    """Start the autonomous engine."""
    engine.start()
    return jsonify({"status": "started"})


@app.route("/api/engine/stop", methods=["POST"])
def api_stop_engine():
    """Stop the autonomous engine."""
    engine.stop()
    return jsonify({"status": "stopped"})


@app.route("/api/engine/status")
def api_engine_status():
    """Get engine status."""
    return jsonify(engine.get_status())


@app.route("/api/scrape", methods=["POST"])
def api_scrape():
    """Trigger a manual scrape."""
    data = request.json or {}
    query = data.get("query", "Software Engineer")
    location = data.get("location", "Remote")
    results = engine.scrape_now(query, location)
    return jsonify(results)


@app.route("/api/jobs/<int:job_id>/score")
def api_job_score(job_id):
    """Get match score for a single job."""
    db = get_session()
    try:
        job = db.query(Job).get(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        return jsonify({
            "job_id": job.id,
            "title": job.title,
            "company": job.company,
            "match_score": job.match_score,
        })
    finally:
        db.close()


@app.route("/api/activity-log")
def api_activity_log():
    """Get recent activity log entries."""
    db = get_session()
    try:
        logs = db.query(ActivityLog).order_by(
            desc(ActivityLog.timestamp)
        ).limit(50).all()
        return jsonify([{
            "id": log.id,
            "action": log.action,
            "details": log.details,
            "level": log.level,
            "timestamp": log.timestamp.isoformat() if log.timestamp else None,
        } for log in logs])
    finally:
        db.close()


@app.route("/emails")
def emails_list():
    """List all sent/drafted emails."""
    db = get_session()
    try:
        emails = db.query(EmailLog).order_by(desc(EmailLog.sent_at)).all()
        return render_template("emails.html", emails=emails)
    finally:
        db.close()


@app.route("/logs")
def logs_page():
    """Full activity log page."""
    db = get_session()
    try:
        logs = db.query(ActivityLog).order_by(desc(ActivityLog.timestamp)).limit(200).all()
        return render_template("logs.html", logs=logs)
    finally:
        db.close()


# ─────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────

if __name__ == "__main__":
    print(f"""
+----------------------------------------------------------+
|           JobFinder Dashboard Starting...                 |
|                                                          |
|   Open: http://localhost:{DASHBOARD_PORT}                       |
|                                                          |
|   Controls:                                              |
|   - Set up your Profile first                            |
|   - Configure Search settings                            |
|   - Start Engine for autonomous mode                     |
|                                                          |
|   Safety: DRY_RUN={'ON' if DRY_RUN else 'OFF'} | REVIEW_MODE={'ON' if REVIEW_MODE else 'OFF'}            |
+----------------------------------------------------------+
    """)
    app.run(host="0.0.0.0", port=DASHBOARD_PORT, debug=True)
