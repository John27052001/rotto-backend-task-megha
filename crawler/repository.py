from database import get_connection


# ---------------------------------------------------------
# GET ONE JOB
# ---------------------------------------------------------

def get_job(job_id):
    """
    Return one job from PostgreSQL.

    Returns None if the job does not exist.
    """

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT *
        FROM jobs
        WHERE id = %s;
        """,
        (job_id,),
    )

    job = cursor.fetchone()

    cursor.close()
    connection.close()

    return job


# ---------------------------------------------------------
# CHECK WHETHER A JOB EXISTS
# ---------------------------------------------------------

def job_exists(job_id):
    """
    Return True if the job already exists.
    Otherwise return False.
    """

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT 1
        FROM jobs
        WHERE id = %s;
        """,
        (job_id,),
    )

    exists = cursor.fetchone() is not None

    cursor.close()
    connection.close()

    return exists


# ---------------------------------------------------------
# GET CONTENT HASH
# ---------------------------------------------------------

def get_content_hash(job_id):
    """
    Return the stored content hash for a job.
    """

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT content_hash
        FROM jobs
        WHERE id = %s;
        """,
        (job_id,),
    )

    row = cursor.fetchone()

    cursor.close()
    connection.close()

    if row is None:
        return None

    return row[0]


# ---------------------------------------------------------
# GET LAST SEEN TIME
# ---------------------------------------------------------

def get_last_seen_at(job_id):
    """
    Return when the listing was last observed alive.

    This is NOT the same as the last detail fetch.
    """

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT last_seen_at
        FROM jobs
        WHERE id = %s;
        """,
        (job_id,),
    )

    row = cursor.fetchone()

    cursor.close()
    connection.close()

    if row is None:
        return None

    return row[0]


# ---------------------------------------------------------
# GET DETAIL FETCH TIME
# ---------------------------------------------------------

def get_detail_fetched_at(job_id):
    """
    Return when the full job detail page was last
    successfully fetched.

    None means we have not recorded a detail fetch yet.
    """

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT detail_fetched_at
        FROM jobs
        WHERE id = %s;
        """,
        (job_id,),
    )

    row = cursor.fetchone()

    cursor.close()
    connection.close()

    if row is None:
        return None

    return row[0]


# ---------------------------------------------------------
# MARK JOB AS SEEN
# ---------------------------------------------------------

def mark_job_seen(job_id, observed_at):
    """
    Record that discovery saw this listing alive.

    Important:
    This changes last_seen_at but DOES NOT change
    detail_fetched_at.
    """

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE jobs
        SET
            last_seen_at = %s,
            removed_at = NULL
        WHERE id = %s;
        """,
        (
            observed_at,
            job_id,
        ),
    )

    connection.commit()

    cursor.close()
    connection.close()


# ---------------------------------------------------------
# MARK DETAIL PAGE AS FETCHED
# ---------------------------------------------------------

def mark_detail_fetched(job_id, fetched_at):
    """
    Record that we successfully fetched the full
    detail page for this job.
    """

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE jobs
        SET detail_fetched_at = %s
        WHERE id = %s;
        """,
        (
            fetched_at,
            job_id,
        ),
    )

    connection.commit()

    cursor.close()
    connection.close()


# ---------------------------------------------------------
# SAVE / RECONCILE JOB
# ---------------------------------------------------------

def save_job(job, observed_at=None):
    """
    Insert or update one normalized job.

    Returns:

        "new"
        "changed"
        "unchanged"

    observed_at is the time THIS crawl observed the job.

    The lifecycle behavior is:

    New ID
        -> insert
        -> first_seen_at = observed_at
        -> last_seen_at  = observed_at

    Existing ID + same content hash
        -> preserve content
        -> update last_seen_at
        -> clear removed_at

    Existing ID + different content hash
        -> update job content
        -> preserve first_seen_at
        -> update last_seen_at
        -> clear removed_at
    """

    # -----------------------------------------------------
    # BACKWARD COMPATIBILITY
    # -----------------------------------------------------
    #
    # Some of our earlier tests put first_seen_at and
    # last_seen_at directly inside the job dictionary.
    #
    # If observed_at was not supplied explicitly, use
    # those values.
    # -----------------------------------------------------

    if observed_at is None:
        observed_at = (
            job.get("last_seen_at")
            or job.get("first_seen_at")
        )

    if observed_at is None:
        raise ValueError(
            "save_job requires observed_at"
        )

    job_id = job["id"]

    connection = get_connection()
    cursor = connection.cursor()

    # -----------------------------------------------------
    # CHECK EXISTING ROW
    # -----------------------------------------------------

    cursor.execute(
        """
        SELECT
            content_hash,
            removed_at
        FROM jobs
        WHERE id = %s;
        """,
        (job_id,),
    )

    existing = cursor.fetchone()

    # -----------------------------------------------------
    # NEW JOB
    # -----------------------------------------------------

    if existing is None:

        cursor.execute(
            """
            INSERT INTO jobs (
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
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, NULL
            );
            """,
            (
                job["id"],
                job["source"],
                job["source_job_id"],
                job["url"],
                job["title"],
                job.get("company"),
                job.get("company_logo_url"),
                job["location"],
                job.get("work_type"),
                job.get("salary_min"),
                job.get("salary_max"),
                job.get("salary_period"),
                job.get("posted_at"),
                job["description"],
                job["canonical_job_id"],
                job["content_hash"],
                observed_at,
                observed_at,
            ),
        )

        connection.commit()

        cursor.close()
        connection.close()

        return "new"

    # -----------------------------------------------------
    # EXISTING JOB
    # -----------------------------------------------------

    old_content_hash = existing[0]

    # -----------------------------------------------------
    # CONTENT DID NOT CHANGE
    # -----------------------------------------------------

    if old_content_hash == job["content_hash"]:

        cursor.execute(
            """
            UPDATE jobs
            SET
                last_seen_at = %s,
                removed_at = NULL
            WHERE id = %s;
            """,
            (
                observed_at,
                job_id,
            ),
        )

        connection.commit()

        cursor.close()
        connection.close()

        return "unchanged"

    # -----------------------------------------------------
    # CONTENT CHANGED
    # -----------------------------------------------------

    cursor.execute(
        """
        UPDATE jobs
        SET
            source = %s,
            source_job_id = %s,
            url = %s,
            title = %s,
            company = %s,
            company_logo_url = %s,
            location = %s,
            work_type = %s,
            salary_min = %s,
            salary_max = %s,
            salary_period = %s,
            posted_at = %s,
            description = %s,
            canonical_job_id = %s,
            content_hash = %s,
            last_seen_at = %s,
            removed_at = NULL
        WHERE id = %s;
        """,
        (
            job["source"],
            job["source_job_id"],
            job["url"],
            job["title"],
            job.get("company"),
            job.get("company_logo_url"),
            job["location"],
            job.get("work_type"),
            job.get("salary_min"),
            job.get("salary_max"),
            job.get("salary_period"),
            job.get("posted_at"),
            job["description"],
            job["canonical_job_id"],
            job["content_hash"],
            observed_at,
            job_id,
        ),
    )

    connection.commit()

    cursor.close()
    connection.close()

    return "changed"


# ---------------------------------------------------------
# MARK JOB REMOVED
# ---------------------------------------------------------

def mark_job_removed(job_id, removed_at=None):
    """
    Mark a job as removed.

    Returns True only when the job changes from:

        live -> removed

    Returns False when:

        - job does not exist
        - job was already removed

    This makes repeated removal observations idempotent.
    """

    # Compatibility with our earlier test helper.
    if removed_at is None:
        from datetime import datetime, timezone

        removed_at = datetime.now(
            timezone.utc
        )

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE jobs
        SET removed_at = %s
        WHERE id = %s
          AND removed_at IS NULL;
        """,
        (
            removed_at,
            job_id,
        ),
    )

    # rowcount tells us whether PostgreSQL actually
    # changed a live row.
    was_removed = (
        cursor.rowcount > 0
    )

    connection.commit()

    cursor.close()
    connection.close()

    return was_removed