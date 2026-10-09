from collections import defaultdict
from threading import Lock


_lock = Lock()

_stats = {
    "requests_total": 0,
    "requests_blocked": 0,
    "requests_by_status": defaultdict(int),
}


def reset_request_stats():
    """
    Reset counters at the beginning of a crawl run.
    """
    with _lock:
        _stats["requests_total"] = 0
        _stats["requests_blocked"] = 0
        _stats["requests_by_status"].clear()


def log_request(status=None, blocked=False):
    """
    Record one HTTP request.

    status examples:
        200
        403
        404
        "timeout"
        "error"
    """
    with _lock:
        _stats["requests_total"] += 1

        status_key = (
            str(status)
            if status is not None
            else "unknown"
        )

        _stats["requests_by_status"][status_key] += 1

        if blocked:
            _stats["requests_blocked"] += 1


def get_request_stats():
    """
    Return a normal JSON-serializable dictionary.
    """
    with _lock:
        return {
            "requests_total": _stats["requests_total"],
            "requests_blocked": _stats["requests_blocked"],
            "requests_by_status": dict(
                _stats["requests_by_status"]
            ),
        }