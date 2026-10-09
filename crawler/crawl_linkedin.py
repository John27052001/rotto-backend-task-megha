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
from sources.linkedin import discover_jobs, fetch_job
from validation import validate_job


# ---------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------

# None = process every discovered LinkedIn job.
SAMPLE_LIMIT = None

# Periodically refresh known detail pages so changes that
# are not visible during discovery can still be detected.
DETAIL_REFRESH_INTERVAL = timedelta(
    hours=24
)


# ---------------------------------------------------------
# DETAIL REFRESH
# ---------------------------------------------------------

def should_refresh(job_id, observed_at):
    """
    Return True when an existing LinkedIn listing should
    have its full detail page fetched again.
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
# REPORT
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
    Mark an existing listing removed only when its public
    detail URL returns strong removal evidence.

    404 and 410 qualify.

    403, 429, timeouts, server errors, failed discovery and
    absence from search results do not qualify.
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

    # A failed detail request for a source ID that we have
    # never stored is not a removal transition.
    if not existing_job:
        return False

    mark_job_removed(
        job_id,
        observed_at,
    )

    report[
        "jobs_removed"
    ] += 1

    print(
        f"  Result: removed "
        f"(confirmed HTTP {error.code})"
    )

    return True


# ---------------------------------------------------------
# LINKEDIN CRAWL
# ---------------------------------------------------------

def crawl_linkedin():
    """
    Run one incremental LinkedIn crawl.

    New listing:
        fetch -> validate -> hash -> save

    Existing listing, refresh not due:
        update last_seen_at only

    Existing listing, refresh due:
        fetch detail and reconcile changes

    Existing listing returning 404/410:
        mark removed

    Blocked/error response:
        preserve existing good data

    Missing from search:
        do not mark removed
    """

    print(
        "Starting LinkedIn crawl..."
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
            "LinkedIn discovery failed."
        )

        print(
            "Type:",
            type(error).__name__,
        )

        print(
            "Error:",
            error,
        )

        report[
            "jobs_failed"
        ] += 1

        # A failed or blocked discovery run must never
        # remove existing rows.
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
    # PROCESS DISCOVERED JOBS
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
            f"linkedin:{source_job_id}"
        )

        print()
        print(
            f"Processing "
            f"{index}/{len(jobs_to_process)}:"
        )

        print(
            discovered_job["url"]
        )

        # Determine whether the source listing was already
        # stored before making the detail request.
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

                    # Discovery itself confirms that this
                    # listing remains visible.
                    #
                    # mark_job_seen should also clear
                    # removed_at when a previously removed
                    # listing reappears.
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

                # Anything other than confirmed 404/410
                # remains an ordinary crawl failure.
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

                # Never damage an existing good row because
                # a later parse or validation failed.
                continue

            # -------------------------------------------------
            # DATABASE FIELDS
            # -------------------------------------------------

            job["id"] = job_id

            # Every source listing starts in its own
            # canonical group. The cross-source dedupe pass
            # runs after all crawlers finish.
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

            # Only record a detail fetch after the page was
            # successfully fetched, parsed, validated and
            # persisted.
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
    # SAFE ABSENCE POLICY
    # ---------------------------------------------------------
    #
    # We intentionally do NOT remove database rows merely
    # because their IDs were absent from this LinkedIn search
    # result.
    #
    # Search results may be incomplete, paginated, blocked,
    # personalized or otherwise non-authoritative.
    # ---------------------------------------------------------

    print()
    print(
        "=" * 60
    )

    print(
        "LINKEDIN CRAWL REPORT"
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
    crawl_linkedin()