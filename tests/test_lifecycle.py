import json
import os
import sys

# Allow the test file to import code from the crawler folder.
sys.path.insert(0, "crawler")

from database import get_connection
from reconciliation import reconcile_run


# Use Rotto's public fixture by default.
# Their grader can provide a different fixture using FIXTURE_PATH.
FIXTURE_PATH = os.getenv(
    "FIXTURE_PATH",
    "tests/fixtures/lifecycle.json",
)


def reset_test_database():
    """
    Start the lifecycle test with an empty jobs table.
    This must ONLY run against rotto_test.
    """
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("DELETE FROM jobs;")

    connection.commit()

    cursor.close()
    connection.close()


def get_job(job_id):
    """
    Get the fields we need to verify for one stored job.
    """
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            id,
            title,
            content_hash,
            first_seen_at,
            last_seen_at,
            removed_at
        FROM jobs
        WHERE id = %s;
        """,
        (job_id,),
    )

    row = cursor.fetchone()

    cursor.close()
    connection.close()

    return row


def format_time(value):
    """
    Convert PostgreSQL timestamps into the same format
    used by Rotto's fixture.

    Example:
    2026-10-01T09:00:00+00:00
                becomes
    2026-10-01T09:00:00Z
    """
    if value is None:
        return None

    return value.isoformat().replace("+00:00", "Z")


def main():

    # --------------------------------------------------
    # SAFETY CHECK
    # --------------------------------------------------
    # Never allow this test to delete rows from the
    # normal crawler database.
    # --------------------------------------------------

    if os.getenv("DB_NAME") != "rotto_test":
        raise RuntimeError(
            "Lifecycle tests must run with DB_NAME=rotto_test"
        )

    # --------------------------------------------------
    # LOAD FIXTURE
    # --------------------------------------------------

    with open(FIXTURE_PATH) as file:
        fixture = json.load(file)

    # Start with an empty test database.
    reset_test_database()

    # Store hashes from earlier runs.
    #
    # This lets us verify things such as:
    #
    # "Job 101 was not detail-refreshed, therefore its
    # content hash should still equal the initial run."
    saved_hashes = {}

    # --------------------------------------------------
    # PROCESS EVERY FIXTURE RUN IN ORDER
    # --------------------------------------------------

    for run in fixture["runs"]:

        print()
        print("Testing run:", run["name"])

        # ==============================================
        # FIRST APPLICATION
        # ==============================================

        actual_report = reconcile_run(run)
        expected_report = run["expected"]["report"]

        # Check lifecycle counters.
        assert actual_report == expected_report, (
            f"Report mismatch for {run['name']}\n"
            f"Expected: {expected_report}\n"
            f"Actual:   {actual_report}"
        )

        print("  Report: PASS")

        # ==============================================
        # CHECK DATABASE ROWS
        # ==============================================

        for job_id, expected in run["expected"]["rows"].items():

            row = get_job(job_id)

            # The expected job must exist.
            assert row is not None, (
                f"{job_id} is missing after {run['name']}"
            )

            (
                actual_id,
                actual_title,
                actual_hash,
                actual_first_seen,
                actual_last_seen,
                actual_removed,
            ) = row

            # ------------------------------------------
            # Check ID
            # ------------------------------------------

            assert actual_id == job_id, (
                f"ID mismatch for {job_id}"
            )

            # ------------------------------------------
            # Check title
            # ------------------------------------------

            assert actual_title == expected["title"], (
                f"Title mismatch for {job_id}\n"
                f"Expected: {expected['title']}\n"
                f"Actual:   {actual_title}"
            )

            # ------------------------------------------
            # Check first_seen_at
            # ------------------------------------------

            assert (
                format_time(actual_first_seen)
                == expected["first_seen_at"]
            ), (
                f"first_seen_at mismatch for {job_id}\n"
                f"Expected: {expected['first_seen_at']}\n"
                f"Actual:   {format_time(actual_first_seen)}"
            )

            # ------------------------------------------
            # Check last_seen_at
            # ------------------------------------------

            assert (
                format_time(actual_last_seen)
                == expected["last_seen_at"]
            ), (
                f"last_seen_at mismatch for {job_id}\n"
                f"Expected: {expected['last_seen_at']}\n"
                f"Actual:   {format_time(actual_last_seen)}"
            )

            # ------------------------------------------
            # Check removed_at
            # ------------------------------------------

            assert (
                format_time(actual_removed)
                == expected["removed_at"]
            ), (
                f"removed_at mismatch for {job_id}\n"
                f"Expected: {expected['removed_at']}\n"
                f"Actual:   {format_time(actual_removed)}"
            )

            # ------------------------------------------
            # Check content hash
            # ------------------------------------------

            hash_run = expected["content_hash_equals_run"]

            if hash_run is not None:

                old_hash = saved_hashes[(hash_run, job_id)]

                assert actual_hash == old_hash, (
                    f"Hash changed unexpectedly for {job_id}\n"
                    f"Expected hash from run: {hash_run}"
                )

            # Remember this job's hash after this run.
            saved_hashes[(run["name"], job_id)] = actual_hash

        print("  Rows: PASS")

        # ==============================================
        # IDEMPOTENCY TEST
        # ==============================================
        #
        # Run the EXACT SAME crawl observation again.
        #
        # Nothing should be considered:
        # - new
        # - changed
        # - removed
        #
        # ==============================================

        replay_report = reconcile_run(run)

        expected_replay_report = {
            "jobs_new": 0,
            "jobs_changed": 0,
            "jobs_removed": 0,
        }

        assert replay_report == expected_replay_report, (
            f"Replay was not idempotent for {run['name']}\n"
            f"Expected: {expected_replay_report}\n"
            f"Actual:   {replay_report}"
        )

        print("  Replay: PASS")

    # --------------------------------------------------
    # EVERYTHING PASSED
    # --------------------------------------------------

    print()
    print("ALL LIFECYCLE TESTS PASSED!")


if __name__ == "__main__":
    main()