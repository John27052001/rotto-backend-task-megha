import urllib.error
from datetime import datetime, timedelta, timezone

from hashing import make_content_hash
from removal import is_confirmed_removed_status
from repository import (
    get_detail_fetched_at,
    job_exists,
    mark_detail_fetched,
    mark_job_removed,
    mark_job_seen,
    save_job,
)
from sources.reed import discover_jobs, fetch_job
from validation import validate_job


# ---------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------

# None = process every discovered Reed job.
SAMPLE_LIMIT = None

# Known jobs get their detail page refreshed periodically
# so detail-only changes can eventually be detected.
DETAIL_REFRESH_INTERVAL = timedelta(
    hours=24
)


# ---------------------------------------------------------
# DETAIL REFRESH
# ---------------------------------------------------------

def should_refresh(job_id, observed_at):
    """
    Return True when a known listing should have its
    full detail page fetched again.
    """

    detail_fetched_at = get_detail_fetched_at(
        job_id
    )

    if detail_fetched_at is None:
        return True

    return (
        observed_at - detail_fetched_at
        >= DETAIL_REFRESH_INTERVAL
    )


# ---------------------------------------------------------
# EMPTY REPORT
# ---------------------------------------------------------

def new_report():
    return {
        "jobs_seen": 0,
        "jobs_new": 0,
        "jobs_changed": 0,
        "jobs_removed": 0,
        "jobs_failed": 0,
    }


# ---------------------------------------------------------
# CONFIRMED REMOVAL
# ---------------------------------------------------------

def handle_confirmed_removal(
    error,
    job_id,
    existing_job,
    observed_at,
    report,
):
    """
    Handle HTTP 404/410 safely.

    We only transition a row to removed when:
      1. this is an already-known database listing, and
      2. the source detail URL gives strong removal evidence.

    Returns True when the error was handled as a confirmed
    removal, otherwise False.
    """

    if not isinstance(
        error,
        urllib.error.HTTPError,
    ):
        return False

    if not is_confirmed_removed_status(
        error.code
    ):
        return False

    # A failed fetch for a newly discovered source ID is
    # not a lifecycle transition for an existing row.
    if not existing_job:
        return False

    mark_job_removed(
        job_id,
        observed_at,
    )

    report["jobs_removed"] += 1

    print(
        f"  Result: removed "
        f"(confirmed HTTP {error.code})"
    )

    return True


# ---------------------------------------------------------
# REED CRAWL
# ---------------------------------------------------------

def crawl_reed():
    """
    Run one incremental Reed crawl.

    Important lifecycle behavior:

    - newly discovered listing:
        fetch, validate and save

    - known listing with refresh not due:
        update last_seen_at without another detail request

    - known listing with refresh due:
        fetch and compare content

    - confirmed detail 404/410:
        mark an existing listing removed

    - 403/429/timeout/5xx/parser failure:
        preserve the existing row

    - absence from discovery:
        never treated as removal evidence
    """

    print(
        "Starting Reed crawl..."
    )

    print()

    report = new_report()

    observed_at = datetime.now(
        timezone.utc
    )

    # -----------------------------------------------------
    # DISCOVERY
    # -----------------------------------------------------

    try:
        discovered_jobs = discover_jobs()

    except Exception as error:

        print(
            "Reed discovery failed."
        )

        print(
            "Type:",
            type(error).__name__,
        )

        print(
            "Error:",
            error,
        )

        report["jobs_failed"] += 1

        # Most importantly: do not remove anything when
        # discovery itself failed or was incomplete.
        return report

    print(
        "Jobs discovered:",
        len(discovered_jobs),
    )

    # -----------------------------------------------------
    # PROCESSING LIMIT
    # -----------------------------------------------------

    if SAMPLE_LIMIT is None:
        jobs_to_process = discovered_jobs
    else:
        jobs_to_process = (
            discovered_jobs[
                :SAMPLE_LIMIT
            ]
        )

    # -----------------------------------------------------
    # PROCESS EACH DISCOVERED LISTING
    # -----------------------------------------------------

    for index, discovered_job in enumerate(
        jobs_to_process,
        start=1,
    ):

        source_job_id = str(
            discovered_job[
                "source_job_id"
            ]
        )

        job_id = (
            f"reed:{source_job_id}"
        )

        print()
        print(
            f"Processing "
            f"{index}/{len(jobs_to_process)}:"
        )

        print(
            discovered_job["url"]
        )

        # Determine this before fetching the detail page.
        existing_job = job_exists(
            job_id
        )

        try:

            # -------------------------------------------------
            # EXISTING LISTING
            # -------------------------------------------------

            if existing_job:

                refresh_due = should_refresh(
                    job_id,
                    observed_at,
                )

                # ---------------------------------------------
                # DETAIL REFRESH NOT DUE
                # ---------------------------------------------

                if not refresh_due:

                    # Discovery proves that this source listing
                    # is currently visible.
                    #
                    # mark_job_seen should also clear removed_at
                    # if a previously removed source listing
                    # reappears.
                    mark_job_seen(
                        job_id,
                        observed_at,
                    )

                    report[
                        "jobs_seen"
                    ] += 1

                    print(
                        "  Result: seen "
                        "(detail refresh not due)"
                    )

                    continue

                print(
                    "  Detail refresh due."
                )

            # -------------------------------------------------
            # FETCH DETAIL PAGE
            # -------------------------------------------------

            try:
                job = fetch_job(
                    discovered_job
                )

            except urllib.error.HTTPError as error:

                # 404/410 are removal evidence only for a
                # listing that already exists in our DB.
                handled = (
                    handle_confirmed_removal(
                        error,
                        job_id,
                        existing_job,
                        observed_at,
                        report,
                    )
                )

                if handled:
                    continue

                # 403, 429, 5xx, etc. are failures, NOT
                # removal evidence.
                raise

            # -------------------------------------------------
            # VALIDATION
            # -------------------------------------------------

            errors = validate_job(
                job,
                discovered_job,
            )

            if errors:

                report[
                    "jobs_failed"
                ] += 1

                print(
                    "  Result: invalid"
                )

                for error in errors:
                    print(
                        "   -",
                        error,
                    )

                # Do not change/remove an existing good row
                # because a later parse failed.
                continue

            # -------------------------------------------------
            # DATABASE FIELDS
            # -------------------------------------------------

            job["id"] = job_id

            # Deduplication runs after all sources complete
            # and can replace this with a shared cross-source
            # canonical ID.
            job[
                "canonical_job_id"
            ] = job_id

            job[
                "content_hash"
            ] = make_content_hash(
                job
            )

            # -------------------------------------------------
            # SAVE / RECONCILE
            # -------------------------------------------------

            result = save_job(
                job,
                observed_at,
            )

            # Only update detail_fetched_at after a successful
            # fetch + parse + validation + persistence cycle.
            mark_detail_fetched(
                job_id,
                observed_at,
            )

            report[
                "jobs_seen"
            ] += 1

            if result == "new":

                report[
                    "jobs_new"
                ] += 1

            elif result == "changed":

                report[
                    "jobs_changed"
                ] += 1

            print(
                "  Result:",
                result,
            )

        # -----------------------------------------------------
        # HTTP FAILURE
        # -----------------------------------------------------

        except urllib.error.HTTPError as error:

            report[
                "jobs_failed"
            ] += 1

            print(
                "  Result: HTTP ERROR"
            )

            print(
                "  Status:",
                error.code,
            )

            if error.code in (
                403,
                429,
            ):
                print(
                    "  Existing data preserved; "
                    "blocked/rate-limited response "
                    "is not removal evidence."
                )

            else:
                print(
                    "  Existing data preserved."
                )

        # -----------------------------------------------------
        # OTHER FAILURE
        # -----------------------------------------------------

        except Exception as error:

            report[
                "jobs_failed"
            ] += 1

            print(
                "  Result: ERROR"
            )

            print(
                "  Type:",
                type(error).__name__,
            )

            print(
                "  Message:",
                error,
            )

            print(
                "  Existing data preserved."
            )

    # ---------------------------------------------------------
    # IMPORTANT:
    # ---------------------------------------------------------
    #
    # We intentionally DO NOT compare every database Reed row
    # against this discovery result and remove missing IDs.
    #
    # Search discovery is not guaranteed to be complete or
    # authoritative. Therefore absence from these results is
    # not sufficient evidence that a job disappeared.
    # ---------------------------------------------------------

    print()
    print(
        "=" * 60
    )

    print(
        "REED CRAWL REPORT"
    )

    print(
        "=" * 60
    )

    for key, value in report.items():

        print(
            f"{key}: {value}"
        )

    return report


# ---------------------------------------------------------
# RUN DIRECTLY
# ---------------------------------------------------------

if __name__ == "__main__":
    crawl_reed()