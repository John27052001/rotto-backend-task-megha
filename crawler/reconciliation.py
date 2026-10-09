from datetime import datetime

from hashing import make_content_hash
from repository import (
    mark_job_removed,
    mark_job_seen,
    save_job,
)


def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def reconcile_run(run):
    observed_at = parse_time(run["observed_at"])
    source = run["source"]

    report = {
        "jobs_new": 0,
        "jobs_changed": 0,
        "jobs_removed": 0,
    }

    # -------------------------------------------------
    # 1. Process jobs that were discovered in this run.
    # -------------------------------------------------

    detail_ids = {
        job["source_job_id"]
        for job in run["details"]
    }

    for source_job_id in run["discovered_source_job_ids"]:

        # If we fetched fresh details, save_job() will handle it later.
        if source_job_id in detail_ids:
            continue

        job_id = f"{source}:{source_job_id}"

        # We saw the listing, so we know it is still live.
        mark_job_seen(
            job_id,
            observed_at,
        )

    # -------------------------------------------------
    # 2. Process successfully fetched job details.
    # -------------------------------------------------

    for job in run["details"]:

        job = job.copy()

        job["id"] = f'{job["source"]}:{job["source_job_id"]}'

        # We'll improve deduplication later.
        # For now every source listing gets its own canonical id.
        job["canonical_job_id"] = job["id"]

        job["content_hash"] = make_content_hash(job)

        result = save_job(
            job,
            observed_at,
        )

        if result == "new":
            report["jobs_new"] += 1

        elif result == "changed":
            report["jobs_changed"] += 1

    # -------------------------------------------------
    # 3. Process jobs with explicit removal evidence.
    # -------------------------------------------------

    for source_job_id in run["confirmed_removed_source_job_ids"]:

        job_id = f"{source}:{source_job_id}"

        was_removed = mark_job_removed(
            job_id,
            observed_at,
        )

        if was_removed:
            report["jobs_removed"] += 1

    return report