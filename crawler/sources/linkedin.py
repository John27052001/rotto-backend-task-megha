import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from dotenv import load_dotenv

from request_stats import log_request


# ---------------------------------------------------------
# ENVIRONMENT
# ---------------------------------------------------------

load_dotenv()


# ---------------------------------------------------------
# LINKEDIN SETTINGS
# ---------------------------------------------------------

BASE_URL = "https://www.linkedin.com"

SEARCH_URL = (
    "https://www.linkedin.com/jobs/search/"
    "?keywords=Software%20Engineer"
    "&location=United%20Kingdom"
)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


# ---------------------------------------------------------
# FETCH PAGE THROUGH ROTTO PROXY
# ---------------------------------------------------------

def fetch_page(url):
    """
    Fetch one LinkedIn page through the supplied
    residential proxy.

    Every request is recorded in request_stats.
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

            log_request(
                status=response.status,
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
# DISCOVER LINKEDIN JOBS
# ---------------------------------------------------------

def discover_jobs():
    """
    Discover LinkedIn jobs from the public UK search page.

    LinkedIn URLs commonly look like:

    /jobs/view/software-engineer-at-company-1234567890

    The final numeric component is the LinkedIn job ID.
    """

    print(
        "Discovering LinkedIn jobs..."
    )

    html = fetch_page(
        SEARCH_URL
    )

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

        href = href.replace(
            "&amp;",
            "&",
        )

        parsed = urllib.parse.urlparse(
            href
        )

        path = parsed.path.rstrip("/")

        # Example:
        #
        # /jobs/view/software-engineer-backend-at-doordash-4296369615
        match = re.search(
            r"/jobs/view/([^/?#]+)-(\d+)$",
            path,
        )

        if match is None:
            continue

        source_job_id = (
            match.group(2)
        )

        # Strip LinkedIn tracking query parameters.
        clean_url = urllib.parse.urljoin(
            BASE_URL,
            path,
        )

        jobs[source_job_id] = {
            "source_job_id": source_job_id,
            "url": clean_url,
        }

    print(
        "LinkedIn jobs discovered:",
        len(jobs),
    )

    # Deterministic processing order.
    return sorted(
        jobs.values(),
        key=lambda job: int(
            job["source_job_id"]
        ),
    )


# ---------------------------------------------------------
# TEXT HELPER
# ---------------------------------------------------------

def get_text(
    soup,
    selector,
):
    element = soup.select_one(
        selector
    )

    if element is None:
        return None

    value = element.get_text(
        " ",
        strip=True,
    )

    if not value:
        return None

    return value


# ---------------------------------------------------------
# COMPANY LOGO
# ---------------------------------------------------------

def get_company_logo(soup):
    """
    Return LinkedIn's company logo URL when the public
    page provides one.

    Store the URL only.
    """

    selectors = [
        ".top-card-layout__entity-image",
        ".artdeco-entity-image",
        ".topcard__logo-image",
    ]

    for selector in selectors:

        image = soup.select_one(
            selector
        )

        if image is None:
            continue

        src = (
            image.get("src")
            or image.get("data-delayed-url")
        )

        if src:
            return src

    return None


# ---------------------------------------------------------
# WORK TYPE
# ---------------------------------------------------------

def normalize_work_type(value):
    if not value:
        return None

    text = str(
        value
    ).lower().strip()

    if (
        "full-time" in text
        or "full time" in text
    ):
        return "full time"

    if (
        "part-time" in text
        or "part time" in text
    ):
        return "part time"

    if "contract" in text:
        return "contract"

    if (
        "temporary" in text
        or text == "temp"
    ):
        return "temporary"

    return None


def find_work_type(soup):
    """
    Find LinkedIn employment type using the public
    job criteria section.
    """

    criteria_items = soup.select(
        ".description__job-criteria-item"
    )

    for item in criteria_items:

        text = item.get_text(
            " ",
            strip=True,
        )

        normalized = (
            normalize_work_type(
                text
            )
        )

        if normalized:
            return normalized

    # Fallback used by some LinkedIn page variants.
    for element in soup.select(
        ".job-criteria__text"
    ):

        text = element.get_text(
            " ",
            strip=True,
        )

        normalized = (
            normalize_work_type(
                text
            )
        )

        if normalized:
            return normalized

    return None


# ---------------------------------------------------------
# POSTED DATE
# ---------------------------------------------------------

def parse_datetime_value(value):
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(
            str(value).replace(
                "Z",
                "+00:00",
            )
        )

    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed


def parse_posted_at(soup):
    """
    Prefer LinkedIn's machine-readable date.

    We do not invent an exact timestamp when only
    relative display text is available.
    """

    # First look specifically around the posted-time
    # element.
    posted_element = soup.select_one(
        ".posted-time-ago__text"
    )

    if posted_element is not None:

        # Sometimes datetime exists directly on it.
        value = posted_element.get(
            "datetime"
        )

        parsed = parse_datetime_value(
            value
        )

        if parsed is not None:
            return parsed

        # Sometimes LinkedIn nests a <time> element.
        nested_time = (
            posted_element.select_one(
                "time"
            )
        )

        if nested_time is not None:

            parsed = parse_datetime_value(
                nested_time.get(
                    "datetime"
                )
            )

            if parsed is not None:
                return parsed

    # Fallback: inspect time elements in the document.
    for time_element in soup.find_all(
        "time"
    ):

        parsed = parse_datetime_value(
            time_element.get(
                "datetime"
            )
        )

        if parsed is not None:
            return parsed

    return None


# ---------------------------------------------------------
# DESCRIPTION
# ---------------------------------------------------------

def get_description(soup):
    """
    Extract the full public job description as plain text.
    """

    element = soup.select_one(
        ".description__text"
    )

    if element is None:
        element = soup.select_one(
            ".show-more-less-html__markup"
        )

    if element is None:
        return ""

    return element.get_text(
        "\n",
        strip=True,
    )


# ---------------------------------------------------------
# LOCATION
# ---------------------------------------------------------

def get_location(
    soup,
    company,
):
    """
    LinkedIn's top card uses .topcard__flavor for several
    values, including company and location.

    Select the first useful flavor that is not simply the
    company name.
    """

    flavors = soup.select(
        ".topcard__flavor"
    )

    for flavor in flavors:

        text = flavor.get_text(
            " ",
            strip=True,
        )

        if not text:
            continue

        if (
            company
            and text.lower()
            == company.lower()
        ):
            continue

        return text

    return None


# ---------------------------------------------------------
# PARSE SOURCE JOB ID
# ---------------------------------------------------------

def get_source_job_id(url):
    path = urllib.parse.urlparse(
        url
    ).path.rstrip("/")

    match = re.search(
        r"-(\d+)$",
        path,
    )

    if match is None:
        return None

    return match.group(1)


# ---------------------------------------------------------
# PARSE ONE LINKEDIN DETAIL PAGE
# ---------------------------------------------------------

def parse_job_page(
    html,
    url,
    expected_source_job_id=None,
):
    """
    Parse one LinkedIn public job page into the common
    normalized schema used by the crawler.
    """

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    # -----------------------------------------------------
    # SOURCE JOB ID
    # -----------------------------------------------------

    source_job_id = get_source_job_id(
        url
    )

    if source_job_id is None:
        raise ValueError(
            "Could not determine LinkedIn source_job_id"
        )

    if expected_source_job_id is not None:

        if (
            str(expected_source_job_id)
            != str(source_job_id)
        ):
            raise ValueError(
                "LinkedIn detail page ID does not match "
                "discovered job ID"
            )

    # -----------------------------------------------------
    # TITLE
    # -----------------------------------------------------

    title = get_text(
        soup,
        ".top-card-layout__title",
    )

    # -----------------------------------------------------
    # COMPANY
    # -----------------------------------------------------

    company = get_text(
        soup,
        ".topcard__org-name-link",
    )

    if company is None:
        company = get_text(
            soup,
            ".topcard__flavor-row "
            ".topcard__flavor",
        )

    # -----------------------------------------------------
    # LOCATION
    # -----------------------------------------------------

    location = get_location(
        soup,
        company,
    )

    # -----------------------------------------------------
    # DESCRIPTION
    # -----------------------------------------------------

    description = get_description(
        soup
    )

    # -----------------------------------------------------
    # OPTIONAL SOURCE FIELDS
    # -----------------------------------------------------

    work_type = find_work_type(
        soup
    )

    posted_at = parse_posted_at(
        soup
    )

    company_logo_url = (
        get_company_logo(
            soup
        )
    )

    # -----------------------------------------------------
    # REQUIRED FIELD SAFETY
    # -----------------------------------------------------

    if not title:
        raise ValueError(
            "LinkedIn job is missing title"
        )

    if not location:
        raise ValueError(
            "LinkedIn job is missing location"
        )

    if not description:
        raise ValueError(
            "LinkedIn job is missing description"
        )

    # -----------------------------------------------------
    # NORMALIZED RESULT
    # -----------------------------------------------------

    return {
        "source": "linkedin",
        "source_job_id": str(
            source_job_id
        ),
        "url": url,
        "title": title,
        "company": company,
        "company_logo_url": (
            company_logo_url
        ),
        "location": location,
        "work_type": work_type,

        # Use NULL when LinkedIn does not expose salary
        # information reliably.
        "salary_min": None,
        "salary_max": None,
        "salary_period": None,

        "posted_at": posted_at,
        "description": description,
    }


# ---------------------------------------------------------
# FETCH + PARSE ONE JOB
# ---------------------------------------------------------

def fetch_job(job_info):
    """
    Fetch and parse one discovered LinkedIn listing.
    """

    html = fetch_page(
        job_info["url"]
    )

    return parse_job_page(
        html,
        job_info["url"],
        expected_source_job_id=(
            job_info["source_job_id"]
        ),
    )


# ---------------------------------------------------------
# MANUAL TEST
# ---------------------------------------------------------

if __name__ == "__main__":

    print(
        "Testing LinkedIn discovery..."
    )

    try:
        jobs = discover_jobs()

    except Exception as error:

        print(
            "DISCOVERY FAILED"
        )

        print(
            "Type:",
            type(error).__name__,
        )

        print(
            "Error:",
            error,
        )

        raise SystemExit(1)

    if not jobs:

        print(
            "No LinkedIn jobs discovered."
        )

    else:

        print()
        print(
            "Testing first discovered job..."
        )

        first_job = jobs[0]

        print(
            "Discovered:",
            first_job,
        )

        try:
            job = fetch_job(
                first_job
            )

            print()
            print(
                "PARSED LINKEDIN JOB"
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