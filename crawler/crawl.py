import json
import os
from datetime import datetime, timezone
from decimal import Decimal

from crawl_linkedin import crawl_linkedin
from crawl_reed import crawl_reed
from database import get_connection
from deduplication import deduplicate_jobs
from request_stats import (
    get_request_stats,
    reset_request_stats,
)


# ---------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------

OUTPUT_DIR = "output"


# ---------------------------------------------------------
# TIME
# ---------------------------------------------------------

def utc_now():
    return datetime.now(
        timezone.utc
    )


# ---------------------------------------------------------
# JSON VALUE CONVERSION
# ---------------------------------------------------------

def iso_value(value):
    """
    Convert database values into JSON-safe values.
    """

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, Decimal):
        return float(value)

    return value


# ---------------------------------------------------------
# INDEED
# ---------------------------------------------------------

def crawl_indeed_safely():
    """
    Attempt Indeed discovery without allowing a blocked
    Indeed request to stop Reed or LinkedIn.

    A blocked/incomplete Indeed crawl is NOT treated as
    removal evidence.
    """

    report = {
        "jobs_seen": 0,
        "jobs_new": 0,
        "jobs_changed": 0,
        "jobs_removed": 0,
        "jobs_failed": 0,
    }

    try:
        from sources.indeed import discover_jobs

        discovered_jobs = discover_jobs()

        print(
            "Indeed jobs discovered:",
            len(discovered_jobs),
        )

        # Indeed detail parsing is not yet available for
        # the blocked response format.
        #
        # Do not pretend these results were processed.
        if discovered_jobs:
            print(
                "Indeed discovery returned jobs, "
                "but full processing is not yet enabled."
            )

    except Exception as error:

        report["jobs_failed"] += 1

        print()
        print(
            "Indeed crawl unavailable."
        )

        print(
            "Type:",
            type(error).__name__,
        )

        print(
            "Message:",
            error,
        )

    return report


# ---------------------------------------------------------
# EXPORT ALL JOBS
# ---------------------------------------------------------

def export_jobs():
    """
    Export every stored row, including removed jobs,
    to output/jobs.jsonl.
    """

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True,
    )

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            id,
            source,
            source_job_id,
            url,
            title,
            company,
            company_logo_url,
            location,
            work_type,
            salary_min,
            salary_max,
            salary_period,
            posted_at,
            description,
            canonical_job_id,
            content_hash,
            first_seen_at,
            last_seen_at,
            removed_at
        FROM jobs
        ORDER BY source, source_job_id;
        """
    )

    columns = [
        description.name
        for description in cursor.description
    ]

    rows = cursor.fetchall()

    cursor.close()
    connection.close()

    output_path = os.path.join(
        OUTPUT_DIR,
        "jobs.jsonl",
    )

    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as file:

        for row in rows:

            job = {}

            for column, value in zip(
                columns,
                row,
            ):
                job[column] = iso_value(
                    value
                )

            file.write(
                json.dumps(
                    job,
                    ensure_ascii=False,
                )
            )

            file.write("\n")

    return len(rows)


# ---------------------------------------------------------
# LIVE JOB COUNTS BY SOURCE
# ---------------------------------------------------------

def get_jobs_by_source():
    """
    Count currently live stored listings by source.
    """

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            source,
            COUNT(*)
        FROM jobs
        WHERE removed_at IS NULL
        GROUP BY source
        ORDER BY source;
        """
    )

    rows = cursor.fetchall()

    cursor.close()
    connection.close()

    result = {
        "indeed": 0,
        "linkedin": 0,
        "reed": 0,
    }

    for source, count in rows:
        result[source] = count

    return result


# ---------------------------------------------------------
# OPTIONAL DATABASE DEDUPE COUNT
# ---------------------------------------------------------

def get_duplicates_linked():
    """
    Count listings participating in canonical groups
    containing more than one source listing.

    The main report uses the result returned directly by
    deduplicate_jobs(), but this helper is useful for
    verification/debugging.
    """

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT COALESCE(
            SUM(group_size),
            0
        )
        FROM (
            SELECT
                canonical_job_id,
                COUNT(*) AS group_size
            FROM jobs
            WHERE canonical_job_id IS NOT NULL
            GROUP BY canonical_job_id
            HAVING COUNT(*) > 1
        ) groups;
        """
    )

    value = cursor.fetchone()[0]

    cursor.close()
    connection.close()

    return int(
        value or 0
    )


# ---------------------------------------------------------
# COMBINE SOURCE REPORTS
# ---------------------------------------------------------

def combine_reports(*reports):
    """
    Combine per-source lifecycle counts into one run report.
    """

    combined = {
        "jobs_new": 0,
        "jobs_changed": 0,
        "jobs_removed": 0,
    }

    for report in reports:

        if not report:
            continue

        combined["jobs_new"] += report.get(
            "jobs_new",
            0,
        )

        combined["jobs_changed"] += report.get(
            "jobs_changed",
            0,
        )

        combined["jobs_removed"] += report.get(
            "jobs_removed",
            0,
        )

    return combined


# ---------------------------------------------------------
# WRITE REPORT.JSON
# ---------------------------------------------------------

def write_report(
    started_at,
    finished_at,
    lifecycle,
    dedupe_report,
):
    """
    Write the required output/report.json.
    """

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True,
    )

    request_stats = get_request_stats()

    report = {
        "started_at": (
            started_at.isoformat()
        ),
        "finished_at": (
            finished_at.isoformat()
        ),

        "requests_total": (
            request_stats[
                "requests_total"
            ]
        ),

        "requests_blocked": (
            request_stats[
                "requests_blocked"
            ]
        ),

        "requests_by_status": (
            request_stats[
                "requests_by_status"
            ]
        ),

        "jobs_by_source": (
            get_jobs_by_source()
        ),

        "duplicates_linked": (
            dedupe_report.get(
                "duplicates_linked",
                0,
            )
        ),

        "jobs_new": (
            lifecycle[
                "jobs_new"
            ]
        ),

        "jobs_removed": (
            lifecycle[
                "jobs_removed"
            ]
        ),

        "jobs_changed": (
            lifecycle[
                "jobs_changed"
            ]
        ),

        # We will finalize the proxy-cost calculation
        # before submission.
        "estimated_cost_usd": 0.0,
    }

    output_path = os.path.join(
        OUTPUT_DIR,
        "report.json",
    )

    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            report,
            file,
            indent=2,
            ensure_ascii=False,
        )

        file.write("\n")

    return report


# ---------------------------------------------------------
# MASTER CRAWL
# ---------------------------------------------------------

def main():
    """
    Run the complete live crawl.

    This is the entry point used by:

        make crawl
    """

    print(
        "=" * 60
    )

    print(
        "ROTTO JOB CRAWL"
    )

    print(
        "=" * 60
    )

    started_at = utc_now()

    # Every make crawl run gets fresh request counters.
    reset_request_stats()

    # -----------------------------------------------------
    # INDEED
    # -----------------------------------------------------

    print()
    print(
        "=" * 60
    )
    print(
        "INDEED"
    )
    print(
        "=" * 60
    )

    indeed_report = (
        crawl_indeed_safely()
    )

    # -----------------------------------------------------
    # LINKEDIN
    # -----------------------------------------------------

    print()
    print(
        "=" * 60
    )
    print(
        "LINKEDIN"
    )
    print(
        "=" * 60
    )

    try:
        linkedin_report = (
            crawl_linkedin()
        )

    except Exception as error:

        print()
        print(
            "LinkedIn crawl failed."
        )

        print(
            "Type:",
            type(error).__name__,
        )

        print(
            "Message:",
            error,
        )

        linkedin_report = {
            "jobs_seen": 0,
            "jobs_new": 0,
            "jobs_changed": 0,
            "jobs_removed": 0,
            "jobs_failed": 1,
        }

    # -----------------------------------------------------
    # REED
    # -----------------------------------------------------

    print()
    print(
        "=" * 60
    )
    print(
        "REED"
    )
    print(
        "=" * 60
    )

    try:
        reed_report = crawl_reed()

    except Exception as error:

        print()
        print(
            "Reed crawl failed."
        )

        print(
            "Type:",
            type(error).__name__,
        )

        print(
            "Message:",
            error,
        )

        reed_report = {
            "jobs_seen": 0,
            "jobs_new": 0,
            "jobs_changed": 0,
            "jobs_removed": 0,
            "jobs_failed": 1,
        }

    # -----------------------------------------------------
    # COMBINE LIFECYCLE COUNTS
    # -----------------------------------------------------

    lifecycle = combine_reports(
        indeed_report,
        linkedin_report,
        reed_report,
    )

    # -----------------------------------------------------
    # CROSS-SOURCE DEDUPLICATION
    # -----------------------------------------------------

    print()
    print(
        "Running cross-source deduplication..."
    )

    try:
        dedupe_report = (
            deduplicate_jobs()
        )

    except Exception as error:

        print(
            "Deduplication failed."
        )

        print(
            "Type:",
            type(error).__name__,
        )

        print(
            "Message:",
            error,
        )

        # Do not lose otherwise valid crawl output because
        # the dedupe phase failed.
        dedupe_report = {
            "duplicate_groups": 0,
            "duplicates_linked": 0,
        }

    # -----------------------------------------------------
    # EXPORT DATABASE
    # -----------------------------------------------------

    print()
    print(
        "Exporting jobs..."
    )

    exported_rows = export_jobs()

    # Finish timestamp should represent completion of the
    # crawl and export work.
    finished_at = utc_now()

    # -----------------------------------------------------
    # FINAL REPORT
    # -----------------------------------------------------

    report = write_report(
        started_at,
        finished_at,
        lifecycle,
        dedupe_report,
    )

    # -----------------------------------------------------
    # DISPLAY SUMMARY
    # -----------------------------------------------------

    print()
    print(
        "=" * 60
    )

    print(
        "FINAL CRAWL REPORT"
    )

    print(
        "=" * 60
    )

    print(
        "Exported rows:",
        exported_rows,
    )

    print(
        "Started:",
        report[
            "started_at"
        ],
    )

    print(
        "Finished:",
        report[
            "finished_at"
        ],
    )

    print(
        "Requests total:",
        report[
            "requests_total"
        ],
    )

    print(
        "Requests blocked:",
        report[
            "requests_blocked"
        ],
    )

    print(
        "Requests by status:",
        report[
            "requests_by_status"
        ],
    )

    print(
        "Jobs by source:",
        report[
            "jobs_by_source"
        ],
    )

    print(
        "Duplicates linked:",
        report[
            "duplicates_linked"
        ],
    )

    print(
        "Jobs new:",
        report[
            "jobs_new"
        ],
    )

    print(
        "Jobs removed:",
        report[
            "jobs_removed"
        ],
    )

    print(
        "Jobs changed:",
        report[
            "jobs_changed"
        ],
    )

    print(
        "Estimated cost USD:",
        report[
            "estimated_cost_usd"
        ],
    )

    print()
    print(
        "Wrote output/jobs.jsonl"
    )

    print(
        "Wrote output/report.json"
    )

    return report


# ---------------------------------------------------------
# RUN DIRECTLY
# ---------------------------------------------------------

if __name__ == "__main__":
    main()