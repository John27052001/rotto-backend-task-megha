import hashlib
import json


def make_content_hash(job):
    content = {
        "url": job.get("url"),
        "title": job.get("title"),
        "company": job.get("company"),
        "company_logo_url": job.get("company_logo_url"),
        "location": job.get("location"),
        "work_type": job.get("work_type"),
        "salary_min": job.get("salary_min"),
        "salary_max": job.get("salary_max"),
        "salary_period": job.get("salary_period"),
        "posted_at": str(job.get("posted_at")),
        "description": job.get("description"),
    }

    text = json.dumps(content, sort_keys=True)

    return hashlib.sha256(text.encode("utf-8")).hexdigest()