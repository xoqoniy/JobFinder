"""
Email module for sending follow-up emails, networking, and thank-you messages.
Uses Gmail SMTP with App Passwords (free).
"""
import smtplib
import logging
import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from pathlib import Path

from config import EMAIL_ADDRESS, EMAIL_APP_PASSWORD
from database import EmailLog, Application, Job, ActivityLog, get_session

logger = logging.getLogger(__name__)


def send_email(
    to: str,
    subject: str,
    body: str,
    html_body: str = None,
    attachments: list[str] = None,
    application_id: int = None,
    email_type: str = "follow_up",
) -> bool:
    """
    Send an email via Gmail SMTP.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Plain text body.
        html_body: Optional HTML body.
        attachments: Optional list of file paths to attach.
        application_id: Optional application ID for tracking.
        email_type: Type of email for logging.

    Returns:
        True if sent successfully.
    """
    if not EMAIL_ADDRESS or not EMAIL_APP_PASSWORD:
        raise ValueError(
            "Email credentials not configured. Set EMAIL_ADDRESS and EMAIL_APP_PASSWORD in .env\n"
            "Create an App Password at: https://myaccount.google.com/apppasswords"
        )

    db = get_session()

    try:
        # Build message
        msg = MIMEMultipart("alternative") if html_body else MIMEMultipart()
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = to
        msg["Subject"] = subject

        msg.attach(MIMEText(body, "plain"))
        if html_body:
            msg.attach(MIMEText(html_body, "html"))

        # Attachments
        if attachments:
            for file_path in attachments:
                path = Path(file_path)
                if path.exists():
                    with open(path, "rb") as f:
                        part = MIMEApplication(f.read(), Name=path.name)
                        part["Content-Disposition"] = f'attachment; filename="{path.name}"'
                        msg.attach(part)

        # Send via Gmail SMTP
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)
            server.send_message(msg)

        # Log to database
        email_log = EmailLog(
            application_id=application_id,
            recipient=to,
            subject=subject,
            body=body,
            email_type=email_type,
            status="sent",
        )
        db.add(email_log)
        db.add(ActivityLog(
            action=f"Email sent ({email_type})",
            details=f"To: {to}, Subject: {subject}",
            level="success",
        ))
        db.commit()

        logger.info(f"Email sent to {to}: {subject}")
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error(
            "Gmail authentication failed. Make sure you're using an App Password, "
            "not your regular password. Create one at: https://myaccount.google.com/apppasswords"
        )
        db.add(EmailLog(
            application_id=application_id,
            recipient=to,
            subject=subject,
            body=body,
            email_type=email_type,
            status="failed",
        ))
        db.commit()
        return False

    except Exception as e:
        logger.error(f"Email send failed: {e}")
        db.add(EmailLog(
            application_id=application_id,
            recipient=to,
            subject=subject,
            body=body,
            email_type=email_type,
            status="failed",
        ))
        db.commit()
        return False

    finally:
        db.close()


def send_follow_ups(days_after: int = 7) -> int:
    """
    Send follow-up emails for applications submitted X days ago
    that haven't received a response yet.

    Returns number of follow-ups sent.
    """
    db = get_session()
    sent = 0

    try:
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=days_after)

        applications = db.query(Application).filter(
            Application.status == "submitted",
            Application.follow_up_sent == False,
            Application.response_received == False,
            Application.applied_at <= cutoff,
            Application.applied_at.isnot(None),
        ).all()

        for app in applications:
            job = db.query(Job).get(app.job_id)
            if not job:
                continue

            # Generate follow-up email content
            from generator import generate_email
            email_data = generate_email(job, email_type="follow_up")

            # For follow-ups, we'd need the recruiter's email.
            # Since we often don't have it, log it as a draft
            email_log = EmailLog(
                application_id=app.id,
                recipient="[recruiter email needed]",
                subject=email_data["subject"],
                body=email_data["body"],
                email_type="follow_up",
                status="draft",
            )
            db.add(email_log)

            app.follow_up_sent = True
            app.follow_up_date = datetime.datetime.utcnow()
            db.commit()
            sent += 1

            logger.info(f"Follow-up drafted for {job.title} @ {job.company}")

        return sent

    except Exception as e:
        logger.error(f"Follow-up process failed: {e}")
        return sent

    finally:
        db.close()
