"""One shared connection to MongoDB Atlas for the whole project.

The levels, from biggest to smallest:
  client     -> the connection to the whole cluster
  database   -> a named group of collections (ours is "episode_three")
  collection -> a group of documents, like a table
  document   -> one record, stored as nested key/value data (like a dict)
"""
import os
from urllib.parse import unquote, urlsplit

from pymongo import MongoClient
from pymongo.errors import ConfigurationError, OperationFailure, ServerSelectionTimeoutError

from episode_three import config

BYTES_PER_MB = 1024 * 1024

# A MongoClient keeps a pool of open connections and reuses them, and setting
# one up is slow. So the whole program shares ONE client, created on first use.
_client = None


def get_client():
    """Return the shared MongoClient, creating it the first time it's needed."""
    global _client
    if _client is None:
        _client = MongoClient(
            config.get_mongodb_uri(),
            # Give up after 10 seconds (default is 30) if Atlas can't be reached.
            serverSelectionTimeoutMS=10_000,
            # A label that shows up in Atlas logs, so we know which program connected.
            appname="episode-three",
            # Give dates back with their UTC time zone attached, so a date read from
            # the database equals the same date built fresh in Python.
            tz_aware=True,
        )
    return _client


def get_db():
    """Return the project database (episode_three unless .env says otherwise)."""
    return get_client()[config.MONGODB_DB]


def size_mb(db_name):
    """Storage a database uses toward the free-tier limit: data + indexes, in MB.

    Atlas counts the uncompressed size of every document plus every index, which
    is what dataSize and indexSize from the dbStats command report.
    """
    stats = get_client()[db_name].command("dbStats")
    return (stats["dataSize"] + stats["indexSize"]) / BYTES_PER_MB


def explain_error(error):
    """Turn an exception into a short message with the most likely fix.

    The connection string and password are removed first, so nothing secret
    is ever printed.
    """
    details = _hide_secrets(str(error))
    short_details = details[:300]

    if isinstance(error, config.ConfigError):
        return details
    if "CERTIFICATE_VERIFY_FAILED" in details:
        return (
            "The secure (TLS) connection to Atlas failed a certificate check.\n"
            "Report this to the instructor; don't install anything to fix it yet.\n"
            "Details: " + short_details
        )
    if isinstance(error, OperationFailure) and "authentication failed" in details.lower():
        return (
            "Authentication failed.\n"
            "Check the username/password in MONGODB_URI "
            "(special characters must be URL-encoded)."
        )
    if isinstance(error, ServerSelectionTimeoutError):
        return (
            "Could not reach Atlas within 10 seconds.\n"
            "Check Atlas -> Network Access: is your current IP on the allowlist?\n"
            "On college or office Wi-Fi, port 27017 may be blocked; try a phone hotspot.\n"
            "Details: " + short_details
        )
    if isinstance(error, ConfigurationError) and (
        "DNS" in details or "resolution lifetime" in details
    ):
        return (
            "Your network couldn't look up the Atlas address (a DNS problem).\n"
            "Try switching Windows DNS to 8.8.8.8, or use the 'Legacy URI String'\n"
            "from Atlas -> Connect -> Drivers as MONGODB_URI.\n"
            "Details: " + short_details
        )
    return f"{type(error).__name__}: {short_details}"


def _hide_secrets(text):
    """Replace the connection string and password in `text` with placeholders."""
    uri = os.getenv("MONGODB_URI", "").strip()
    if not uri:
        return text
    text = text.replace(uri, "<connection string hidden>")
    try:
        password = urlsplit(uri).password
    except ValueError:
        password = None
    if password:
        for form in {password, unquote(password)}:
            text = text.replace(form, "<password hidden>")
    return text
