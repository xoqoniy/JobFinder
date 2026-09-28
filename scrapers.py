"""
Job scrapers for multiple platforms.
Each scraper returns a list of job dicts that get inserted into the database.
"""
import time
import random
import json
import re
import datetime
import logging
from abc import ABC, abstractmethod
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

from database import Job, ActivityLog, get_session

logger = logging.getLogger(__name__)
ua = UserAgent()


class BaseScraper(ABC):
    """Base class for all job scrapers."""

    PLATFORM = "base"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": ua.random,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })

    def _delay(self, min_s=2, max_s=5):
        """Human-like delay between requests."""
        time.sleep(random.uniform(min_s, max_s))

    @abstractmethod
    def search(self, query: str, location: str = "", **kwargs) -> list[dict]:
        """Search for jobs. Returns list of job dicts."""
        pass

    def save_jobs(self, jobs: list[dict]) -> int:
        """Save scraped jobs to database, skip duplicates."""
        db = get_session()
        saved = 0
        try:
            for job_data in jobs:
                existing = db.query(Job).filter_by(
                    external_id=job_data.get("external_id", "")
                ).first()
                if existing:
                    continue

                job = Job(
                    external_id=job_data.get("external_id", f"{self.PLATFORM}_{int(time.time())}_{saved}"),
                    platform=self.PLATFORM,
                    title=job_data.get("title", "Unknown"),
                    company=job_data.get("company", "Unknown"),
                    location=job_data.get("location", ""),
                    description=job_data.get("description", ""),
                    salary_min=job_data.get("salary_min"),
                    salary_max=job_data.get("salary_max"),
                    salary_currency=job_data.get("salary_currency", "USD"),
                    job_type=job_data.get("job_type", ""),
                    experience_level=job_data.get("experience_level", ""),
                    url=job_data.get("url", ""),
                    apply_url=job_data.get("apply_url", ""),
                    posted_date=job_data.get("posted_date"),
                    is_easy_apply=job_data.get("is_easy_apply", False),
                    status="new",
                )
                db.add(job)
                saved += 1

            db.add(ActivityLog(
                action=f"Scraped {self.PLATFORM}",
                details=f"Found {len(jobs)} jobs, saved {saved} new",
                level="success"
            ))
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Error saving jobs from {self.PLATFORM}: {e}")
            db.add(ActivityLog(
                action=f"Scrape error {self.PLATFORM}",
                details=str(e),
                level="error"
            ))
            db.commit()
        finally:
            db.close()
        return saved


class LinkedInScraper(BaseScraper):
    """
    Scrapes LinkedIn job listings via their public job search pages.
    No login required for basic search results.
    """

    PLATFORM = "linkedin"
    BASE_URL = "https://www.linkedin.com/jobs/search"

    EXPERIENCE_MAP = {
        "internship": "1",
        "entry": "2",
        "associate": "3",
        "mid": "4",
        "director": "5",
        "executive": "6",
    }

    def search(self, query: str, location: str = "", **kwargs) -> list[dict]:
        """Search LinkedIn jobs (public, no auth)."""
        jobs = []
        max_pages = kwargs.get("max_pages", 3)
        experience = kwargs.get("experience_level", "")

        for page in range(max_pages):
            params = {
                "keywords": query,
                "location": location,
                "start": page * 25,
                "sortBy": "DD",  # Date descending
            }

            if experience and experience.lower() in self.EXPERIENCE_MAP:
                params["f_E"] = self.EXPERIENCE_MAP[experience.lower()]

            if kwargs.get("remote_only"):
                params["f_WT"] = "2"  # Remote

            if kwargs.get("easy_apply"):
                params["f_AL"] = "true"

            try:
                self.session.headers["User-Agent"] = ua.random
                resp = self.session.get(self.BASE_URL, params=params, timeout=15)
                resp.raise_for_status()

                soup = BeautifulSoup(resp.text, "lxml")
                job_cards = soup.select("div.base-card")

                if not job_cards:
                    # Try alternative selectors
                    job_cards = soup.select("li.result-card")

                for card in job_cards:
                    try:
                        title_el = card.select_one("h3.base-search-card__title, h3.result-card__title")
                        company_el = card.select_one("h4.base-search-card__subtitle, h4.result-card__subtitle")
                        location_el = card.select_one("span.job-search-card__location, span.result-card__location")
                        link_el = card.select_one("a.base-card__full-link, a.result-card__full-link")
                        date_el = card.select_one("time")

                        title = title_el.get_text(strip=True) if title_el else "Unknown"
                        company = company_el.get_text(strip=True) if company_el else "Unknown"
                        loc = location_el.get_text(strip=True) if location_el else ""
                        url = link_el["href"] if link_el else ""
                        posted = None
                        if date_el and date_el.get("datetime"):
                            try:
                                posted = datetime.datetime.fromisoformat(date_el["datetime"])
                            except ValueError:
                                pass

                        # Extract job ID from URL
                        ext_id = ""
                        if url:
                            match = re.search(r"(\d{8,})", url)
                            if match:
                                ext_id = f"li_{match.group(1)}"
                            else:
                                ext_id = f"li_{hash(url) & 0xFFFFFFFF}"

                        jobs.append({
                            "external_id": ext_id,
                            "title": title,
                            "company": company,
                            "location": loc,
                            "url": url.split("?")[0] if url else "",
                            "posted_date": posted,
                            "is_easy_apply": kwargs.get("easy_apply", False),
                        })
                    except Exception as e:
                        logger.warning(f"Error parsing LinkedIn card: {e}")
                        continue

                logger.info(f"LinkedIn page {page + 1}: found {len(job_cards)} cards")
                self._delay(3, 7)

            except requests.RequestException as e:
                logger.error(f"LinkedIn request error on page {page + 1}: {e}")
                break

        return jobs


class IndeedScraper(BaseScraper):
    """Scrapes Indeed job listings."""

    PLATFORM = "indeed"
    BASE_URL = "https://www.indeed.com/jobs"

    def search(self, query: str, location: str = "", **kwargs) -> list[dict]:
        """Search Indeed jobs."""
        jobs = []
        max_pages = kwargs.get("max_pages", 3)

        for page in range(max_pages):
            params = {
                "q": query,
                "l": location,
                "start": page * 10,
                "sort": "date",
            }

            if kwargs.get("job_type"):
                type_map = {
                    "full-time": "fulltime",
                    "part-time": "parttime",
                    "contract": "contract",
                    "internship": "internship",
                }
                jt = type_map.get(kwargs["job_type"].lower(), "")
                if jt:
                    params["jt"] = jt

            if kwargs.get("remote_only"):
                params["remotejob"] = "032b3046-06a3-4876-8dfd-474eb5e7ed11"

            try:
                self.session.headers["User-Agent"] = ua.random
                resp = self.session.get(self.BASE_URL, params=params, timeout=15)
                resp.raise_for_status()

                soup = BeautifulSoup(resp.text, "lxml")

                # Indeed uses various card selectors
                job_cards = soup.select("div.job_seen_beacon, div.jobsearch-ResultsList > div")

                for card in job_cards:
                    try:
                        title_el = card.select_one("h2.jobTitle a, a.jcs-JobTitle")
                        company_el = card.select_one("span[data-testid='company-name'], span.companyName")
                        location_el = card.select_one("div[data-testid='text-location'], div.companyLocation")
                        salary_el = card.select_one("div.salary-snippet-container, div.metadata.salary-snippet-container")

                        if not title_el:
                            continue

                        title = title_el.get_text(strip=True)
                        company = company_el.get_text(strip=True) if company_el else "Unknown"
                        loc = location_el.get_text(strip=True) if location_el else ""

                        # Get job URL
                        job_link = title_el.get("href", "")
                        if job_link and not job_link.startswith("http"):
                            job_link = f"https://www.indeed.com{job_link}"

                        # Extract job ID
                        ext_id = ""
                        jk_match = re.search(r"jk=([a-f0-9]+)", job_link)
                        if jk_match:
                            ext_id = f"indeed_{jk_match.group(1)}"
                        else:
                            ext_id = f"indeed_{hash(title + company) & 0xFFFFFFFF}"

                        # Parse salary if available
                        salary_min = salary_max = None
                        if salary_el:
                            salary_text = salary_el.get_text(strip=True)
                            salary_nums = re.findall(r"[\d,]+\.?\d*", salary_text.replace(",", ""))
                            if len(salary_nums) >= 2:
                                salary_min = float(salary_nums[0])
                                salary_max = float(salary_nums[1])
                            elif len(salary_nums) == 1:
                                salary_min = salary_max = float(salary_nums[0])

                        jobs.append({
                            "external_id": ext_id,
                            "title": title,
                            "company": company,
                            "location": loc,
                            "url": job_link,
                            "salary_min": salary_min,
                            "salary_max": salary_max,
                        })
                    except Exception as e:
                        logger.warning(f"Error parsing Indeed card: {e}")
                        continue

                logger.info(f"Indeed page {page + 1}: found {len(job_cards)} cards")
                self._delay(3, 7)

            except requests.RequestException as e:
                logger.error(f"Indeed request error on page {page + 1}: {e}")
                break

        return jobs


class GlassdoorScraper(BaseScraper):
    """Scrapes Glassdoor job listings."""

    PLATFORM = "glassdoor"
    BASE_URL = "https://www.glassdoor.com/Job/jobs.htm"

    def search(self, query: str, location: str = "", **kwargs) -> list[dict]:
        """Search Glassdoor jobs."""
        jobs = []
        max_pages = kwargs.get("max_pages", 2)

        for page in range(max_pages):
            params = {
                "sc.keyword": query,
                "locT": "C" if location else "",
                "locKeyword": location,
                "p": page + 1,
            }

            try:
                self.session.headers["User-Agent"] = ua.random
                resp = self.session.get(self.BASE_URL, params=params, timeout=15)
                resp.raise_for_status()

                soup = BeautifulSoup(resp.text, "lxml")
                job_cards = soup.select("li.react-job-listing, div[data-test='jobListing']")

                for card in job_cards:
                    try:
                        title_el = card.select_one("a[data-test='job-link'], a.jobLink")
                        company_el = card.select_one("div.job-search-8wag7x, a[data-test='emp-name']")
                        location_el = card.select_one("span.job-search-87g0oy, div[data-test='emp-location']")
                        salary_el = card.select_one("span[data-test='detailSalary']")

                        if not title_el:
                            continue

                        title = title_el.get_text(strip=True)
                        company = company_el.get_text(strip=True) if company_el else "Unknown"
                        loc = location_el.get_text(strip=True) if location_el else ""

                        job_link = title_el.get("href", "")
                        if job_link and not job_link.startswith("http"):
                            job_link = f"https://www.glassdoor.com{job_link}"

                        # Extract ID
                        gd_match = re.search(r"jobListingId=(\d+)", job_link)
                        ext_id = f"gd_{gd_match.group(1)}" if gd_match else f"gd_{hash(title + company) & 0xFFFFFFFF}"

                        jobs.append({
                            "external_id": ext_id,
                            "title": title,
                            "company": company,
                            "location": loc,
                            "url": job_link,
                        })
                    except Exception as e:
                        logger.warning(f"Error parsing Glassdoor card: {e}")
                        continue

                logger.info(f"Glassdoor page {page + 1}: found {len(job_cards)} cards")
                self._delay(4, 8)

            except requests.RequestException as e:
                logger.error(f"Glassdoor request error on page {page + 1}: {e}")
                break

        return jobs


class RemoteOKScraper(BaseScraper):
    """
    Scrapes RemoteOK using their free public JSON API.
    This is the most reliable scraper since it uses an official API.
    """

    PLATFORM = "remoteok"
    API_URL = "https://remoteok.com/api"

    def search(self, query: str, location: str = "", **kwargs) -> list[dict]:
        """Search RemoteOK jobs via their public API."""
        jobs = []

        try:
            self.session.headers["User-Agent"] = ua.random
            resp = self.session.get(self.API_URL, timeout=15)
            resp.raise_for_status()

            data = resp.json()

            # First item is metadata, skip it
            for item in data[1:]:
                title = item.get("position", "")
                company = item.get("company", "")

                # Filter by query
                searchable = f"{title} {company} {' '.join(item.get('tags', []))}".lower()
                if query.lower() not in searchable and not any(
                    kw.lower() in searchable for kw in query.split()
                ):
                    continue

                # Parse salary
                salary_min = salary_max = None
                if item.get("salary_min"):
                    try:
                        salary_min = float(item["salary_min"])
                    except (ValueError, TypeError):
                        pass
                if item.get("salary_max"):
                    try:
                        salary_max = float(item["salary_max"])
                    except (ValueError, TypeError):
                        pass

                posted = None
                if item.get("date"):
                    try:
                        posted = datetime.datetime.fromisoformat(
                            item["date"].replace("Z", "+00:00")
                        )
                    except ValueError:
                        pass

                jobs.append({
                    "external_id": f"rok_{item.get('id', hash(title) & 0xFFFFFFFF)}",
                    "title": title,
                    "company": company,
                    "location": item.get("location", "Remote"),
                    "url": item.get("url", f"https://remoteok.com/l/{item.get('id', '')}"),
                    "apply_url": item.get("apply_url", ""),
                    "description": item.get("description", ""),
                    "salary_min": salary_min,
                    "salary_max": salary_max,
                    "salary_currency": "USD",
                    "job_type": "full-time",
                    "posted_date": posted,
                })

            logger.info(f"RemoteOK: found {len(jobs)} matching jobs")

        except requests.RequestException as e:
            logger.error(f"RemoteOK request error: {e}")
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"RemoteOK parse error: {e}")

        return jobs


def get_scraper(platform: str) -> BaseScraper:
    """Factory to get the right scraper by platform name."""
    scrapers = {
        "linkedin": LinkedInScraper,
        "indeed": IndeedScraper,
        "glassdoor": GlassdoorScraper,
        "remoteok": RemoteOKScraper,
    }
    cls = scrapers.get(platform.lower())
    if not cls:
        raise ValueError(f"Unknown platform: {platform}. Available: {list(scrapers.keys())}")
    return cls()


def scrape_all(query: str, location: str = "", platforms: list[str] = None, **kwargs) -> dict:
    """
    Run scrapers across all specified platforms.
    Returns a summary dict: {platform: count_saved}
    """
    if platforms is None:
        platforms = ["linkedin", "indeed", "remoteok"]

    results = {}
    for platform in platforms:
        try:
            scraper = get_scraper(platform)
            logger.info(f"Scraping {platform} for '{query}' in '{location}'...")
            jobs = scraper.search(query, location, **kwargs)
            saved = scraper.save_jobs(jobs)
            results[platform] = {"found": len(jobs), "saved": saved}
            logger.info(f"  → {platform}: found {len(jobs)}, saved {saved} new")
        except Exception as e:
            logger.error(f"  → {platform} failed: {e}")
            results[platform] = {"found": 0, "saved": 0, "error": str(e)}

    return results
