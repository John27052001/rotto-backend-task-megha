import os
import sys
import time
import urllib.error
import urllib.request

from dotenv import load_dotenv


sys.path.insert(
    0,
    os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    ),
)

from request_stats import log_request


# ---------------------------------------------------------
# ENVIRONMENT
# ---------------------------------------------------------

load_dotenv()


# ---------------------------------------------------------
# INDEED SETTINGS
# ---------------------------------------------------------

BASE_URL = "https://uk.indeed.com"

SEARCH_URL = (
    "https://uk.indeed.com/jobs"
    "?q=software+engineer"
    "&l=United+Kingdom"
)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


# ---------------------------------------------------------
# RETRY SETTINGS
# ---------------------------------------------------------

# Keep retries deliberately small.
MAX_ATTEMPTS = 3

# Simple bounded backoff between attempts.
RETRY_DELAY_SECONDS = 2


# ---------------------------------------------------------
# FETCH ONE PAGE THROUGH ROTTO PROXY
# ---------------------------------------------------------

def fetch_page(url):
    """
    Fetch one public Indeed page through the supplied
    residential proxy.

    Every HTTP request is recorded in request_stats.

    403 and 429 responses are counted as blocked requests.
    """

    proxy_host = os.getenv(
        "PROXY_HOST"
    )

    proxy_port = os.getenv(
        "PROXY_PORT"
    )

    proxy_username = os.getenv(
        "PROXY_USERNAME"
    )

    proxy_password = os.getenv(
        "PROXY_PASSWORD"
    )

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

    proxy_handler = (
        urllib.request.ProxyHandler(
            {
                "http": proxy_url,
                "https": proxy_url,
            }
        )
    )

    opener = (
        urllib.request.build_opener(
            proxy_handler
        )
    )

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "text/html,"
                "application/xhtml+xml,"
                "application/xml;q=0.9,"
                "*/*;q=0.8"
            ),
            "Accept-Language": (
                "en-GB,en;q=0.9"
            ),
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

        blocked = (
            error.code in (
                403,
                429,
            )
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
# CHALLENGE DETECTION
# ---------------------------------------------------------

def looks_like_challenge(html):
    """
    Detect obvious security/challenge responses.

    We only detect them. We do not solve or interact
    with CAPTCHA/security challenges.
    """

    if not html:
        return False

    if isinstance(
        html,
        bytes,
    ):
        text = html.decode(
            "utf-8",
            errors="ignore",
        )

    else:
        text = str(
            html
        )

    text = text.lower()

    challenge_markers = [
        "verify you are human",
        "security check",
        "additional verification",
        "captcha",
        "cf-mitigated",
    ]

    return any(
        marker in text
        for marker in challenge_markers
    )


# ---------------------------------------------------------
# FETCH WITH BOUNDED RETRIES
# ---------------------------------------------------------

def fetch_page_with_retries(url):
    """
    Try a small bounded number of requests.

    The supplied proxy uses a rotating residential pool,
    so a fresh connection may receive a different exit IP.

    We retry only a few times and never attempt to solve
    security challenges.
    """

    last_error = None

    for attempt in range(
        1,
        MAX_ATTEMPTS + 1,
    ):

        print(
            f"Indeed request attempt "
            f"{attempt}/{MAX_ATTEMPTS}..."
        )

        try:

            html = fetch_page(
                url
            )

            # Some bot protection can return HTTP 200 while
            # serving a challenge page instead of jobs.
            if looks_like_challenge(
                html
            ):

                log_request(
                    status="challenge",
                    blocked=True,
                )

                last_error = RuntimeError(
                    "Indeed returned a security challenge"
                )

            else:

                # Normal usable HTML.
                return html

        except urllib.error.HTTPError as error:

            last_error = error

            # Retry only blocking/rate-limit responses.
            #
            # 404, 410, 5xx etc. should not be repeatedly
            # retried here.
            if error.code not in (
                403,
                429,
            ):
                raise

        except Exception as error:

            last_error = error

        # ---------------------------------------------
        # BACKOFF
        # ---------------------------------------------

        if attempt < MAX_ATTEMPTS:

            print(
                f"Indeed attempt {attempt} failed. "
                f"Waiting {RETRY_DELAY_SECONDS}s..."
            )

            time.sleep(
                RETRY_DELAY_SECONDS
            )

    raise RuntimeError(
        "Indeed remained unavailable after "
        f"{MAX_ATTEMPTS} attempts: "
        f"{last_error}"
    )


# ---------------------------------------------------------
# DISCOVER INDEED JOBS
# ---------------------------------------------------------

def discover_jobs():
    """
    Attempt public Indeed UK discovery.

    Important:
    A blocked or incomplete response is NOT interpreted
    as an empty authoritative listing.

    We raise an error instead so the master crawler can
    preserve existing Indeed data safely.
    """

    print(
        "Discovering Indeed jobs..."
    )

    html = fetch_page_with_retries(
        SEARCH_URL
    )

    # Defensive check.
    if looks_like_challenge(
        html
    ):

        raise RuntimeError(
            "Indeed returned a security challenge page"
        )

    # -----------------------------------------------------
    # PARSER STATUS
    # -----------------------------------------------------
    #
    # We have not yet obtained a usable Indeed search page
    # through the supplied proxy during development.
    #
    # Therefore we deliberately do NOT guess the DOM
    # structure or fabricate source IDs.
    #
    # If a normal page is obtained through one of the
    # rotating proxy sessions, this is where discovery
    # parsing will be implemented.
    # -----------------------------------------------------

    raise RuntimeError(
        "Indeed search page was reachable without an "
        "obvious challenge, but discovery parsing is "
        "not implemented for this response format"
    )


# ---------------------------------------------------------
# FETCH ONE INDEED JOB
# ---------------------------------------------------------

def fetch_job(job_info):
    """
    Fetch one previously discovered Indeed job.

    Detail parsing will be implemented after obtaining a
    usable public Indeed response format.
    """

    if not job_info:

        raise ValueError(
            "Missing Indeed job information"
        )

    url = job_info.get(
        "url"
    )

    if not url:

        raise ValueError(
            "Indeed job is missing URL"
        )

    html = fetch_page_with_retries(
        url
    )

    if looks_like_challenge(
        html
    ):

        raise RuntimeError(
            "Indeed returned a security challenge page"
        )

    raise RuntimeError(
        "Indeed detail parser is not implemented "
        "for this response format"
    )


# ---------------------------------------------------------
# MANUAL TEST
# ---------------------------------------------------------

if __name__ == "__main__":

    print(
        "Testing Indeed through proxy..."
    )

    print()

    try:

        jobs = discover_jobs()

        print()
        print(
            "Indeed jobs discovered:",
            len(jobs),
        )

    except urllib.error.HTTPError as error:

        print()
        print(
            "FAILED"
        )

        print(
            "Type:",
            type(error).__name__,
        )

        print(
            "HTTP status:",
            error.code,
        )

    except Exception as error:

        print()
        print(
            "FAILED"
        )

        print(
            "Type:",
            type(error).__name__,
        )

        print(
            "Error:",
            error,
        )