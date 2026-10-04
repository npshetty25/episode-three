"""A small, polite client for the AniList GraphQL API.

GraphQL in one paragraph: there is ONE web address for everything. Each request
sends a "query" naming exactly the fields we want, plus "variables" that fill
in its blanks (like which anime). The answer comes back as JSON shaped like the
query.

"Polite" means we follow AniList's rules (https://docs.anilist.co/guide/rate-limiting):
- at most ~27 requests a minute (the limit is temporarily 30, normally 90)
- if AniList answers 429 "Too Many Requests", wait as long as it says, then retry
- if the network or AniList's server fails, retry a few times with growing waits
- never wait forever for an answer (30-second timeout)
"""
import logging
import time

import requests

API_URL = "https://graphql.anilist.co"
MIN_SECONDS_BETWEEN_REQUESTS = 2.2   # 60 / 2.2 = about 27 requests per minute
REQUEST_TIMEOUT_SECONDS = 30
RETRY_WAITS_SECONDS = [5, 15, 45]    # waits before retry 1, 2 and 3 after a network/server error
DEFAULT_RETRY_AFTER_SECONDS = 60     # used if a 429 answer doesn't say how long to wait
MAX_RATE_LIMIT_RETRIES = 5           # stop instead of looping forever if we keep getting 429

logger = logging.getLogger(__name__)

# A Session reuses the same network connection for every request, which saves
# time when each round trip is slow.
_session = requests.Session()
_last_request_started = None

# Running totals, so scripts can report what happened.
stats = {"requests": 0, "http_429": 0, "retries": 0, "limit_values": [], "lowest_remaining": None}


class AniListError(Exception):
    """AniList answered with an error, or kept failing after all retries."""


def post_query(query, variables=None):
    """Send one GraphQL query to AniList and return the "data" part of the answer.

    Only pass variables the query really uses. AniList does NOT ignore filters
    set to None: on mediaTrends, mediaId_in=None gives HTTP 500 and
    episode_lesser=None or date_greater=None give HTTP 400 (found in TASK 003).
    """
    payload = {"query": query, "variables": variables or {}}
    server_failures = 0
    rate_limit_hits = 0

    while True:
        _wait_for_turn()
        try:
            response = _session.post(API_URL, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.RequestException as error:
            # No usable answer at all: timeout, dropped connection, DNS problem...
            server_failures += 1
            _wait_before_retry(server_failures, f"network error ({type(error).__name__})", error)
            continue

        _record_rate_limit_headers(response)

        if response.status_code == 429:
            rate_limit_hits += 1
            stats["http_429"] += 1
            if rate_limit_hits > MAX_RATE_LIMIT_RETRIES:
                raise AniListError(f"Still rate-limited after {MAX_RATE_LIMIT_RETRIES} waits; stopping.")
            wait = _retry_after_seconds(response)
            logger.warning("HTTP 429 (too many requests): waiting %s s as AniList asked", wait)
            time.sleep(wait)
            continue

        if response.status_code >= 500:
            # AniList's own server had a problem; usually temporary.
            server_failures += 1
            reason = f"server error HTTP {response.status_code} ({_error_message(response)})"
            _wait_before_retry(server_failures, reason)
            continue

        try:
            body = response.json()
        except ValueError:
            raise AniListError(f"HTTP {response.status_code}: the answer was not JSON") from None

        # GraphQL reports problems (bad field name, unknown ID...) in an "errors" list.
        if body.get("errors"):
            messages = "; ".join(error.get("message", "?") for error in body["errors"])
            raise AniListError(f"AniList returned an error (HTTP {response.status_code}): {messages}")
        if response.status_code != 200:
            raise AniListError(f"Unexpected HTTP {response.status_code} from AniList")
        return body["data"]


def _wait_for_turn():
    """Sleep until at least MIN_SECONDS_BETWEEN_REQUESTS have passed since the last request."""
    global _last_request_started
    if _last_request_started is not None:
        elapsed = time.monotonic() - _last_request_started
        if elapsed < MIN_SECONDS_BETWEEN_REQUESTS:
            time.sleep(MIN_SECONDS_BETWEEN_REQUESTS - elapsed)
    _last_request_started = time.monotonic()
    stats["requests"] += 1


def _wait_before_retry(failure_number, reason, error=None):
    """Wait 5, 15, then 45 seconds before retrying; give up after the third retry."""
    if failure_number > len(RETRY_WAITS_SECONDS):
        raise AniListError(f"Giving up after {len(RETRY_WAITS_SECONDS)} retries: {reason}") from error
    wait = RETRY_WAITS_SECONDS[failure_number - 1]
    stats["retries"] += 1
    logger.warning("%s: retry %s in %s s", reason, failure_number, wait)
    time.sleep(wait)


def _error_message(response):
    """The first error message in an AniList answer, or the start of the raw text."""
    try:
        return response.json()["errors"][0]["message"]
    except (ValueError, KeyError, IndexError, TypeError):
        return response.text[:150]


def _retry_after_seconds(response):
    """How long a 429 answer asks us to wait (the Retry-After header), in seconds."""
    try:
        return max(1, int(float(response.headers["Retry-After"])))
    except (KeyError, ValueError):
        return DEFAULT_RETRY_AFTER_SECONDS


def _record_rate_limit_headers(response):
    """Log AniList's rate-limit headers and keep the lowest 'remaining' value seen."""
    limit = response.headers.get("X-RateLimit-Limit")
    remaining = response.headers.get("X-RateLimit-Remaining")
    logger.info("HTTP %s, X-RateLimit-Limit=%s, X-RateLimit-Remaining=%s", response.status_code, limit, remaining)
    if limit is not None and limit not in stats["limit_values"]:
        stats["limit_values"].append(limit)
    if remaining is not None and remaining.isdigit():
        lowest = stats["lowest_remaining"]
        stats["lowest_remaining"] = int(remaining) if lowest is None else min(lowest, int(remaining))
