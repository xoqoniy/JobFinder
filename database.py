"""
Database models and initialization using SQLAlchemy.
Stores jobs, applications, generated documents, and user profile.
"""
import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Boolean,
    DateTime, Float, ForeignKey, Enum as SAEnum
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from config import DB_PATH

Base = declarative_base()
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
Session = sessionmaker(bind=engine)


class UserProfile(Base):
    """Stores the user's professional profile for CV generation."""
    __tablename__ = "user_profile"

    id = Column(Integer, primary_key=True)
    full_name = Column(String(200), nullable=False, default="")
    email = Column(String(200), default="")
    phone = Column(String(50), default="")
    location = Column(String(200), default="")
    linkedin_url = Column(String(500), default="")
    github_url = Column(String(500), default="")
    portfolio_url = Column(String(500), default="")
    summary = Column(Text, default="")
    skills = Column(Text, default="")  # JSON list
    experience = Column(Text, default="")  # JSON list of objects
    education = Column(Text, default="")  # JSON list of objects
    certifications = Column(Text, default="")  # JSON list
    base_cv_path = Column(String(500), default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow,
                        onupdate=datetime.datetime.utcnow)


class Job(Base):
    """A scraped job listing."""
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True)
    external_id = Column(String(200), unique=True)  # Platform-specific ID
    platform = Column(String(50), nullable=False)  # linkedin, indeed, glassdoor, remoteok
    title = Column(String(500), nullable=False)
    company = Column(String(300), nullable=False)
    location = Column(String(300), default="")
    description = Column(Text, default="")
    salary_min = Column(Float, nullable=True)
    salary_max = Column(Float, nullable=True)
    salary_currency = Column(String(10), default="USD")
    job_type = Column(String(50), default="")  # full-time, part-time, contract
    experience_level = Column(String(50), default="")
    url = Column(String(1000), nullable=False)
    apply_url = Column(String(1000), default="")
    posted_date = Column(DateTime, nullable=True)
    scraped_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Matching
    match_score = Column(Float, default=0.0)  # 0-100 relevance score
    is_easy_apply = Column(Boolean, default=False)

    # Status
    status = Column(String(50), default="new")
    # new, queued, generating, applying, applied, skipped, failed, review

    applications = relationship("Application", back_populates="job")

    def __repr__(self):
        return f"<Job {self.title} @ {self.company} [{self.platform}]>"


class Application(Base):
    """Tracks an application attempt."""
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    status = Column(String(50), default="pending")
    # pending, cv_generated, letter_generated, ready, submitted, failed, review

    cv_path = Column(String(500), default="")
    cover_letter_path = Column(String(500), default="")
    cv_content = Column(Text, default="")
    cover_letter_content = Column(Text, default="")

    # Audit trail
    screenshot_paths = Column(Text, default="")  # JSON list
    error_message = Column(Text, default="")
    applied_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow,
                        onupdate=datetime.datetime.utcnow)

    # Follow-up
    follow_up_sent = Column(Boolean, default=False)
    follow_up_date = Column(DateTime, nullable=True)
    response_received = Column(Boolean, default=False)
    response_type = Column(String(50), default="")  # positive, rejection, interview

    job = relationship("Job", back_populates="applications")

    def __repr__(self):
        return f"<Application for Job#{self.job_id} - {self.status}>"


class EmailLog(Base):
    """Tracks sent emails."""
    __tablename__ = "email_logs"

    id = Column(Integer, primary_key=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=True)
    recipient = Column(String(300), nullable=False)
    subject = Column(String(500), nullable=False)
    body = Column(Text, nullable=False)
    email_type = Column(String(50), default="follow_up")  # follow_up, networking, thank_you
    sent_at = Column(DateTime, default=datetime.datetime.utcnow)
    status = Column(String(50), default="sent")  # sent, failed, draft


class ActivityLog(Base):
    """Audit trail for all system actions."""
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True)
    action = Column(String(200), nullable=False)
    details = Column(Text, default="")
    level = Column(String(20), default="info")  # info, warning, error, success
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)


class SearchConfig(Base):
    """Saved search configurations."""
    __tablename__ = "search_configs"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    job_title = Column(String(300), nullable=False)
    location = Column(String(300), default="")
    keywords = Column(Text, default="")  # comma-separated
    exclude_keywords = Column(Text, default="")  # comma-separated
    experience_level = Column(String(50), default="")
    job_type = Column(String(50), default="")
    remote_only = Column(Boolean, default=False)
    salary_min = Column(Float, nullable=True)
    platforms = Column(Text, default="linkedin,indeed,glassdoor")  # comma-separated
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


def init_db():
    """Create all tables and seed default profile if empty."""
    Base.metadata.create_all(engine)
    
    db = get_session()
    try:
        profile = db.query(UserProfile).first()
        if not profile:
            import os
            import json
            
            cv_path = ""
            for candidate in ["SafarmurodAshurovCV.pdf", "my_cv.pdf", "cv.pdf", "resume.pdf"]:
                if os.path.exists(candidate):
                    cv_path = candidate
                    break
            
            skills_list = [
                "Python", "JavaScript", "TypeScript", "C++", "Dart", "Flutter",
                "FastAPI", "Flask", "SQL", "PostgreSQL", "Machine Learning",
                "Artificial Intelligence", "Docker", "Git", "Linux", "REST APIs"
            ]
            
            db.add(UserProfile(
                full_name="Safarmurod Ashurov",
                email="sm.ashurov7@gmail.com",
                phone="(+36) 705401469",
                location="Hungary / Remote",
                linkedin_url="https://www.linkedin.com/in/safarmurod-ashurov/",
                github_url="https://github.com/xoqoniy",
                portfolio_url="https://www.instagram.com/codedpolymath/",
                summary="Computer Science student specializing in Artificial Intelligence with hands-on experience in full-stack engineering, machine learning models, autonomous systems, and backend development.",
                skills=json.dumps(skills_list),
                experience=json.dumps([
                    {
                        "title": "Software & AI Developer",
                        "company": "Projects & Freelance",
                        "location": "Remote",
                        "start_date": "2023",
                        "end_date": "Present",
                        "description": "Building full-stack web applications, AI automation tools, and autonomous agent frameworks.",
                        "achievements": [
                            "Engineered autonomous web automation engines with Playwright and LLM integrations.",
                            "Developed high-performance REST APIs and microservices in Python and FastAPI."
                        ]
                    }
                ]),
                education=json.dumps([
                    {
                        "degree": "B.Sc. in Computer Science (Artificial Intelligence Specialization)",
                        "school": "University",
                        "year": "2026"
                    }
                ]),
                certifications=json.dumps(["AI & Machine Learning Foundations", "Full-Stack Software Engineering"]),
                base_cv_path=cv_path
            ))
            db.commit()
            print("Auto-seeded default UserProfile in database.")

        # Seed search configs if empty
        if db.query(SearchConfig).count() == 0:
            default_configs = [
                SearchConfig(
                    name="Remote - Full Stack / Software Engineer",
                    job_title="Full Stack Software Engineer",
                    location="Remote",
                    remote_only=True,
                    experience_level="entry,mid",
                    exclude_keywords="unpaid,volunteer,no salary",
                    platforms="linkedin,indeed,remoteok",
                    is_active=True,
                ),
                SearchConfig(
                    name="Remote - Backend Developer (Python/AI)",
                    job_title="Backend Developer",
                    location="Remote",
                    remote_only=True,
                    keywords="Python,FastAPI,Node,Django",
                    experience_level="entry,mid",
                    exclude_keywords="unpaid,volunteer",
                    platforms="linkedin,indeed,remoteok",
                    is_active=True,
                ),
                SearchConfig(
                    name="Remote - Frontend Developer",
                    job_title="Frontend Developer",
                    location="Remote",
                    remote_only=True,
                    keywords="React,JavaScript,TypeScript,Vue",
                    experience_level="entry,mid",
                    exclude_keywords="unpaid,volunteer",
                    platforms="linkedin,indeed,remoteok",
                    is_active=True,
                ),
                SearchConfig(
                    name="Budapest - Hybrid/Onsite Software Engineer",
                    job_title="Software Engineer",
                    location="Budapest, Hungary",
                    keywords="hybrid,budapest",
                    experience_level="entry,mid",
                    exclude_keywords="unpaid,volunteer",
                    platforms="linkedin,indeed",
                    is_active=True,
                ),
                SearchConfig(
                    name="Budapest - Hybrid Full Stack / Backend",
                    job_title="Full Stack Developer",
                    location="Budapest, Hungary",
                    keywords="hybrid,budapest",
                    experience_level="entry,mid",
                    exclude_keywords="unpaid,volunteer",
                    platforms="linkedin,indeed",
                    is_active=True,
                ),
                SearchConfig(
                    name="Paid Internship - Software / AI / Web",
                    job_title="Software Engineer Intern",
                    location="Budapest, Hungary",
                    keywords="paid intern,internship,trainee",
                    exclude_keywords="unpaid,uncompensated,volunteer,no pay,free intern",
                    platforms="linkedin,indeed,remoteok",
                    is_active=True,
                ),
                SearchConfig(
                    name="Remote - Paid Software Intern",
                    job_title="Software Engineer Intern",
                    location="Remote",
                    remote_only=True,
                    keywords="paid,intern,internship",
                    exclude_keywords="unpaid,uncompensated,volunteer",
                    platforms="linkedin,indeed,remoteok",
                    is_active=True,
                ),
            ]
            db.add_all(default_configs)
            db.commit()
            print("Auto-seeded targeted SearchConfigs for Budapest Hybrid & Remote roles.")
    except Exception as e:
        db.rollback()
        print(f"UserProfile/SearchConfig seed error: {e}")
    finally:
        db.close()


def get_session():
    """Get a new database session."""
    return Session()


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")

