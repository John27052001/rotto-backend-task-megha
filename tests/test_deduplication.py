import sys

sys.path.insert(0, "crawler")

from deduplication import (
    jobs_are_duplicates,
)


def job(
    source,
    title,
    company,
    location,
    description,
):
    return {
        "source": source,
        "title": title,
        "company": company,
        "location": location,
        "description": description,
    }


# Same real-world job on two boards.
reed_job = job(
    "reed",
    "Senior Software Engineer",
    "Example Technologies Ltd",
    "London, England",
    (
        "We are looking for a Senior Software Engineer "
        "to build backend services using Python and AWS. "
        "You will work with product and engineering teams."
    ),
)

linkedin_job = job(
    "linkedin",
    "Senior Software Engineer",
    "Example Technologies Ltd",
    "London, England, United Kingdom",
    (
        "We are looking for a Senior Software Engineer "
        "to build backend services using Python and AWS. "
        "You will work with product and engineering teams."
    ),
)


# Similar title, but different company.
different_company = job(
    "linkedin",
    "Senior Software Engineer",
    "Different Company",
    "London, England",
    reed_job["description"],
)


# Same company/location but clearly different role.
different_role = job(
    "linkedin",
    "Marketing Manager",
    "Example Technologies Ltd",
    "London, England",
    (
        "Lead marketing campaigns, brand strategy and "
        "customer acquisition."
    ),
)


assert jobs_are_duplicates(
    reed_job,
    linkedin_job,
) is True


assert jobs_are_duplicates(
    reed_job,
    different_company,
) is False


assert jobs_are_duplicates(
    reed_job,
    different_role,
) is False


# Same source must never be cross-source deduplicated.
same_source = dict(
    linkedin_job
)

same_source["source"] = "reed"

assert jobs_are_duplicates(
    reed_job,
    same_source,
) is False


print(
    "ALL DEDUPLICATION TESTS PASSED!"
)