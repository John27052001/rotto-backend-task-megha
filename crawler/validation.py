def validate_job(job, discovered_job=None):
    errors = []

    if not job.get("source"):
        errors.append("missing source")

    if not job.get("source_job_id"):
        errors.append("missing source_job_id")

    if not job.get("url"):
        errors.append("missing url")

    if not job.get("title"):
        errors.append("missing title")

    if not job.get("location"):
        errors.append("missing location")

    if not job.get("description"):
        errors.append("missing description")

    if discovered_job is not None:

        discovered_id = str(
            discovered_job["source_job_id"]
        )

        parsed_id = str(
            job["source_job_id"]
        )

        if discovered_id != parsed_id:
            errors.append(
                "source_job_id does not match discovered job"
            )

    return errors