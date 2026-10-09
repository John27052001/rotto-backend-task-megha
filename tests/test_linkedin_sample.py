import sys

sys.path.insert(0, "crawler")

from sources.linkedin import discover_jobs, fetch_job
from validation import validate_job


jobs = discover_jobs()

valid = 0
failed = 0

print()
print("Testing first 5 LinkedIn jobs...")
print("=" * 60)

for i, discovered in enumerate(jobs[:5], start=1):
    print()
    print(f"JOB {i} OF 5")
    print("ID:", discovered["source_job_id"])

    try:
        job = fetch_job(discovered)

        errors = validate_job(
            job,
            discovered,
        )

        if errors:
            failed += 1

            print("Status: INVALID")

            for error in errors:
                print(" -", error)

        else:
            valid += 1

            print("Status: VALID")
            print("Title:", job["title"])
            print("Company:", job["company"])
            print("Location:", job["location"])
            print("Work type:", job["work_type"])
            print("Posted:", job["posted_at"])
            print(
                "Description length:",
                len(job["description"]),
            )

    except Exception as error:
        failed += 1

        print("Status: ERROR")
        print(
            "Type:",
            type(error).__name__,
        )
        print(
            "Error:",
            error,
        )


print()
print("=" * 60)
print("LINKEDIN SAMPLE SUMMARY")
print("=" * 60)
print("Jobs tested:", min(5, len(jobs)))
print("Valid:", valid)
print("Invalid/errors:", failed)