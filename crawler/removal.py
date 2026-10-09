def is_confirmed_removed_status(status_code):
    """
    Return True only when an HTTP status is strong
    evidence that the public listing no longer exists.

    Search-result absence, blocking, rate limiting,
    timeouts and server errors are NOT removal evidence.
    """

    return status_code in (404, 410)


def is_blocked_status(status_code):
    """
    Responses caused by bot protection/rate limiting.
    These must never mark a job removed.
    """

    return status_code in (403, 429)