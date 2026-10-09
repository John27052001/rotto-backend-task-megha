import re
import unicodedata
from difflib import SequenceMatcher

from database import get_connection


def normalize_text(value):
    if not value:
        return ""

    value = unicodedata.normalize(
        "NFKD",
        str(value),
    )

    value = value.lower()

    value = re.sub(
        r"[^a-z0-9]+",
        " ",
        value,
    )

    return " ".join(
        value.split()
    )


def text_similarity(left, right):
    left = normalize_text(left)
    right = normalize_text(right)

    if not left or not right:
        return 0.0

    return SequenceMatcher(
        None,
        left,
        right,
    ).ratio()


def same_company(left, right):
    left = normalize_text(left)
    right = normalize_text(right)

    if not left or not right:
        return False

    return left == right


def same_location(left, right):
    left = normalize_text(left)
    right = normalize_text(right)

    if not left or not right:
        return False

    if left == right:
        return True

    # Allow small source formatting differences such as:
    # "London" vs "London, England, United Kingdom"
    return (
        left in right
        or right in left
    )


def jobs_are_duplicates(a, b):
    """
    Conservative cross-source duplicate matcher.

    We deliberately require:
      - different sources
      - same company
      - very similar title
      - compatible location
      - supporting description similarity

    High precision is more important than aggressively
    linking uncertain listings.
    """

    if a["source"] == b["source"]:
        return False

    if not same_company(
        a["company"],
        b["company"],
    ):
        return False

    title_score = text_similarity(
        a["title"],
        b["title"],
    )

    if title_score < 0.90:
        return False

    if not same_location(
        a["location"],
        b["location"],
    ):
        return False

    description_score = text_similarity(
        a["description"],
        b["description"],
    )

    # Exact/near-exact title + company + location is already
    # strong evidence, but require some description overlap.
    if description_score < 0.45:
        return False

    return True


def load_live_jobs():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            id,
            source,
            source_job_id,
            title,
            company,
            location,
            description,
            canonical_job_id
        FROM jobs
        WHERE removed_at IS NULL
        ORDER BY id;
        """
    )

    rows = cursor.fetchall()

    cursor.close()
    connection.close()

    columns = [
        "id",
        "source",
        "source_job_id",
        "title",
        "company",
        "location",
        "description",
        "canonical_job_id",
    ]

    return [
        dict(zip(columns, row))
        for row in rows
    ]


def update_canonical_ids(updates):
    if not updates:
        return

    connection = get_connection()
    cursor = connection.cursor()

    for job_id, canonical_job_id in updates.items():
        cursor.execute(
            """
            UPDATE jobs
            SET canonical_job_id = %s
            WHERE id = %s;
            """,
            (
                canonical_job_id,
                job_id,
            ),
        )

    connection.commit()

    cursor.close()
    connection.close()


def deduplicate_jobs():
    """
    Link conservative cross-source duplicate groups.

    Every unmatched job keeps itself as its canonical ID.
    """

    jobs = load_live_jobs()

    # Start every listing in its own canonical group.
    canonical = {
        job["id"]: job["id"]
        for job in jobs
    }

    # Compare cross-source pairs.
    for index, left in enumerate(jobs):

        for right in jobs[
            index + 1:
        ]:

            if not jobs_are_duplicates(
                left,
                right,
            ):
                continue

            left_canonical = canonical[
                left["id"]
            ]

            right_canonical = canonical[
                right["id"]
            ]

            # Stable deterministic canonical ID.
            chosen = min(
                left_canonical,
                right_canonical,
            )

            replaced = max(
                left_canonical,
                right_canonical,
            )

            # Merge the complete existing group, not only
            # this pair.
            for job_id, value in list(
                canonical.items()
            ):
                if value == replaced:
                    canonical[job_id] = chosen

            canonical[left["id"]] = chosen
            canonical[right["id"]] = chosen

    update_canonical_ids(
        canonical
    )

    groups = {}

    for job_id, canonical_id in canonical.items():
        groups.setdefault(
            canonical_id,
            [],
        ).append(job_id)

    duplicate_groups = [
        members
        for members in groups.values()
        if len(members) > 1
    ]

    duplicates_linked = sum(
        len(group)
        for group in duplicate_groups
    )

    print()
    print("=" * 60)
    print("DEDUPLICATION REPORT")
    print("=" * 60)
    print(
        "Live jobs:",
        len(jobs),
    )
    print(
        "Duplicate groups:",
        len(duplicate_groups),
    )
    print(
        "Listings linked:",
        duplicates_linked,
    )

    return {
        "duplicate_groups": len(
            duplicate_groups
        ),
        "duplicates_linked": (
            duplicates_linked
        ),
    }


if __name__ == "__main__":
    deduplicate_jobs()