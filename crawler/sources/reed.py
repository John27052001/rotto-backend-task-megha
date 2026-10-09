import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from bs4 import BeautifulSoup
from dotenv import load_dotenv

from request_stats import log_request


# ---------------------------------------------------------
# ENVIRONMENT
# ---------------------------------------------------------

load_dotenv()


# ---------------------------------------------------------
# REED SETTINGS
# ---------------------------------------------------------

BASE_URL = "https://www.reed.co.uk"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


# ---------------------------------------------------------
# DISCOVERY SLICES
# ---------------------------------------------------------

SEARCH_SLICES = [
    "https://www.reed.co.uk/jobs/software-engineer-jobs",
    "https://www.reed.co.uk/jobs/data-analyst-jobs",
    "https://www.reed.co.uk/jobs/project-manager-jobs",
    "https://www.reed.co.uk/jobs/accountant-jobs",
    "https://www.reed.co.uk/jobs/sales-jobs",
    "https://www.reed.co.uk/jobs/customer-service-jobs",
    "https://www.reed.co.uk/jobs/healthcare-jobs",
    "https://www.reed.co.uk/jobs/warehouse-jobs",
    "https://www.reed.co.uk/jobs/construction-jobs",
    "https://www.reed.co.uk/jobs/marketing-jobs",
    "https://www.reed.co.uk/jobs/hr-jobs",
    "https://www.reed.co.uk/jobs/engineering-jobs",
]


# ---------------------------------------------------------
# FETCH PAGE THROUGH ROTTO PROXY
# ---------------------------------------------------------

def fetch_page(url):
    """
    Fetch one Reed page through the supplied residential
    proxy.

    Every HTTP request is recorded in request_stats.
    """

    proxy_host = os.getenv("PROXY_HOST")
    proxy_port = os.getenv("PROXY_PORT")
    proxy_username = os.getenv("PROXY_USERNAME")
    proxy_password = os.getenv("PROXY_PASSWORD")

    if not all([
        proxy_host,
        proxy_port,
        proxy_username,
        proxy_password,
    ]):
        raise RuntimeError(
            "Proxy environment variables are not configured"
        )

    proxy_url = (
        f"http://{proxy_username}:"
        f"{proxy_password}@"
        f"{proxy_host}:"
        f"{proxy_port}"
    )

    proxy_handler = urllib.request.ProxyHandler(
        {
            "http": proxy_url,
            "https": proxy_url,
        }
    )

    opener = urllib.request.build_opener(
        proxy_handler
    )

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,*/*;q=0.8"
            ),
            "Accept-Language": "en-GB,en;q=0.9",
        },
    )

    try:
        with opener.open(
            request,
            timeout=20,
        ) as response:

            status = response.status

            log_request(
                status=status,
                blocked=False,
            )

            return response.read()

    except urllib.error.HTTPError as error:

        blocked = error.code in (
            403,
            429,
        )

        log_request(
            status=error.code,
            blocked=blocked,
        )

        raise

    except Exception:

        log_request(
            status="error",
            blocked=False,
        )

        raise


# ---------------------------------------------------------
# EXTRACT LISTINGS FROM ONE SEARCH PAGE
# ---------------------------------------------------------

def extract_discovered_jobs(html):
    """
    Extract Reed listing IDs and public URLs from one
    search-results page.
    """

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    jobs = {}

    for link in soup.find_all(
        "a",
        href=True,
    ):
        href = link["href"]

        clean_path = urllib.parse.urlparse(
            href
        ).path

        # Example:
        #
        # /jobs/software-engineer/12345678
        #
        # The final number is Reed's source job ID.
        match = re.fullmatch(
            r"/jobs/[^/]+/(\d+)",
            clean_path,
        )

        if match is None:
            continue

        source_job_id = match.group(1)

        url = urllib.parse.urljoin(
            BASE_URL,
            clean_path,
        )

        jobs[source_job_id] = {
            "source_job_id": source_job_id,
            "url": url,
        }

    return jobs


# ---------------------------------------------------------
# BUILD PAGINATED SEARCH URL
# ---------------------------------------------------------

def build_search_page_url(
    search_url,
    page_number,
):
    """
    Build a Reed search pagination URL.
    """

    if page_number == 1:
        return search_url

    separator = (
        "&"
        if "?" in search_url
        else "?"
    )

    return (
        f"{search_url}"
        f"{separator}"
        f"pager={page_number}"
    )


# ---------------------------------------------------------
# DISCOVER JOBS
# ---------------------------------------------------------

def discover_jobs(
    max_pages_per_slice=1,
):
    """
    Discover Reed jobs across multiple broad UK job
    families.

    Listings are globally deduplicated by Reed's
    source_job_id.
    """

    all_jobs = {}

    total_slices = len(
        SEARCH_SLICES
    )

    for slice_number, search_url in enumerate(
        SEARCH_SLICES,
        start=1,
    ):

        print()
        print(
            f"Reed search slice "
            f"{slice_number}/{total_slices}"
        )

        print(search_url)

        for page_number in range(
            1,
            max_pages_per_slice + 1,
        ):

            page_url = build_search_page_url(
                search_url,
                page_number,
            )

            print(
                f"  Discovering page "
                f"{page_number}..."
            )

            try:
                html = fetch_page(
                    page_url
                )

            except Exception as error:
                print(
                    "  Failed:",
                    error,
                )

                # Keep everything successfully discovered
                # from previous slices/pages.
                break

            page_jobs = extract_discovered_jobs(
                html
            )

            before = len(
                all_jobs
            )

            all_jobs.update(
                page_jobs
            )

            after = len(
                all_jobs
            )

            new_jobs = (
                after - before
            )

            print(
                "    Listings on page:",
                len(page_jobs),
            )

            print(
                "    New unique jobs:",
                new_jobs,
            )

            print(
                "    Total unique jobs:",
                after,
            )

            # Avoid wasting proxy traffic when pagination
            # stops producing additional listings.
            if new_jobs == 0:

                print(
                    "    No new unique jobs. "
                    "Stopping this slice."
                )

                break

    print()
    print(
        "Reed discovery complete."
    )

    print(
        "Total unique Reed jobs:",
        len(all_jobs),
    )

    # Deterministic processing order.
    return sorted(
        all_jobs.values(),
        key=lambda job: int(
            job["source_job_id"]
        ),
    )


# ---------------------------------------------------------
# CLEAN DESCRIPTION
# ---------------------------------------------------------

def clean_description(description):
    """
    Convert Reed's HTML description into plain text.
    """

    if not description:
        return ""

    soup = BeautifulSoup(
        description,
        "html.parser",
    )

    return soup.get_text(
        separator="\n",
        strip=True,
    )


# ---------------------------------------------------------
# NORMALIZE WORK TYPE
# ---------------------------------------------------------

def normalize_work_type(value):
    if not value:
        return None

    if isinstance(
        value,
        list,
    ):
        if not value:
            return None

        value = value[0]

    value = str(value).upper()

    if value == "FULL_TIME":
        return "full time"

    if value == "PART_TIME":
        return "part time"

    if value in (
        "CONTRACT",
        "CONTRACTOR",
    ):
        return "contract"

    if value == "TEMPORARY":
        return "temporary"

    return None


# ---------------------------------------------------------
# NORMALIZE SALARY PERIOD
# ---------------------------------------------------------

def normalize_salary_period(value):
    if not value:
        return None

    value = str(value).upper()

    if value == "YEAR":
        return "year"

    if value == "DAY":
        return "day"

    if value == "HOUR":
        return "hour"

    return None


# ---------------------------------------------------------
# PARSE DATETIME
# ---------------------------------------------------------

def parse_datetime(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(
            str(value).replace(
                "Z",
                "+00:00",
            )
        )

    except ValueError:
        return None


# ---------------------------------------------------------
# BUILD LOCATION
# ---------------------------------------------------------

def build_location(job_posting):
    job_location = job_posting.get(
        "jobLocation"
    )

    if not job_location:
        return None

    if isinstance(
        job_location,
        list,
    ):
        if not job_location:
            return None

        job_location = job_location[0]

    if not isinstance(
        job_location,
        dict,
    ):
        return None

    address = job_location.get(
        "address",
        {},
    )

    if not isinstance(
        address,
        dict,
    ):
        return None

    parts = [
        address.get(
            "addressLocality"
        ),
        address.get(
            "addressRegion"
        ),
    ]

    parts = [
        str(part).strip()
        for part in parts
        if part
    ]

    if not parts:
        return None

    return ", ".join(parts)


# ---------------------------------------------------------
# FIND JOBPOSTING JSON-LD
# ---------------------------------------------------------

def find_job_posting(soup):
    """
    Find Reed's schema.org JobPosting data.
    """

    scripts = soup.find_all(
        "script",
        type="application/ld+json",
    )

    for script in scripts:

        try:
            raw = script.string

            if not raw:
                continue

            data = json.loads(raw)

        except (
            json.JSONDecodeError,
            TypeError,
        ):
            continue

        # -------------------------------------------------
        # DIRECT DICTIONARY
        # -------------------------------------------------

        if isinstance(
            data,
            dict,
        ):

            if (
                data.get("@type")
                == "JobPosting"
            ):
                return data

            graph = data.get(
                "@graph"
            )

            if isinstance(
                graph,
                list,
            ):

                for item in graph:

                    if (
                        isinstance(
                            item,
                            dict,
                        )
                        and item.get("@type")
                        == "JobPosting"
                    ):
                        return item

        # -------------------------------------------------
        # JSON-LD LIST
        # -------------------------------------------------

        elif isinstance(
            data,
            list,
        ):

            for item in data:

                if (
                    isinstance(
                        item,
                        dict,
                    )
                    and item.get("@type")
                    == "JobPosting"
                ):
                    return item

    return None


# ---------------------------------------------------------
# PARSE ONE JOB DETAIL PAGE
# ---------------------------------------------------------

def parse_job_page(
    html,
    url,
):
    """
    Parse one Reed public job detail page into our
    normalized job structure.
    """

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    job_posting = find_job_posting(
        soup
    )

    if job_posting is None:
        raise ValueError(
            "No JobPosting JSON-LD found"
        )

    # -----------------------------------------------------
    # SOURCE JOB ID
    # -----------------------------------------------------

    identifier = job_posting.get(
        "identifier",
        {},
    )

    if not isinstance(
        identifier,
        dict,
    ):
        identifier = {}

    source_job_id = identifier.get(
        "value"
    )

    # Fallback to the numeric ID from the public URL.
    if source_job_id is None:

        path = urllib.parse.urlparse(
            url
        ).path

        match = re.search(
            r"/(\d+)/?$",
            path,
        )

        if match:
            source_job_id = (
                match.group(1)
            )

    if source_job_id is None:
        raise ValueError(
            "Reed job is missing source_job_id"
        )

    source_job_id = str(
        source_job_id
    )

    # -----------------------------------------------------
    # COMPANY
    # -----------------------------------------------------

    organization = job_posting.get(
        "hiringOrganization"
    ) or {}

    if not isinstance(
        organization,
        dict,
    ):
        organization = {}

    company = organization.get(
        "name"
    )

    # -----------------------------------------------------
    # COMPANY LOGO
    # -----------------------------------------------------

    company_logo_url = None

    logo = organization.get(
        "logo"
    )

    if isinstance(
        logo,
        str,
    ):
        company_logo_url = logo

    elif isinstance(
        logo,
        dict,
    ):
        company_logo_url = (
            logo.get("url")
            or logo.get("contentUrl")
        )

    # -----------------------------------------------------
    # SALARY
    # -----------------------------------------------------

    salary = job_posting.get(
        "baseSalary"
    ) or {}

    if not isinstance(
        salary,
        dict,
    ):
        salary = {}

    salary_value = salary.get(
        "value"
    ) or {}

    if not isinstance(
        salary_value,
        dict,
    ):
        salary_value = {}

    salary_min = salary_value.get(
        "minValue"
    )

    salary_max = salary_value.get(
        "maxValue"
    )

    # Some listings may provide a single salary value.
    single_salary = salary_value.get(
        "value"
    )

    if (
        salary_min is None
        and salary_max is None
        and single_salary is not None
    ):
        salary_min = single_salary
        salary_max = single_salary

    salary_period = normalize_salary_period(
        salary_value.get(
            "unitText"
        )
    )

    if (
        salary_min is None
        and salary_max is None
    ):
        salary_period = None

    # -----------------------------------------------------
    # DESCRIPTION
    # -----------------------------------------------------

    description = clean_description(
        job_posting.get(
            "description"
        )
    )

    # -----------------------------------------------------
    # POSTED DATE
    # -----------------------------------------------------

    posted_at = parse_datetime(
        job_posting.get(
            "datePosted"
        )
    )

    # -----------------------------------------------------
    # NORMALIZED RESULT
    # -----------------------------------------------------

    return {
        "source": "reed",
        "source_job_id": source_job_id,
        "url": url,
        "title": job_posting.get(
            "title"
        ),
        "company": company,
        "company_logo_url": company_logo_url,
        "location": build_location(
            job_posting
        ),
        "work_type": normalize_work_type(
            job_posting.get(
                "employmentType"
            )
        ),
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_period": salary_period,
        "posted_at": posted_at,
        "description": description,
    }


# ---------------------------------------------------------
# FETCH + PARSE ONE JOB
# ---------------------------------------------------------

def fetch_job(job_info):
    """
    Fetch and parse one discovered Reed listing.
    """

    html = fetch_page(
        job_info["url"]
    )

    job = parse_job_page(
        html,
        job_info["url"],
    )

    # Protect against accidentally parsing a different
    # listing than the one discovery returned.
    expected_id = str(
        job_info["source_job_id"]
    )

    parsed_id = str(
        job["source_job_id"]
    )

    if expected_id != parsed_id:
        raise ValueError(
            "Reed detail page ID does not match "
            "discovered job ID"
        )

    return job


# ---------------------------------------------------------
# MANUAL TEST
# ---------------------------------------------------------

if __name__ == "__main__":
    print(
        "Testing Reed discovery..."
    )

    jobs = discover_jobs(
        max_pages_per_slice=1
    )

    print()
    print(
        "Jobs discovered:",
        len(jobs),
    )

    if not jobs:
        print(
            "No Reed jobs discovered."
        )

    else:
        first_job = jobs[0]

        print()
        print(
            "Testing first discovered job:"
        )

        print(
            first_job
        )

        try:
            job = fetch_job(
                first_job
            )

            print()
            print(
                "PARSED REED JOB"
            )

            print(
                "-" * 60
            )

            for key, value in job.items():

                if (
                    key == "description"
                    and value
                ):
                    print(
                        f"{key}: "
                        f"{value[:500]}..."
                    )

                else:
                    print(
                        f"{key}: {value}"
                    )

        except Exception as error:

            print()
            print(
                "FAILED TO PARSE JOB"
            )

            print(
                "Type:",
                type(error).__name__,
            )

            print(
                "Error:",
                error,
            )